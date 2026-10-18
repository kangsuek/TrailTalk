"""화자 인식 스파이크(S3-35) 공통: 설정·OpenAI 호출·ffmpeg.

server/ 폴더에서 실행한다(app.config로 키를 읽는다). 오디오는 SPIKE_DIR(필수, 임시 폴더)에 둔다.
"""

import asyncio
import base64
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.getcwd())  # server/의 app 패키지

import httpx2  # noqa: E402

from app.config import Settings  # noqa: E402

SETTINGS = Settings()
OUT = Path(os.environ.get("SPIKE_DIR") or sys.exit("SPIKE_DIR(임시 폴더)를 지정하세요"))
FFMPEG = os.environ.get("FFMPEG_PATH", str(Path.home() / ".local/bin/ffmpeg"))
RATE = 16000


def headers() -> dict[str, str]:
    key = SETTINGS.openai_api_key
    if key is None:
        sys.exit("OPENAI_API_KEY(WHISPER_API_KEY)가 없습니다")
    return {"Authorization": f"Bearer {key.get_secret_value()}"}


def url(path: str) -> str:
    return SETTINGS.openai_base_url.rstrip("/") + path


def ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def duration(path: Path) -> float:
    """ffprobe가 없어 ffmpeg -i의 Duration으로 본다."""
    out = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def data_url(path: Path) -> str:
    return "data:audio/wav;base64," + base64.b64encode(path.read_bytes()).decode()


async def transcribe(
    client: httpx2.AsyncClient,
    audio: Path,
    *,
    model: str,
    names: list[str] | None = None,
    refs: list[Path] | None = None,
) -> tuple[int, dict | str, float]:
    """(상태 코드, JSON 또는 오류 본문, 걸린 초)."""
    data: dict[str, str | list[str]] = {"model": model}
    if "diarize" in model:
        data |= {"response_format": "diarized_json", "chunking_strategy": "auto"}
        if names:
            data["known_speaker_names[]"] = names
            data["known_speaker_references[]"] = [data_url(p) for p in refs or []]
    else:
        data |= {"response_format": "json", "languages": ["ko"]}
    started = time.perf_counter()
    response = await client.post(
        url("/audio/transcriptions"),
        headers=headers(),
        data=data,
        files={"file": (audio.name, audio.read_bytes(), "audio/wav")},
        timeout=60,
    )
    elapsed = time.perf_counter() - started
    try:
        body: dict | str = response.json()
    except ValueError:
        body = response.text[:500]
    return response.status_code, body, elapsed


def segments(body: dict | str) -> str:
    if not isinstance(body, dict):
        return f"오류: {body}"
    if "segments" not in body:
        return f"text={body.get('text')!r}" if "text" in body else f"오류: {body}"
    return " | ".join(
        f"[{s.get('speaker')} {s.get('start', 0):.1f}-{s.get('end', 0):.1f}] "
        f"{s.get('text', '').strip()}"
        for s in body["segments"]
    )


def run(main) -> None:  # noqa: ANN001
    OUT.mkdir(parents=True, exist_ok=True)
    asyncio.run(main())
