"""Claude Code CLI 검증 스파이크 공통 모듈 (구현 계획서 S0-04).

`claude -p`를 stream-json 입출력으로 띄워 두고 턴을 주고받는 최소 래퍼다.
1단계 `ClaudeCliBackend`의 시제품 역할도 한다.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import statistics
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
REPO_DIR = SPIKE_DIR.parents[2]
FIXTURE_DIR = REPO_DIR / "server" / "tests" / "fixtures" / "claude_cli"

# 임시 폴더 경로(사용자 이름·머신 식별자 포함)는 녹화에서 치환한다
TEMP_PATH = re.compile(r"/(?:private/)?(?:tmp|var/folders)/[^\"\s\\]*")

ISOLATION_FLAGS = ["--restricted", "--strict-mcp-config", "--setting-sources", ""]


def load_env_token() -> str | None:
    """저장소 루트 .env의 CLAUDE_CODE_OAUTH_TOKEN 값(없으면 None). 값은 출력하지 않는다."""
    env = REPO_DIR / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "CLAUDE_CODE_OAUTH_TOKEN" and value.strip():
            return value.strip()
    return None


@dataclass
class Turn:
    """한 턴의 결과."""

    text: str = ""
    events: list[dict] = field(default_factory=list)
    first_delta_s: float | None = None
    first_tool_s: float | None = None
    elapsed_s: float = 0.0
    result: dict | None = None
    tool_uses: list[dict] = field(default_factory=list)


class CliSession:
    """세션 하나 = 상주 CLI 프로세스 하나."""

    def __init__(
        self,
        *,
        model: str = "haiku",
        system_prompt: str | None = None,
        tools: str = "",
        extra_args: list[str] | None = None,
        resume: str | None = None,
        persist: bool = False,
        use_env_token: bool = False,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.cwd = cwd or Path(tempfile.mkdtemp(prefix="trailtalk-cli-"))
        args = [
            shutil.which("claude") or "claude",
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--include-partial-messages",
            "--verbose",
            "--model",
            model,
            "--tools",
            tools,
            *ISOLATION_FLAGS,
        ]
        if system_prompt is not None:
            args += ["--system-prompt", system_prompt]
        if resume:
            args += ["--resume", resume]
        if not persist and not resume:
            args.append("--no-session-persistence")
        args += extra_args or []
        self.args = args
        self.env = dict(os.environ)
        self.env.update(env or {})
        if use_env_token:
            token = load_env_token()
            if not token:
                raise RuntimeError(".env에 CLAUDE_CODE_OAUTH_TOKEN이 없습니다")
            self.env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        self.proc: asyncio.subprocess.Process | None = None
        self.init_event: dict | None = None
        self.session_id: str | None = None
        self.started_at = 0.0
        self.raw_lines: list[str] = []

    async def start(self) -> None:
        self.started_at = time.perf_counter()
        self.proc = await asyncio.create_subprocess_exec(
            *self.args,
            cwd=self.cwd,
            env=self.env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,
        )

    async def _send(self, obj: dict) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()

    async def send_user(self, text: str) -> None:
        await self._send({"type": "user", "message": {"role": "user", "content": text}})

    async def send_interrupt(self) -> str:
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        await self._send(
            {
                "type": "control_request",
                "request_id": request_id,
                "request": {"subtype": "interrupt"},
            }
        )
        return request_id

    async def read_event(self, timeout: float = 120) -> dict | None:
        assert self.proc and self.proc.stdout
        line = await asyncio.wait_for(self.proc.stdout.readline(), timeout)
        if not line:
            return None
        decoded = line.decode()
        try:
            event = json.loads(decoded)
        except json.JSONDecodeError:
            return {"type": "non_json", "text": decoded}
        self.raw_lines.append(decoded)
        if event.get("type") == "system" and event.get("subtype") == "init":
            self.init_event = event
            self.session_id = event.get("session_id")
        return event

    async def read_turn(self, sent_at: float, on_delta=None, timeout: float = 180) -> Turn:
        """result 이벤트가 올 때까지 읽는다. on_delta(turn)가 True를 반환하면 그 시점에 멈춘다."""
        turn = Turn()
        while True:
            event = await self.read_event(timeout)
            if event is None:
                raise RuntimeError(f"CLI가 턴 도중 종료됨: {await self.stderr()}")
            turn.events.append(event)
            kind = event.get("type")
            if kind == "stream_event":
                block = event["event"].get("content_block") or {}
                if (
                    block.get("type") in ("tool_use", "server_tool_use")
                    and turn.first_tool_s is None
                ):
                    turn.first_tool_s = time.perf_counter() - sent_at
                delta = event["event"].get("delta", {})
                if delta.get("type") == "text_delta":
                    if turn.first_delta_s is None:
                        turn.first_delta_s = time.perf_counter() - sent_at
                    turn.text += delta["text"]
                    if on_delta and on_delta(turn):
                        return turn
            elif kind == "assistant":
                for block in event["message"].get("content", []):
                    if block.get("type") == "tool_use":
                        turn.tool_uses.append(block)
            elif kind == "result":
                turn.result = event
                turn.elapsed_s = time.perf_counter() - sent_at
                return turn

    async def ask(self, text: str, **kwargs) -> Turn:
        sent_at = time.perf_counter()
        await self.send_user(text)
        return await self.read_turn(sent_at, **kwargs)

    async def stderr(self) -> str:
        if self.proc and self.proc.stderr:
            try:
                return (await asyncio.wait_for(self.proc.stderr.read(), 2)).decode()[-2000:]
            except TimeoutError:
                return ""
        return ""

    async def close(self) -> int | None:
        if not self.proc:
            return None
        if self.proc.stdin and not self.proc.stdin.is_closing():
            self.proc.stdin.close()
        try:
            return await asyncio.wait_for(self.proc.wait(), 30)
        except TimeoutError:
            self.proc.kill()
            return await self.proc.wait()


def median(values: list[float]) -> float:
    return round(statistics.median(values), 3)


def save_fixture(name: str, lines: list[str]) -> Path:
    """녹화 출력을 공개 저장소에 둘 수 있게 치환해 저장한다."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    home = str(Path.home())
    ids: dict[str, str] = {}
    out = []
    for line in lines:
        event = json.loads(line)
        sid = event.get("session_id")
        if sid and sid not in ids:
            ids[sid] = f"00000000-0000-4000-8000-{len(ids):012d}"
        text = line.replace(home, "/home/user")
        text = TEMP_PATH.sub("/tmp/redacted", text)
        for real, fake in ids.items():
            text = text.replace(real, fake)
        event = json.loads(text)
        if event.get("type") == "system" and event.get("subtype") == "init":
            event["cwd"] = "/tmp/trailtalk-cli"
            # 개인 환경(스킬·플러그인·슬래시 명령) 목록은 녹화에서 뺀다
            for key in ("slash_commands", "terminal_slash_commands", "skills", "agents", "plugins"):
                if key in event:
                    event[key] = []
        out.append(json.dumps(event, ensure_ascii=False))
    path = FIXTURE_DIR / f"{name}.jsonl"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def run(main) -> None:
    asyncio.run(main())
