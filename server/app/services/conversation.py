"""대화 세션과 턴 처리(계획서 S1-08).

- 세션 시작: 프롬프트를 조립해 CLI를 열고, 숨은 첫 메시지로 받은 인사말을
  assistant 턴(seq 0)으로 저장한다.
- 턴: 사용자 턴을 먼저 저장하고 CLI 이벤트를 SSE 이벤트(app/api/events.py)로 바꿔 보낸다.
- 종료: CLI를 닫고 대화 런타임(MCP 토큰)을 버린 뒤 CLI 대화 기록 파일을 지운다.

프롬프트는 세션의 시작 시각·모드와 현재 프로필로 만든다. CLI가 죽어 --resume으로 다시 띄울 때도
같은 값으로 다시 만든다.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing

import anyio
from fastapi import FastAPI
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.events import (
    DoneEvent,
    ErrorEvent,
    SentenceEvent,
    ToolEvent,
    TurnEvent,
    encode_sse,
    public_tool_name,
)
from app.db.models import ConversationMode, ConversationSession, SessionStatus, Turn, TurnRole
from app.db.types import new_id, utcnow
from app.errors import AppError
from app.llm.backend import LlmError, LlmSession
from app.llm.claude_cli import delete_cli_session_file
from app.llm.events import (
    TextDelta,
    ToolCalled,
    ToolFinished,
    ToolStarted,
    TurnFinished,
    TurnStarted,
)
from app.mcp.server import mcp_client_config
from app.persona.loader import LoadedPersona
from app.persona.prompt import build_system_prompt
from app.persona.rules import GREETING_INSTRUCTION
from app.services.profile import profile_with_persona
from app.services.runtime import ConversationRuntime
from app.voice.sentences import SentenceSplitter

logger = logging.getLogger("trailtalk.conversation")


class SessionNotFound(AppError):
    def __init__(self) -> None:
        super().__init__("session_not_found", "대화 세션을 찾을 수 없습니다.", 404)


class SessionEnded(AppError):
    def __init__(self) -> None:
        super().__init__("session_ended", "이미 끝난 대화입니다.", 409)


class TurnBusy(AppError):
    def __init__(self) -> None:
        super().__init__("turn_in_progress", "이전 답변이 아직 끝나지 않았습니다.", 409)


_LLM_PUBLIC_MESSAGES = {
    "llm_process_exited": "답변 도중 연결이 끊겼어요. 다시 말해 주세요.",
    "llm_timeout": "답변이 너무 오래 걸려 멈췄어요. 다시 말해 주세요.",
}


def public_error(exc: AppError) -> AppError:
    """클라이언트에 보낼 오류. LLM·서버 오류의 상세(CLI stderr, 경로 등)는 로그에만 남긴다."""
    if isinstance(exc, LlmError):
        message = _LLM_PUBLIC_MESSAGES.get(exc.code, "답변을 만들지 못했습니다.")
        return LlmError(exc.code, message, exc.status_code)
    if exc.status_code >= 500:
        return AppError(exc.code, "서버 내부 오류가 발생했습니다.", exc.status_code)
    return exc


async def _set_status(db: AsyncSession, session_id: str, status: SessionStatus) -> None:
    """상태를 바꾼다. 이미 끝난 세션은 건드리지 않는다(종료 요청과 턴이 겹쳐도 ended를 지킨다)."""
    values: dict = {"status": status}
    if status is SessionStatus.ENDED:
        values["ended_at"] = utcnow()
    await db.execute(
        update(ConversationSession)
        .where(
            ConversationSession.id == session_id,
            ConversationSession.status != SessionStatus.ENDED,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )


async def get_session(db: AsyncSession, session_id: str) -> ConversationSession:
    convo = await db.get(ConversationSession, session_id)
    if convo is None:
        raise SessionNotFound()
    return convo


async def open_llm(
    app: FastAPI, db: AsyncSession, convo: ConversationSession
) -> tuple[LlmSession, LoadedPersona]:
    """대화의 CLI 세션과 프롬프트에 쓴 페르소나. CLI가 살아 있으면 재사용하고 없으면 --resume."""
    settings = app.state.settings
    profile, loaded = await profile_with_persona(db, settings)
    # 프로필·페르소나 행을 만들거나 고쳤으면 바로 커밋한다. 턴 내내 쓰기 잠금을 쥐면
    # 같은 시간에 MCP save_note 같은 다른 쓰기가 SQLite 잠금 대기 끝에 실패한다
    await db.commit()
    prompt = build_system_prompt(
        loaded.persona,
        nickname=profile.nickname,
        mode=convo.mode.value,
        now=convo.started_at,
        timezone=settings.timezone,
    )
    runtime = app.state.runtimes.ensure(convo.id)
    session = await app.state.llm.get(
        convo.id,
        system_prompt=prompt,
        model=settings.llm_chat_model,
        resume_id=convo.cli_session_id,
        mcp_config=mcp_client_config(settings.internal_base_url, runtime),
    )
    return session, loaded


async def teardown(app: FastAPI, session_id: str, cli_session_id: str | None) -> None:
    """CLI를 닫은 뒤 런타임을 버린다(순서 주의: services/runtime.py). 기록 파일도 지운다."""
    await app.state.llm.close(session_id)
    app.state.runtimes.discard(session_id)
    if await asyncio.to_thread(delete_cli_session_file, cli_session_id):
        logger.info("CLI 대화 기록 삭제(session=%s)", session_id)


async def start_session(
    app: FastAPI, db: AsyncSession, mode: ConversationMode
) -> tuple[ConversationSession, Turn, LoadedPersona]:
    convo = ConversationSession(mode=mode)
    db.add(convo)
    await db.commit()
    session_id = convo.id
    runtime = app.state.runtimes.ensure(session_id)
    cli_session_id = None
    try:
        async with runtime.turn_lock:
            session, persona = await open_llm(app, db, convo)
            parts: list[str] = []
            finished = None
            async with aclosing(session.send(GREETING_INSTRUCTION)) as stream:
                async for event in stream:
                    if isinstance(event, TurnStarted) and event.cli_session_id:
                        cli_session_id = event.cli_session_id
                    elif isinstance(event, TextDelta):
                        parts.append(event.text)
                    elif isinstance(event, TurnFinished):
                        finished = event
            if finished is None or finished.is_error:
                detail = finished.error_message if finished else "응답 없음"
                logger.warning("인사말 실패(session=%s): %s", session_id, detail)
                raise LlmError("llm_error", "인사말을 받지 못했습니다.")
            greeting = Turn(
                session_id=convo.id,
                seq=0,
                role=TurnRole.ASSISTANT,
                text="".join(parts).strip() or finished.text,
            )
            db.add(greeting)
            convo.cli_session_id = cli_session_id
            await db.commit()
    except BaseException as exc:
        # 인사말도 없는 빈 세션은 남기지 않는다(rollback으로 만료된 객체 대신 ID로 지운다).
        # 요청 취소·서버 종료 중에도 정리하도록 취소에서 보호한다
        try:
            with anyio.CancelScope(shield=True):  # 같은 태스크에서 끝까지 정리한다
                await _discard_new_session(app, db, session_id, cli_session_id)
        except Exception:
            logger.exception("시작 실패 정리 중 예외(session=%s)", session_id)
        if isinstance(exc, AppError):
            if isinstance(exc, LlmError) or exc.status_code >= 500:
                logger.warning("세션 시작 실패(code=%s): %s", exc.code, exc.message)
            raise public_error(exc) from exc
        raise
    return convo, greeting, persona


async def _discard_new_session(
    app: FastAPI, db: AsyncSession, session_id: str, cli_session_id: str | None
) -> None:
    await db.rollback()
    await teardown(app, session_id, cli_session_id)
    await db.execute(delete(ConversationSession).where(ConversationSession.id == session_id))
    await db.commit()


async def end_session(app: FastAPI, db: AsyncSession, convo: ConversationSession) -> None:
    """세션을 끝낸다. 이미 끝났으면 정리만 다시 한다(멱등)."""
    await _set_status(db, convo.id, SessionStatus.ENDED)
    await db.commit()
    runtime = app.state.runtimes.get(convo.id)
    await app.state.llm.close(convo.id)  # 진행 중인 턴이 있으면 여기서 끊긴다
    if runtime is not None:
        try:
            # 턴 스트림이 정리를 마칠 때까지 기다린다(CLI를 닫았으니 보통 바로 끝난다)
            async with asyncio.timeout(_END_WAIT_S):
                async with runtime.turn_lock:
                    pass
        except TimeoutError:
            logger.warning("종료 중 턴 정리 대기 시간 초과(session=%s)", convo.id)
    await db.refresh(convo)  # 턴 중에 바뀐 cli_session_id·상태를 다시 읽는다
    await teardown(app, convo.id, convo.cli_session_id)


_END_WAIT_S = 10.0


def check_turn_allowed(app: FastAPI, convo: ConversationSession) -> None:
    """SSE를 열기 전 검사. 실패는 JSON 오류로 나간다."""
    if convo.status is SessionStatus.ENDED:
        raise SessionEnded()
    runtime = app.state.runtimes.get(convo.id)
    if runtime is not None and runtime.turn_lock.locked():
        raise TurnBusy()


def _error(exc: AppError) -> bytes:
    exc = public_error(exc)
    return encode_sse(ErrorEvent(code=exc.code, message=exc.message))


async def stream_turn(app: FastAPI, session_id: str, text: str) -> AsyncIterator[bytes]:
    """사용자 메시지 한 턴을 처리하며 SSE 바이트를 낸다.

    클라이언트가 끊기면 이 제너레이터가 닫히고 aclosing이 CLI 턴을 멈춘다. 이때 사용자 턴만
    남는다(문장별 저장은 S2-01).
    """
    runtime = app.state.runtimes.ensure(session_id)
    if runtime.turn_lock.locked():  # 검사와 획득 사이에 await가 없어 경합하지 않는다
        yield _error(TurnBusy())
        return
    async with runtime.turn_lock:
        db = app.state.session_factory()
        try:
            # 안쪽 제너레이터도 바로 닫아야 락을 풀기 전에 CLI 턴 정리(인터럽트)가 끝난다
            async with aclosing(_run_turn(app, db, runtime, session_id, text)) as chunks:
                async for chunk in chunks:
                    yield chunk
        finally:
            # 연결이 끊겨 취소된 중에도 커넥션을 온전히 돌려준다(닫기가 다시 취소되면 망가진
            # 커넥션이 풀에 남아 다음 요청이 실패한다)
            with anyio.CancelScope(shield=True):
                await db.close()


async def _run_turn(
    app: FastAPI, db: AsyncSession, runtime: ConversationRuntime, session_id: str, text: str
) -> AsyncIterator[bytes]:
    """턴 락을 잡은 상태에서 한 턴을 처리한다.

    짧은 DB 작업 구간은 취소(연결 끊김)에서 보호한다. 쿼리 도중 취소되면 SQLAlchemy가
    커넥션을 폐기하다 그것마저 취소되어, 죽은 커넥션이 풀에 남는다.
    """
    with anyio.CancelScope(shield=True):
        convo = await db.get(ConversationSession, session_id)
        if convo is not None and convo.status is not SessionStatus.ENDED:
            last_seq = await db.scalar(
                select(func.max(Turn.seq)).where(Turn.session_id == session_id)
            )
            seq = (last_seq if last_seq is not None else -1) + 1
            user_turn = Turn(session_id=session_id, seq=seq, role=TurnRole.USER, text=text)
            db.add(user_turn)
            await _set_status(db, session_id, SessionStatus.ACTIVE)  # 쉬기 중이면 다시 이어 감
            await db.commit()
    if convo is None or convo.status is SessionStatus.ENDED:
        app.state.runtimes.discard(session_id)  # 위에서 새로 만든 런타임(토큰)을 남기지 않는다
        yield _error(SessionNotFound() if convo is None else SessionEnded())
        return

    assistant_id = new_id()
    yield encode_sse(TurnEvent(turn_id=assistant_id))
    runtime.requested_status = None
    runtime.current_user_turn_id = user_turn.id
    try:
        with anyio.CancelScope(shield=True):
            await db.refresh(convo)  # 그사이 종료 API가 끝냈으면 CLI를 다시 띄우지 않는다
            if convo.status is SessionStatus.ENDED:
                raise SessionEnded()
            session, _ = await open_llm(app, db, convo)
        splitter = SentenceSplitter()
        index = 0
        parts: list[str] = []
        tool_names: dict[str, str] = {}
        finished: TurnFinished | None = None

        def sentences(items: list[str]) -> list[bytes]:
            nonlocal index
            out = []
            for item in items:
                out.append(encode_sse(SentenceEvent(index=index, text=item)))
                index += 1
            return out

        async with aclosing(session.send(text)) as stream:
            async for event in stream:
                if isinstance(event, TurnStarted):
                    if event.cli_session_id and event.cli_session_id != convo.cli_session_id:
                        convo.cli_session_id = event.cli_session_id
                        with anyio.CancelScope(shield=True):
                            await db.commit()
                elif isinstance(event, TextDelta):
                    parts.append(event.text)
                    for chunk in sentences(splitter.feed(event.text)):
                        yield chunk
                elif isinstance(event, ToolStarted):
                    # 도구 앞의 말("잠깐 찾아볼게요")은 기다리지 않고 바로 문장으로 보낸다
                    for chunk in sentences(splitter.flush()):
                        yield chunk
                    if parts and not parts[-1][-1:].isspace():
                        parts.append("\n\n")
                    tool_names[event.tool_use_id] = public_tool_name(event.name)
                    yield encode_sse(
                        ToolEvent(
                            phase="start",
                            tool_use_id=event.tool_use_id,
                            name=tool_names[event.tool_use_id],
                        )
                    )
                elif isinstance(event, ToolCalled):
                    name = tool_names.setdefault(event.tool_use_id, public_tool_name(event.name))
                    yield encode_sse(
                        ToolEvent(
                            phase="call",
                            tool_use_id=event.tool_use_id,
                            name=name,
                            input=event.input,
                        )
                    )
                elif isinstance(event, ToolFinished):
                    yield encode_sse(
                        ToolEvent(
                            phase="end",
                            tool_use_id=event.tool_use_id,
                            name=tool_names.get(event.tool_use_id, "unknown"),
                            summary=event.summary,
                            is_error=event.is_error,
                        )
                    )
                elif isinstance(event, TurnFinished):
                    finished = event
        for chunk in sentences(splitter.flush()):
            yield chunk

        if finished is None or (finished.is_error and not finished.interrupted):
            detail = finished.error_message if finished else "응답 없음"
            logger.warning("턴 실패(session=%s): %s", session_id, detail)
            yield _error(LlmError("llm_error", "답변을 만들지 못했습니다."))
            return
        reply = "".join(parts).strip() or finished.text
        with anyio.CancelScope(shield=True):
            db.add(
                Turn(
                    id=assistant_id,
                    session_id=session_id,
                    seq=seq + 1,
                    role=TurnRole.ASSISTANT,
                    text=reply,
                    interrupted=finished.interrupted,
                )
            )
            requested = runtime.pop_requested_status()
            if requested is not None:
                await _set_status(db, session_id, requested)
            await db.commit()
            await db.refresh(convo)  # 같은 시간에 종료 API가 바꿨을 수 있다
            if requested is SessionStatus.ENDED:
                await teardown(app, session_id, convo.cli_session_id)
        yield encode_sse(
            DoneEvent(
                turn_id=assistant_id,
                text=reply,
                interrupted=finished.interrupted,
                session_status=convo.status.value,
            )
        )
    except AppError as exc:
        logger.warning("턴 오류(session=%s, code=%s): %s", session_id, exc.code, exc.message)
        yield _error(exc)
    except Exception:
        logger.exception("턴 처리 중 예외(session=%s)", session_id)
        yield _error(AppError("internal_error", "서버 내부 오류가 발생했습니다.", 500))
    finally:
        runtime.current_user_turn_id = None
