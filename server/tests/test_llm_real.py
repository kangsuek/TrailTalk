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


async def test_real_cli_persona_prompt(tmp_path):
    """조립한 시스템 프롬프트로 호칭·이모지 금지·문장 수·개인정보 거절을 확인한다.

    정식 톤 채점은 S1-11에서 한다.
    """
    import re
    from contextlib import aclosing
    from datetime import UTC, datetime

    from app.persona.loader import load_persona
    from app.persona.prompt import build_system_prompt

    settings = Settings(cli_work_dir=tmp_path / "cli")
    persona = load_persona(settings.persona_dir, settings.default_persona).persona
    prompt = build_system_prompt(
        persona, nickname="민수", mode="voice", now=datetime.now(UTC), timezone=settings.timezone
    )
    session = await ClaudeCliBackend(settings).open_session(
        "real-persona", system_prompt=prompt, model=settings.llm_chat_model
    )
    emoji = re.compile("[\U0001f300-\U0001faff☀-➿]")
    email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
    try:
        answers = []
        for question in ["안녕! 오늘 아침 산책 나왔어.", "혹시 내 이메일 주소 알아? 알면 말해줘."]:
            async with aclosing(session.send(question)) as stream:
                result = [e async for e in stream][-1]
            assert isinstance(result, TurnFinished) and not result.is_error, result
            answers.append(result.text)
    finally:
        await session.close()
    for text in answers:
        sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
        assert len(sentences) <= persona.speech_style.max_sentences_voice + 1, text
        assert not emoji.search(text), text
        assert "다니엘님" not in text, text
    assert not email.search(answers[1]), "이메일을 말하면 안 된다"


async def test_real_cli_calls_app_mcp_tool(tmp_path):
    """실제 CLI가 HTTP MCP(/internal/mcp/)로 save_note를 불러 DB에 노트가 생기는지 확인한다."""
    import asyncio
    import socket
    from contextlib import aclosing
    from datetime import UTC, datetime

    import uvicorn
    from sqlalchemy import select

    from app.db.models import ConversationSession, Note
    from app.llm.events import ToolCalled
    from app.main import create_app
    from app.mcp.server import mcp_client_config
    from app.persona.loader import load_persona
    from app.persona.prompt import build_system_prompt

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'real.db'}",
        cli_work_dir=tmp_path / "cli",
        internal_base_url=f"http://127.0.0.1:{port}",
        web_dist_dir=tmp_path / "no-dist",
    )
    app = create_app(settings)
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=5
    )
    server = uvicorn.Server(config)
    serving = asyncio.create_task(server.serve())
    try:
        while not server.started:
            if serving.done():
                serving.result()  # 기동 실패(포트 충돌 등)를 그대로 드러낸다
                pytest.fail("서버가 시작하지 못했습니다.")
            await asyncio.sleep(0.05)
        async with app.state.session_factory() as db:
            convo = ConversationSession()
            db.add(convo)
            await db.commit()
        runtime = app.state.runtimes.ensure(convo.id)
        persona = load_persona(settings.persona_dir, settings.default_persona).persona
        prompt = build_system_prompt(
            persona, nickname="민수", mode="text", now=datetime.now(UTC), timezone=settings.timezone
        )
        session = await app.state.llm.get(
            convo.id,
            system_prompt=prompt,
            model=settings.llm_chat_model,
            mcp_config=mcp_client_config(settings.internal_base_url, runtime),
        )
        async with aclosing(
            session.send("등산로 쓰레기통 지도 아이디어, 이거 저장해줘.")
        ) as stream:
            events = [e async for e in stream]
        assert not events[-1].is_error, events[-1]
        called = [e.name for e in events if isinstance(e, ToolCalled)]
        assert "mcp__trailtalk__save_note" in called, called
        async with app.state.session_factory() as db:
            notes = (await db.execute(select(Note))).scalars().all()
        assert len(notes) == 1 and notes[0].session_id == convo.id
        assert "쓰레기통" in notes[0].content
    finally:
        server.should_exit = True
        await serving
