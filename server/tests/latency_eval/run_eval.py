"""응답 지연 평가(V2-M0-06, spec 3.2절). 실제 Claude CLI·OpenAI를 써서 구독 사용량이 든다.

    (cd server && RUN_REAL_CLI=1 uv run python -m tests.latency_eval.run_eval \
        [--server-turns 10] [--browser-turns 10] [--utterance 파일.wav ...])

평가용 서버(기본 8200, 임시 DB·임시 CLI 작업 폴더)를 띄우고 두 가지를 잰다.
 1) 서버 단계: 같은 발화 파일을 음성 턴으로 직접 보내 인식·CLI 첫 글자·합성 시간을 본다.
 2) 말 끝 → 첫 소리: Playwright(Chromium)로 음성 대화를 구동하고 마이크에 발화를 주입한다.
    앱이 보고한 값은 GET /api/latency로 읽는다(검색 턴은 따로 센다). web/dist 빌드가 필요하다.
8000 서버와 실제 DB는 건드리지 않는다. 리포트는 docs/eval/latency-<날짜>.md에 쓴다.
"""

import argparse
import base64
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import wave
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx2 as httpx

from app.config import REPO_DIR, SERVER_DIR, Settings
from tests.latency_eval.stats import render_report

FIXTURE_WAV = REPO_DIR / "web" / "e2e" / "fixtures" / "utterance.wav"
# 기본 발화 파일은 무음 1초 + 한국어 문장 약 3초 + 무음 20초(make-utterance.sh): 문장 부분만 쓴다
FIXTURE_SPEECH_S = (0.9, 4.3)
BROWSER_SCRIPT = Path(__file__).with_name("browser_eval.mjs")
REPORT_DIR = REPO_DIR / "docs" / "eval"


def load_pcm(path: Path, window: tuple[float, float] | None) -> tuple[bytes, int]:
    """WAV에서 16비트 모노 PCM과 샘플레이트. window(초)가 있으면 그 구간만."""
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise SystemExit(f"{path}: 16비트 모노 WAV만 지원합니다")
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if window is not None:
        start, end = (int(seconds * rate) * 2 for seconds in window)
        frames = frames[start:end]
    return frames, rate


def to_wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def usage_text(client: httpx.Client, wait_s: float = 0) -> str:
    """5시간 창 사용률. 새 서버는 첫 CLI 응답 뒤에야 값이 생겨 시작 값은 대개 "알 수 없음"이다."""
    deadline = time.monotonic() + wait_s
    while True:
        try:
            window = client.get("/api/usage").json().get("five_hour")
            if window:
                return f"{window['utilization']}%"
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return "알 수 없음"
        time.sleep(1)


