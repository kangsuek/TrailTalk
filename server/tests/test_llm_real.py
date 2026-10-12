"""실제 Claude CLI 통합 테스트. 구독 사용량을 쓰므로 RUN_REAL_CLI=1일 때만 실행한다.

(cd server && RUN_REAL_CLI=1 uv run pytest tests/test_llm_real.py -q)
"""

import os

import pytest

from app.config import Settings
from app.llm.claude_cli import ClaudeCliBackend
from app.llm.events import TextDelta, TurnFinished, TurnStarted

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REAL_CLI") != "1", reason="RUN_REAL_CLI=1일 때만"
)


async def test_real_cli_turn_and_interrupt(tmp_path):
    settings = Settings(cli_work_dir=tmp_path / "cli")
    assert settings.claude_code_oauth_token, ".env에 CLAUDE_CODE_OAUTH_TOKEN이 필요합니다"
    session = await ClaudeCliBackend(settings).open_session(
        "real",
        system_prompt="너는 테스트 봇이다. 한국어 한 문장으로만 답한다.",
        model=settings.llm_chat_model,
    )
    try:
        events = [e async for e in session.send("사과는 무슨 색이야?")]
        assert isinstance(events[0], TurnStarted) and session.cli_session_id
        result = events[-1]
        assert isinstance(result, TurnFinished) and not result.is_error and result.text

        events = []
        async for event in session.send("1부터 200까지 쉼표로 모두 써줘."):
            events.append(event)
            if sum(len(e.text) for e in events if isinstance(e, TextDelta)) > 30:
                await session.interrupt()
        assert events[-1].interrupted

        result = [e async for e in session.send("'끝'이라고만 답해.")][-1]
        assert not result.is_error and result.text
    finally:
        await session.close()
