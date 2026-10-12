"""9. 대화 중 웹 검색: WebSearch·WebFetch만 켜고 MCP 도구와 함께 동작하는지 확인한다.

서버와 같은 조건(토큰 인증, 격리 옵션, ENABLE_TOOL_SEARCH=false)으로 실행한다.
"""

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from common import SPIKE_DIR, CliSession, run, save_fixture

PERSONA = (
    "너는 '제니'라는 쾌활한 친구 캐릭터야. 사용자를 '다니엘님'이라고 부르고 존댓말로 짧게 답해. "
    "최신 정보나 사실 확인이 필요한 질문에만 웹 검색을 하고, 답할 때 출처 사이트 이름을 짧게 밝혀. "
    "일상 대화에는 검색하지 마."
)


def summarize(label: str, turn) -> None:
    kinds = Counter(
        e["event"]["type"] if e["type"] == "stream_event" else e["type"] for e in turn.events
    )
    tools = [
        (t["name"], json.dumps(t.get("input"), ensure_ascii=False)[:80]) for t in turn.tool_uses
    ]
    first_tool = f"{turn.first_tool_s:.2f}s" if turn.first_tool_s else "-"
    first_text = f"{turn.first_delta_s:.2f}s" if turn.first_delta_s else "-"
    print(f"[{label}] 도구 {tools or '없음'}")
    print(
        f"[{label}] 첫 도구 {first_tool}, 첫 텍스트 {first_text}, 전체 {turn.elapsed_s:.2f}s, "
        f"is_error={turn.result['is_error']}, 거부={turn.result.get('permission_denials')}"
    )
    print(f"[{label}] 이벤트 {dict(kinds)}")
    print(f"[{label}] 답변 {turn.text[:160]!r}")


async def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="trailtalk-web-"))
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
    (work / "mcp.json").write_text(json.dumps(config), encoding="utf-8")
    session = CliSession(
        model="sonnet",
        system_prompt=PERSONA,
        tools="WebSearch,WebFetch",
        extra_args=[
            "--mcp-config",
            str(work / "mcp.json"),
            "--allowedTools",
            "mcp__trailtalk__*,WebSearch,WebFetch",
        ],
        env={"ENABLE_TOOL_SEARCH": "false"},
        use_env_token=True,
        cwd=work,
    )
    await session.start()
    try:
        summarize("일상 대화", await session.ask("안녕! 오늘 산책하기 좋은 날이네."))
        print("init.tools:", (session.init_event or {}).get("tools"))
        summarize("최신 정보", await session.ask("Claude Code 최신 버전이 몇이야?"))
        summarize(
            "페이지 읽기",
            await session.ask(
                "https://docs.astral.sh/uv/ 페이지를 읽고 uv가 뭔지 한 문장으로 알려줘."
            ),
        )
        summarize("노트 저장", await session.ask("방금 알게 된 uv 이야기, 메모로 저장해줘."))
        print(
            "MCP 기록:",
            note_log.read_text(encoding="utf-8").strip() if note_log.exists() else "없음",
        )
        summarize("셸 차단", await session.ask("터미널에서 ls를 실행해서 결과를 알려줘."))
    finally:
        print("exit:", await session.close())
    print("녹화:", save_fixture("web_search", session.raw_lines))


run(main)
