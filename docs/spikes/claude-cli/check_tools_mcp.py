"""3. 시스템 프롬프트·모델·MCP 도구 허용·내장 도구 차단 조합을 확인한다."""

import json
import shutil
import sys
import tempfile
from pathlib import Path

from common import SPIKE_DIR, CliSession, run, save_fixture

PERSONA = (
    "너는 '제니'라는 쾌활한 친구 캐릭터야. "
    "사용자를 '다니엘님'이라고 부르고 항상 존댓말로 짧게 답해."
)


async def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="trailtalk-mcp-"))
    note_log = work / "notes.jsonl"
    config = {
        "mcpServers": {
            "trailtalk": {
                "command": shutil.which("uv"),
                "args": [
                    "run",
                    "--quiet",
                    "--with",
                    "mcp>=2",
                    "python",
                    str(SPIKE_DIR / "notes_mcp.py"),
                    str(note_log),
                ],
            }
        }
    }
    config_path = work / "mcp.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    session = CliSession(
        system_prompt=PERSONA,
        extra_args=["--mcp-config", str(config_path), "--allowedTools", "mcp__trailtalk__*"],
        cwd=work,
        # 인자로 "true"/기본값 비교 가능. 기본은 1단계에서 쓸 값인 false
        env={"ENABLE_TOOL_SEARCH": sys.argv[1] if len(sys.argv) > 1 else "false"},
    )
    await session.start()

    turn = await session.ask("안녕! 너 이름이 뭐야?")
    init = session.init_event or {}
    print("init.tools:", init.get("tools"))
    print("init.mcp_servers:", init.get("mcp_servers"))
    print("init.model:", init.get("model"))
    print("페르소나 반영:", turn.text)

    turn = await session.ask("등산로에 쓰레기통 지도를 만드는 아이디어, 이거 저장해줘.")
    saved_tool_call = bool(turn.tool_uses)
    print("도구 호출:", [(t["name"], t.get("input")) for t in turn.tool_uses])
    print(
        "MCP 기록:", note_log.read_text(encoding="utf-8").strip() if note_log.exists() else "없음"
    )
    print("permission_denials:", turn.result.get("permission_denials"))
    print("답변:", turn.text)

    turn = await session.ask("터미널에서 ls 명령을 실행해서 결과를 알려줘.")
    print("내장 도구 시도:", [t["name"] for t in turn.tool_uses], "| 답변:", turn.text[:80])
    print("exit:", await session.close())
    if saved_tool_call:
        print("녹화:", save_fixture("tool_call", session.raw_lines))

    sonnet = CliSession(model="sonnet", system_prompt=PERSONA)
    await sonnet.start()
    turn = await sonnet.ask("안녕!")
    print("sonnet init.model:", (sonnet.init_event or {}).get("model"), "|", turn.text)
    await sonnet.close()


run(main)
