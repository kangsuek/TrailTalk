"""대화 세션과 턴 처리(계획서 S1-08).

- 세션 시작: 프롬프트를 조립해 CLI를 열고, 숨은 첫 메시지로 받은 인사말을
  assistant 턴(seq 0)으로 저장한다.
- 턴: 사용자 턴을 먼저 저장하고 CLI 이벤트를 SSE 이벤트(app/api/events.py)로 바꿔 보낸다.
  답변은 문장을 보내기 전에 문장마다 커밋한다(계획서 S2-01). 끝나지 못한 답변(연결 끊김·오류·
  서버 강제 종료)은 보낸 문장까지 interrupted로 남는다.
- 종료: CLI를 닫고 대화 런타임(MCP 토큰)을 버린 뒤 CLI 대화 기록 파일을 지운다. 그다음 일지
  정리(추출, app/jobs/extract.py)를 백그라운드로 띄운다.

프롬프트는 세션의 시작 시각·모드와 현재 프로필로 만든다. CLI가 죽어 --resume으로 다시 띄울 때도
같은 값으로 다시 만든다.

미리 띄우기: 화면이 열리면 세션 ID와 시작 시각을 먼저 정해 CLI만 띄워 둔다(prepare_session).
시작할 때 같은 조건이면 그 ID·시각으로 세션 행을 만들어, 같은 프롬프트로 살아 있는 프로세스를
재사용한다. 프로세스 기동·첫 요청 준비 시간(약 1.4초)을 인사말 대기에서 뺀다.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import anyio
from fastapi import FastAPI
from sqlalchemy import delete, func, insert, select, update
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
from app.config import Settings
from app.db.models import (
    ConversationMode,
    ConversationSession,
    ExtractStatus,
    SessionStatus,
    Turn,
    TurnRole,
    UserProfile,
)
from app.db.types import new_id, utcnow
from app.errors import AppError
from app.jobs import extract
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
from app.persona.memory import load_memory
from app.persona.prompt import MemoryContext, build_system_prompt
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


def start_error(exc: AppError) -> AppError:
    """세션 시작·미리 띄우기 실패를 클라이언트에 보낼 오류로 바꾼다(내부 정보 없이 시작용 문구)."""
    if isinstance(exc, LlmError) or exc.status_code >= 500:
        logger.warning("세션 시작 실패(code=%s): %s", exc.code, exc.message)
        return LlmError(
            exc.code, "대화를 시작하지 못했어요. 잠시 뒤 다시 해 주세요.", exc.status_code
        )
    return exc


async def _set_status(
    db: AsyncSession, session_id: str, status: SessionStatus, ended_at: datetime | None = None
) -> None:
    """상태를 바꾼다. 이미 끝난 세션은 건드리지 않는다(종료 요청과 턴이 겹쳐도 ended를 지킨다).

    ended_at: 끝난 시각(기본은 지금). 무발화 종료는 마지막 활동 시각을 넘긴다."""
    values: dict = {"status": status}
    if status is SessionStatus.ENDED:
        values["ended_at"] = ended_at or utcnow()
        # 끝낸 순간부터 정리 대기다. 추출 작업이 돌기 전에 서버가 꺼져도 다음 시작 때 다시 정리한다
        values["extract_status"] = ExtractStatus.PENDING
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


def _session_prompt(
    settings: Settings,
    profile: UserProfile,
    loaded: LoadedPersona,
    mode: ConversationMode,
    started_at: datetime,
    memory: MemoryContext,
) -> str:
    """세션의 시스템 프롬프트. 미리 띄우기와 open_llm이 같은 글자를 만들도록 여기서만 조립한다."""
    return build_system_prompt(
        loaded.persona,
        nickname=profile.nickname,
        mode=mode.value,
        now=started_at,
        timezone=settings.timezone,
        memory=memory,
    )


async def _memory(
    app: FastAPI, db: AsyncSession, profile: UserProfile, now: datetime
) -> MemoryContext:
    """기억 블록 입력(S2-05). 읽기만 하므로 바로 트랜잭션을 닫는다."""
    memory = await load_memory(db, app.state.settings, profile, now)
    await db.commit()
    return memory


async def _profile(app: FastAPI, db: AsyncSession) -> tuple[UserProfile, LoadedPersona]:
    profile, loaded = await profile_with_persona(db, app.state.settings)
    # 프로필·페르소나 행을 만들거나 고쳤으면 바로 커밋한다. 턴 내내 쓰기 잠금을 쥐면
    # 같은 시간에 MCP save_note 같은 다른 쓰기가 SQLite 잠금 대기 끝에 실패한다
    await db.commit()
    return profile, loaded


async def _get_cli(
    app: FastAPI, session_id: str, prompt: str, resume_id: str | None = None
) -> LlmSession:
    settings = app.state.settings
    runtime = app.state.runtimes.ensure(session_id)
    return await app.state.llm.get(
        session_id,
        system_prompt=prompt,
        model=settings.llm_chat_model,
        resume_id=resume_id,
        mcp_config=mcp_client_config(settings.internal_base_url, runtime),
    )


async def open_llm(
    app: FastAPI, db: AsyncSession, convo: ConversationSession
) -> tuple[LlmSession, LoadedPersona]:
    """대화의 CLI 세션과 프롬프트에 쓴 페르소나. CLI가 살아 있으면 재사용하고 없으면 --resume.

    프롬프트는 세션을 처음 열 때 만들어 세션 행에 고정한다. 그 뒤 프로필을 바꿔도 CLI를 다시 띄울
    때(유휴 정리·크래시·서버 재시작 후 --resume) 같은 프롬프트를 쓴다. 다음 커밋 때 함께 저장된다.
    """
    profile, loaded = await _profile(app, db)
    if convo.system_prompt is None:
        memory = await _memory(app, db, profile, convo.started_at)
        convo.system_prompt = _session_prompt(
            app.state.settings, profile, loaded, convo.mode, convo.started_at, memory
        )
        await db.commit()  # 이 턴이 오류로 끝나도 고정한 프롬프트는 남긴다
    session = await _get_cli(app, convo.id, convo.system_prompt, convo.cli_session_id)
    return session, loaded


@dataclass
class PreparedSession:
    """미리 띄운 CLI. 아직 DB 행이 없고, 시작할 때 이 ID·시작 시각으로 세션을 만든다."""

    id: str
    mode: ConversationMode
    started_at: datetime
    prompt: str
    expiry: asyncio.Task | None = None

    def matches(
        self,
        settings: Settings,
        mode: ConversationMode,
        profile: UserProfile,
        loaded: LoadedPersona,
        memory: MemoryContext,
    ) -> bool:
        """재사용 조건: 지금 프로필로 다시 만든 프롬프트가 글자까지 같다(호칭·페르소나 등 프롬프트에
        들어가는 값이 늘어나도 그대로 맞는다). 시작 시각은 준비 시각을 쓰므로, 준비된 지 TTL이
        지났거나 그 사이 현지 날짜·오전/오후가 바뀌었으면 쓰지 않는다(일지 날짜·인사 톤 보호)."""
        if self.mode is not mode:
            return False
        now_utc = utcnow()
        # 너무 오래된 준비분은 새 시각으로 갈아 끼운다(시작 시각 오차를 TTL 안으로 묶는다)
        if (now_utc - self.started_at).total_seconds() > settings.session_prepare_ttl_s:
            return False
        tz = ZoneInfo(settings.timezone)
        then, now = self.started_at.astimezone(tz), now_utc.astimezone(tz)
        if then.date() != now.date() or (then.hour < 12) != (now.hour < 12):
            return False
        # 기억(지난 일지·열린 노트)이 그사이 바뀌었어도 프롬프트가 달라져 새로 띄운다
        return self.prompt == _session_prompt(
            settings, profile, loaded, mode, self.started_at, memory
        )

    def schedule_expiry(self, app: FastAPI) -> None:
        if self.expiry is not None:
            self.expiry.cancel()
        self.expiry = asyncio.create_task(
            _expire_prepared(app, self, app.state.settings.session_prepare_ttl_s)
        )


async def _drop_prepared(app: FastAPI, prepared: PreparedSession) -> None:
    if prepared.expiry is not None and prepared.expiry is not asyncio.current_task():
        prepared.expiry.cancel()
    await teardown(app, prepared.id, None)


async def _expire_prepared(app: FastAPI, prepared: PreparedSession, ttl_s: float) -> None:
    await asyncio.sleep(ttl_s)
    async with app.state.prepare_lock:
        if app.state.prepared is prepared:
            app.state.prepared = None
            logger.info("미리 띄운 CLI 만료(session=%s)", prepared.id)
            await _drop_prepared(app, prepared)


async def prepare_session(app: FastAPI, db: AsyncSession, mode: ConversationMode) -> None:
    """다음 대화에 쓸 CLI를 미리 띄운다. 같은 조건으로 이미 준비돼 있으면 아무것도 하지 않는다."""
    try:
        await _prepare_session(app, db, mode)
    except AppError as exc:
        raise start_error(exc) from exc  # CLI 실행 경로 같은 내부 정보를 응답에 싣지 않는다


async def _prepare_session(app: FastAPI, db: AsyncSession, mode: ConversationMode) -> None:
    settings = app.state.settings
    async with app.state.prepare_lock:
        profile, loaded = await _profile(app, db)
        current: PreparedSession | None = app.state.prepared
        if current is not None:
            memory = await _memory(app, db, profile, current.started_at)
            if current.matches(settings, mode, profile, loaded, memory) and app.state.llm.is_alive(
                current.id
            ):
                current.schedule_expiry(app)  # 화면이 아직 열려 있다: 만료를 미룬다
                return
            app.state.prepared = None
            await _drop_prepared(app, current)
        started_at = utcnow()
        memory = await _memory(app, db, profile, started_at)
        prompt = _session_prompt(settings, profile, loaded, mode, started_at, memory)
        prepared = PreparedSession(new_id(), mode, started_at, prompt)
        try:
            await _get_cli(app, prepared.id, prompt)
        except BaseException:
            app.state.runtimes.discard(prepared.id)
            raise
        prepared.schedule_expiry(app)
        app.state.prepared = prepared
        logger.info("CLI 미리 띄움(session=%s)", prepared.id)


async def _take_prepared(
    app: FastAPI,
    db: AsyncSession,
    mode: ConversationMode,
    profile: UserProfile,
    loaded: LoadedPersona,
) -> PreparedSession | None:
    """같은 조건으로 준비된 CLI를 꺼낸다. 조건이 다르면 정리한다. 준비 중이면 끝나길 기다린다."""
    async with app.state.prepare_lock:
        prepared: PreparedSession | None = app.state.prepared
        if prepared is None:
            return None
        # 기억 조회(DB)는 준비분을 상태에서 빼기 전에 한다. 실패·취소돼도 준비분이 그대로 남아
        # 만료 타이머가 정리한다(빼고 나서 실패하면 런타임·MCP 토큰이 남는다)
        memory = await _memory(app, db, profile, prepared.started_at)
        app.state.prepared = None
        if prepared.expiry is not None:
            prepared.expiry.cancel()
        if prepared.matches(app.state.settings, mode, profile, loaded, memory):
            return prepared
        await _drop_prepared(app, prepared)
        return None


async def cancel_prepared(app: FastAPI) -> None:
    """앱 종료 때 만료 타이머를 멈추고 끝나길 기다린다. CLI는 매니저 종료가 닫는다."""
    prepared: PreparedSession | None = getattr(app.state, "prepared", None)
    if prepared is not None and prepared.expiry is not None:
        prepared.expiry.cancel()
        await asyncio.wait([prepared.expiry])


async def teardown(app: FastAPI, session_id: str, cli_session_id: str | None) -> None:
    """CLI를 닫은 뒤 런타임을 버린다(순서 주의: services/runtime.py). 기록 파일도 지운다."""
    await app.state.llm.close(session_id)
    app.state.runtimes.discard(session_id)
    if await asyncio.to_thread(delete_cli_session_file, cli_session_id):
        logger.info("CLI 대화 기록 삭제(session=%s)", session_id)


async def start_session(
    app: FastAPI, db: AsyncSession, mode: ConversationMode
) -> tuple[ConversationSession, Turn, LoadedPersona]:
    profile, loaded = await _profile(app, db)
    prepared = await _take_prepared(app, db, mode, profile, loaded)
    if prepared is not None:
        convo = ConversationSession(
            id=prepared.id,
            mode=mode,
            started_at=prepared.started_at,
            system_prompt=prepared.prompt,  # 미리 띄운 CLI가 쓰는 프롬프트 그대로
        )
    else:
        convo = ConversationSession(mode=mode)
    db.add(convo)
    try:
        await db.commit()
    except BaseException:
        if prepared is not None:  # 꺼낸 준비분(CLI·MCP 토큰)을 남기지 않는다
            with anyio.CancelScope(shield=True):
                await teardown(app, prepared.id, None)
        raise
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
            raise start_error(exc) from exc
        raise
    return convo, greeting, persona


async def _discard_new_session(
    app: FastAPI, db: AsyncSession, session_id: str, cli_session_id: str | None
) -> None:
    await db.rollback()
    await teardown(app, session_id, cli_session_id)
    await db.execute(delete(ConversationSession).where(ConversationSession.id == session_id))
    await db.commit()


async def end_session(
    app: FastAPI,
    db: AsyncSession,
    convo: ConversationSession,
    ended_at: datetime | None = None,
) -> None:
    """세션을 끝낸다. 이미 끝났으면 정리만 다시 한다(멱등). ended_at: 끝난 시각(기본은 지금)."""
    await _set_status(db, convo.id, SessionStatus.ENDED, ended_at)
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
    extract.ensure_extraction(app, convo.id)


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

    클라이언트가 끊기면 이 제너레이터가 닫히고 aclosing이 CLI 턴을 멈춘다. 이때 사용자 턴과
    보낸 문장까지의 답변(interrupted)이 남는다.
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
    try:
        with anyio.CancelScope(shield=True):
            convo = await db.get(ConversationSession, session_id)
            if convo is not None and convo.status is not SessionStatus.ENDED:
                last_seq = await db.scalar(
                    select(func.max(Turn.seq)).where(Turn.session_id == session_id)
                )
                seq = (last_seq if last_seq is not None else -1) + 1
                user_turn = Turn(session_id=session_id, seq=seq, role=TurnRole.USER, text=text)
                db.add(user_turn)
                await _set_status(db, session_id, SessionStatus.ACTIVE)  # 쉬기 중이면 이어 감
                await db.commit()
    except Exception:
        logger.exception("사용자 턴 저장 실패(session=%s)", session_id)
        yield _error(AppError("internal_error", "서버 내부 오류가 발생했습니다.", 500))
        return
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
        sent: list[str] = []  # 클라이언트에 보낸 문장(부분 답변으로 저장)
        reply_saved = False
        tool_names: dict[str, str] = {}
        finished: TurnFinished | None = None

        async def sentences(items: list[str]) -> list[bytes]:
            """문장을 먼저 커밋하고 보낸다. 클라이언트가 받은 문장은 서버가 죽어도 남는다(보내기
            직전에 끊기면 못 받은 문장이 하나 더 남을 수 있다). 끝나기 전에는 interrupted로
            둔다."""
            nonlocal index, reply_saved
            if not items:
                return []
            sent.extend(items)
            with anyio.CancelScope(shield=True):
                await _save_reply(
                    db, assistant_id, session_id, seq + 1, " ".join(sent), True, reply_saved
                )
                await db.commit()
            reply_saved = True
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
                    for chunk in await sentences(splitter.feed(event.text)):
                        yield chunk
                elif isinstance(event, ToolStarted):
                    # 도구 앞의 말("잠깐 찾아볼게요")은 기다리지 않고 바로 문장으로 보낸다
                    for chunk in await sentences(splitter.flush()):
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
        for chunk in await sentences(splitter.flush()):
            yield chunk

        if finished is None or (finished.is_error and not finished.interrupted):
            detail = finished.error_message if finished else "응답 없음"
            logger.warning("턴 실패(session=%s): %s", session_id, detail)
            error = LlmError("llm_error", "답변을 만들지 못했습니다.")
            yield _error(await _settle_after_error(app, db, runtime, session_id, error))
            return  # 보낸 문장은 끊긴 답변으로 남는다
        reply = "".join(parts).strip() or finished.text
        with anyio.CancelScope(shield=True):
            await _save_reply(
                db, assistant_id, session_id, seq + 1, reply, finished.interrupted, reply_saved
            )
            requested = runtime.pop_requested_status()
            if requested is not None:
                await _set_status(db, session_id, requested)
            await db.commit()
            await db.refresh(convo)  # 같은 시간에 종료 API가 바꿨을 수 있다
            if requested is SessionStatus.ENDED:
                await teardown(app, session_id, convo.cli_session_id)
                extract.ensure_extraction(app, session_id)
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
        yield _error(await _settle_after_error(app, db, runtime, session_id, exc))
    except Exception:
        logger.exception("턴 처리 중 예외(session=%s)", session_id)
        error = AppError("internal_error", "서버 내부 오류가 발생했습니다.", 500)
        yield _error(await _settle_after_error(app, db, runtime, session_id, error))
    finally:
        runtime.current_user_turn_id = None
        # 도구가 쉬기·끝내기를 요청한 뒤 턴이 오류나 연결 끊김으로 끝났어도 요청은 반영한다
        # (정상 종료면 위에서 이미 꺼냈다). 끊김으로 취소된 중에도 끝까지 처리한다
        leftover = runtime.pop_requested_status()
        if leftover is not None:
            with anyio.CancelScope(shield=True):
                await _apply_leftover_status(app, db, session_id, leftover)


async def _save_reply(
    db: AsyncSession,
    turn_id: str,
    session_id: str,
    seq: int,
    text: str,
    interrupted: bool,
    exists: bool,
) -> None:
    """assistant 턴을 만들거나 고친다(커밋은 부르는 쪽). 문장마다 불리므로 한 줄 쿼리로 끝낸다."""
    if exists:
        statement = (
            update(Turn)
            .where(Turn.id == turn_id)
            .values(text=text, interrupted=interrupted)
            .execution_options(synchronize_session=False)
        )
    else:
        statement = insert(Turn).values(
            id=turn_id,
            session_id=session_id,
            seq=seq,
            role=TurnRole.ASSISTANT,
            text=text,
            interrupted=interrupted,
        )
    await db.execute(statement)


async def _settle_after_error(
    app: FastAPI,
    db: AsyncSession,
    runtime: ConversationRuntime,
    session_id: str,
    error: AppError,
) -> AppError:
    """턴이 오류로 끝났을 때 도구가 남긴 쉬기·끝내기 요청을 반영하고 보낼 오류를 고른다.

    끝내기 요청이었거나 그사이 다른 곳(끝내기 API·무발화 감시)이 세션을 끝냈으면 세션이 끝났음을
    알려 클라이언트가 끝난 화면으로 가게 한다(CLI가 닫혀 난 오류를 "다시 말해 주세요"로
    보내지 않게).
    """
    leftover = runtime.pop_requested_status()
    with anyio.CancelScope(shield=True):
        if leftover is not None:
            await _apply_leftover_status(app, db, session_id, leftover)
        ended = leftover is SessionStatus.ENDED or await _is_ended(db, session_id)
    if ended:
        return AppError("session_ended", "대화를 마쳤어요.", 409)
    return error


async def _is_ended(db: AsyncSession, session_id: str) -> bool:
    """세션이 끝났는지 DB에서 다시 읽는다. rollback으로 세션의 객체(convo)를 만료시키므로
    이 뒤에서 그 속성을 읽지 않는다."""
    try:
        await db.rollback()
        status = await db.scalar(
            select(ConversationSession.status).where(ConversationSession.id == session_id)
        )
        await db.commit()
    except Exception:
        logger.exception("세션 상태 확인 실패(session=%s)", session_id)
        return False
    return status is SessionStatus.ENDED


async def _apply_leftover_status(
    app: FastAPI, db: AsyncSession, session_id: str, status: SessionStatus
) -> None:
    try:
        await db.rollback()
        await _set_status(db, session_id, status)
        await db.commit()
        if status is SessionStatus.ENDED:
            convo = await db.get(ConversationSession, session_id)
            await teardown(app, session_id, convo.cli_session_id if convo else None)
            extract.ensure_extraction(app, session_id)
        logger.info("턴이 끝나지 않았지만 상태 요청 반영(session=%s, %s)", session_id, status)
    except Exception:
        logger.exception("상태 요청 반영 실패(session=%s)", session_id)
