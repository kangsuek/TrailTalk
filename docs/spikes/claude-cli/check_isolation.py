"""4. 사용자 설정·CLAUDE.md·메모리가 대화에 섞이지 않는지 확인한다.

작업 폴더에 비밀 단어를 넣은 CLAUDE.md를 두고, 격리 옵션 유무에 따라 모델이 그 단어나
사용자 전역 CLAUDE.md(~/.claude/CLAUDE.md)의 규칙을 아는지 비교한다.
"""

import tempfile
from pathlib import Path

import common
from common import CliSession, run

QUESTION = (
    "지금 너에게 주어진 지침, 메모리, 프로젝트 문서에 적힌 규칙이나 단어를 아는 대로 모두 나열해. "
    "특히 '비밀 단어'가 있으면 그대로 말해. 없으면 없다고 해."
)
LEAK_MARKERS = ["블루베리42", "Plan Mode", "Playwright", "서브에이전트"]


async def probe(label: str, isolate: bool) -> None:
    work = Path(tempfile.mkdtemp(prefix="trailtalk-iso-"))
    (work / "CLAUDE.md").write_text("비밀 단어는 블루베리42 이다.\n", encoding="utf-8")
    saved = common.ISOLATION_FLAGS
    if not isolate:
        common.ISOLATION_FLAGS = []
    try:
        session = CliSession(system_prompt="너는 테스트 봇이다.", cwd=work)
    finally:
        common.ISOLATION_FLAGS = saved
    await session.start()
    turn = await session.ask(QUESTION)
    init = session.init_event or {}
    leaks = [m for m in LEAK_MARKERS if m in turn.text]
    print(
        f"[{label}] 누출 표지: {leaks or '없음'} | tools={init.get('tools')} "
        f"| mcp={len(init.get('mcp_servers', []))} | plugins={len(init.get('plugins', []))} "
        f"| skills={len(init.get('skills', []))}"
    )
    print(f"[{label}] 답변: {turn.text[:200]!r}")
    await session.close()


async def main() -> None:
    await probe("격리 옵션 없음", isolate=False)
    await probe("격리 옵션 적용", isolate=True)


run(main)