def wait_healthy(client: httpx.Client, server: subprocess.Popen, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise SystemExit("평가용 서버가 시작 중에 종료되었습니다")
        try:
            if client.get("/api/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit("평가용 서버가 시간 안에 뜨지 않았습니다")


def send_audio_turn(client: httpx.Client, session_id: str, wav_bytes: bytes) -> str | None:
    """음성 턴 하나를 보내고 SSE를 끝까지 읽는다. 답변 턴 ID를 돌려준다(오류면 경고를 찍는다)."""
    turn_id = None
    with client.stream(
        "POST",
        f"/api/sessions/{session_id}/turns/audio",
        content=wav_bytes,
        headers={"Content-Type": "audio/wav"},
        timeout=httpx.Timeout(180),
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: ") :])
            if event.get("type") == "turn":
                turn_id = event.get("turn_id")
            if event.get("type") == "error":
                print(f"  경고: 서버 오류 이벤트 {event.get('code')}", flush=True)
            if event.get("type") in ("done", "error"):
                break
    return turn_id


def run_server_stage(client: httpx.Client, wavs: list[bytes], turns: int) -> str | None:
    """같은 발화 파일로 turns턴을 보낸다. 세션 ID를 돌려준다."""
    session = client.post("/api/sessions", json={"mode": "voice"}).json()
    session_id = session["session"]["id"]
    for index in range(turns):
        started = time.monotonic()
        send_audio_turn(client, session_id, wavs[index % len(wavs)])
        print(f"  서버 직접 {index + 1}/{turns}: {time.monotonic() - started:.1f}초", flush=True)
    return session_id


def run_browser_stage(base_url: str, pcm_list: list[bytes], turns: int, workdir: Path) -> bool:
    payload = workdir / "utterances.json"
    payload.write_text(
        json.dumps({"pcm_b64": [base64.b64encode(pcm).decode() for pcm in pcm_list]}),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "EVAL_BASE_URL": base_url,
        "EVAL_WEB_DIR": str(REPO_DIR / "web"),
        "EVAL_TURNS": str(turns),
        "EVAL_UTTERANCES": str(payload),
    }
    result = subprocess.run(["node", str(BROWSER_SCRIPT)], env=env, capture_output=True, text=True)
    print(f"  브라우저: {result.stdout.strip() or result.stderr.strip()[:300]}", flush=True)
    return result.returncode == 0


def stop_group(server: subprocess.Popen) -> None:
    """서버와 그 자식(CLI)을 종료한다. 10초 안에 안 죽으면 강제 종료."""
    try:
        os.killpg(server.pid, signal.SIGTERM)
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(server.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def build_note() -> str:
    """어느 코드·웹 빌드로 쟀는지 리포트에 남긴다."""
    dist = REPO_DIR / "web" / "dist" / "index.html"
    built = (
        datetime.fromtimestamp(dist.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        if dist.exists()
        else "없음"
    )
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_DIR, capture_output=True, text=True
    ).stdout.strip()
    return f"코드 {head or '알 수 없음'}, web/dist 빌드 {built}"


def main() -> int:
    parser = argparse.ArgumentParser(description="응답 지연 평가(V2-M0-06)")
    parser.add_argument("--server-turns", type=int, default=10)
    parser.add_argument("--browser-turns", type=int, default=10)
    parser.add_argument(
        "--utterance", action="append", type=Path, help="발화 WAV(16비트 모노, 여러 번 가능)"
    )
    parser.add_argument("--port", type=int, default=8200)
    parser.add_argument("--out", type=Path, help="리포트 경로(기본 docs/eval/latency-<날짜>.md)")
    args = parser.parse_args()

    if os.environ.get("RUN_REAL_CLI") != "1":
        raise SystemExit("실제 CLI·OpenAI를 쓰는 평가입니다. RUN_REAL_CLI=1을 붙여 실행하세요")
    if Settings().openai_api_key is None:
        raise SystemExit("OPENAI_API_KEY가 없어 음성 인식·합성을 할 수 없습니다")
    if args.browser_turns and not (REPO_DIR / "web" / "dist" / "index.html").exists():
        raise SystemExit("web/dist가 없습니다. (cd web && npm run build) 후 다시 실행하세요")

    if args.utterance:
        sources = [load_pcm(path, None) for path in args.utterance]
    else:
        sources = [load_pcm(FIXTURE_WAV, FIXTURE_SPEECH_S)]
    wavs = [to_wav(pcm, rate) for pcm, rate in sources]
    pcm_list = [pcm for pcm, rate in sources if rate == 16_000]
    if args.browser_turns and len(pcm_list) != len(sources):
        raise SystemExit("브라우저 구동에는 16kHz WAV가 필요합니다")

    if args.port == 8000:
        raise SystemExit("8000은 사용자 서버 포트입니다. 다른 포트를 쓰세요")
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise SystemExit(
                f"포트 {args.port}가 이미 사용 중입니다(다른 서버를 평가하지 않도록 중단)"
            )

    workdir = Path(tempfile.mkdtemp(prefix="latency-eval-"))
    base_url = f"http://127.0.0.1:{args.port}"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{workdir / 'eval.db'}",
        "CLI_WORK_DIR": str(workdir / "cli"),
        "INTERNAL_BASE_URL": base_url,
        "VOICE_BACKEND": "openai",
    }
    server_log = workdir / "server.log"
    server = None
    failed = True
    try:
        with server_log.open("w") as log:
            # 새 프로세스 그룹: 종료할 때 uvicorn이 띄운 CLI까지 함께 정리한다
            server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1"]
                + ["--port", str(args.port)],
                cwd=SERVER_DIR,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            with httpx.Client(base_url=base_url, timeout=30) as client:
                wait_healthy(client, server)
                usage_before = usage_text(client)
                server_session = None
                if args.server_turns:
                    print(f"서버 단계 {args.server_turns}턴", flush=True)
                    server_session = run_server_stage(client, wavs, args.server_turns)
                browser_ok = True
                if args.browser_turns:
                    print(f"브라우저 구동 {args.browser_turns}턴", flush=True)
                    browser_ok = run_browser_stage(base_url, pcm_list, args.browser_turns, workdir)
                time.sleep(2)  # 마지막 턴의 클라이언트 보고가 닿을 시간
                usage_after = usage_text(client)
                turns = client.get("/api/latency", params={"limit": 500}).json()["turns"]
        failed = False
    finally:
        if server is not None:
            stop_group(server)
        if failed:  # 실패 원인을 볼 수 있게 로그를 남긴다
            keep = workdir.parent / "latency-eval-last-server.log"
            if server_log.exists():
                shutil.copy(server_log, keep)
                print(f"서버 로그 보존: {keep}", flush=True)
        shutil.rmtree(workdir, ignore_errors=True)

    turns.sort(key=lambda t: t["created_at"])
    server_turns = [t for t in turns if t["session_id"] == server_session]
    browser_turns = [t for t in turns if t["session_id"] != server_session]
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    notes = [
        build_note(),
        f"서버 직접 {args.server_turns}턴, 브라우저 {args.browser_turns}턴 요청 "
        f"(기록된 턴: 서버 {len(server_turns)}, 브라우저 {len(browser_turns)})",
        "발화: "
        + (
            ", ".join(p.name for p in args.utterance)
            if args.utterance
            else "e2e/fixtures/utterance.wav 문장 부분"
        ),
        "브라우저는 헤드리스 Chromium이고 마이크는 주입한 발화다"
        "(에코·이어폰·블루투스 지연은 포함하지 않는다).",
    ]
    if not browser_ok:
        notes.append("브라우저 구동이 중간에 실패했다(턴 수 확인).")
    report = render_report(
        date=now.strftime("%Y-%m-%d"),
        server_turns=server_turns,
        browser_turns=browser_turns,
        usage_before=usage_before,
        usage_after=usage_after,
        notes=notes,
    )
    out = args.out or REPORT_DIR / f"latency-{now.strftime('%Y-%m-%d')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"리포트: {out}")
    return 0 if browser_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
