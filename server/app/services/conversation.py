"""대화 세션과 턴 처리(계획서 S1-08).

- 세션 시작: 프롬프트를 조립해 CLI를 열고, 숨은 첫 메시지로 받은 인사말을
  assistant 턴(seq 0)으로 저장한다.
- 턴: 사용자 턴을 먼저 저장하고 CLI 이벤트를 SSE 이벤트(app/api/events.py)로 바꿔 보낸다.
  답변은 문장을 보내기 전에 문장마다 커밋한다(계획서 S2-01). 끝나지 못한 답변(연결 끊김·오류·
  서버 강제 종료)은 보낸 문장까지 interrupted로 남는다.
- 종료: CLI를 닫고 대화 런타임(MCP 토큰)을 버린 뒤 CLI 대화 기록 파일을 지운다. 그다음 일지
  정리(추출, app/jobs/extract.py)를 백그라운드로 띄운다.
- 다시 열기(S3-26): 끝난 대화를 같은 세션으로 다시 연다. CLI 기록 파일은 지웠으므로 저장된
  전문을 새 프롬프트에 넣어 새 CLI를 띄우고, 재개 인사말을 다음 seq의 턴(greeting)으로 남긴다.

프롬프트는 세션의 시작 시각·모드와 현재 프로필로 만든다. CLI가 죽어 --resume으로 다시 띄울 때도
같은 값으로 다시 만든다.

미리 띄우기: 화면이 열리면 세션 ID와 시작 시각을 먼저 정해 CLI만 띄워 둔다(prepare_session).
시작할 때 같은 조건이면 그 ID·시각으로 세션 행을 만들어, 같은 프롬프트로 살아 있는 프로세스를
재사용한다. 프로세스 기동·첫 요청 준비 시간(약 1.4초)을 인사말 대기에서 뺀다.
"""

import asyncio
import contextlib
import logging
import os
import time
import weakref
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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
    TranscriptEvent,
    TurnEvent,
    VoiceNotice,
    encode_sse,
    public_tool_name,
)
from app.config import Settings
from app.db.models import (
    ConversationMode,
    ConversationSession,
    ExtractStatus,
    Note,
    SessionStatus,
    Turn,
    TurnLatency,
    TurnRole,
    UserProfile,
)
from app.db.types import new_id, utcnow
from app.errors import AppError
from app.jobs import extract
from app.jobs.audio import remove_session_audio
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
from app.persona.prompt import (
    SUMMARY_NOTES_MAX,
    MemoryContext,
    PastNote,
    PastSummary,
    PastTurn,
    build_system_prompt,
)
from app.persona.rules import (
    GREETING_INSTRUCTION,
    INTERRUPTED_HEARD,
    INTERRUPTED_NOTHING,
    REOPEN_GREETING_INSTRUCTION,
)
from app.persona.schema import VoiceStyle
from app.services.profile import profile_voice, profile_with_persona
from app.services.runtime import ConversationRuntime
from app.voice.audio import AudioFile
from app.voice.sentences import SentenceSplitter

logger = logging.getLogger("trailtalk.conversation")


class SessionNotFound(AppError):
    def __init__(self) -> None:
        super().__init__("session_not_found", "대화 세션을 찾을 수 없습니다.", 404)


class SessionEnded(AppError):
    def __init__(self) -> None:
        super().__init__("session_ended", "이미 끝난 대화입니다.", 409)


class SessionNotEnded(AppError):
    def __init__(self) -> None:
        super().__init__("session_not_ended", "아직 끝나지 않은 대화입니다.", 409)


@dataclass
class VoiceTiming:
    """음성 턴 지연 측정(S3-07). 시각은 요청 시작(time.monotonic) 기준 ms다."""

    started: float
    audio_bytes: int
    upload_ms: int
    stt_ms: int
    first_token_ms: int | None = None
    first_sentence_ms: int | None = None
    done_ms: int | None = None  # 마지막 이벤트를 보내기 직전(없으면 정리 때)

    def elapsed_ms(self) -> int:
        return round((time.monotonic() - self.started) * 1000)


class TurnNotFound(AppError):
    def __init__(self) -> None:
        super().__init__("turn_not_found", "답변을 찾을 수 없습니다.", 404)


class SessionActive(AppError):
    def __init__(self) -> None:
        super().__init__("session_active", "진행 중인 대화는 끝낸 뒤 지울 수 있어요.", 409)


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
    previous: list[PastTurn] | None = None,
    previous_summary: PastSummary | None = None,
) -> str:
    """세션의 시스템 프롬프트. 미리 띄우기와 open_llm이 같은 글자를 만들도록 여기서만 조립한다.
    previous: 다시 연 대화의 앞부분 기록(started_at에는 다시 연 시각을 넘긴다)."""
    return build_system_prompt(
        loaded.persona,
        nickname=profile.nickname,
        mode=mode.value,
        now=started_at,
        timezone=settings.timezone,
        memory=memory,
        previous=previous,
        previous_summary=previous_summary,
    )


async def _memory(
    app: FastAPI,
    db: AsyncSession,
    profile: UserProfile,
    now: datetime,
    exclude_session_id: str | None = None,
) -> MemoryContext:
    """기억 블록 입력(S2-05). 읽기만 하므로 바로 트랜잭션을 닫는다.
    exclude_session_id: 다시 여는 대화 자신의 요약은 기억에서 뺀다(전문을 따로 넣는다)."""
    memory = await load_memory(db, app.state.settings, profile, now, exclude_session_id)
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
) -> tuple[LlmSession, LoadedPersona, VoiceStyle]:
    """대화의 CLI 세션, 프롬프트에 쓴 페르소나, 합성할 보이스(설정 화면 값, S3-18).

    CLI가 살아 있으면 재사용하고 없으면 --resume. 보이스는 부를 때마다 프로필에서 읽으므로
    대화 중에 바꿔도 다음 답변부터 쓴다.

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
    return session, loaded, profile_voice(profile, loaded)


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
) -> tuple[ConversationSession, Turn, LoadedPersona, VoiceStyle]:
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
    seen: list[str] = []  # 인사말이 실패해도 띄운 CLI의 기록 파일을 지우도록 ID를 남긴다
    try:
        async with runtime.turn_lock:
            session, persona, voice = await open_llm(app, db, convo)
            text, cli_session_id = await _receive_greeting(
                session, GREETING_INSTRUCTION, session_id, seen
            )
            greeting = Turn(session_id=convo.id, seq=0, role=TurnRole.ASSISTANT, text=text)
            db.add(greeting)
            convo.cli_session_id = cli_session_id
            await db.commit()
    except BaseException as exc:
        # 인사말도 없는 빈 세션은 남기지 않는다(rollback으로 만료된 객체 대신 ID로 지운다).
        # 요청 취소·서버 종료 중에도 정리하도록 취소에서 보호한다
        try:
            with anyio.CancelScope(shield=True):  # 같은 태스크에서 끝까지 정리한다
                await _discard_new_session(app, db, session_id, cli_session_id or _last(seen))
        except Exception:
            logger.exception("시작 실패 정리 중 예외(session=%s)", session_id)
        if isinstance(exc, AppError):
            raise start_error(exc) from exc
        raise
    return convo, greeting, persona, voice


def _last(items: list[str]) -> str | None:
    return items[-1] if items else None


async def _receive_greeting(
    session: LlmSession, instruction: str, session_id: str, seen: list[str]
) -> tuple[str, str | None]:
    """숨은 안내를 보내 인사말을 받는다. (인사말, CLI 세션 ID)
    seen: 받은 CLI 세션 ID를 바로 적는다(실패해도 호출한 쪽이 기록 파일을 지울 수 있게)."""
    cli_session_id = None
    parts: list[str] = []
    finished = None
    async with aclosing(session.send(instruction)) as stream:
        async for event in stream:
            if isinstance(event, TurnStarted) and event.cli_session_id:
                cli_session_id = event.cli_session_id
                seen.append(cli_session_id)
            elif isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, TurnFinished):
                finished = event
    if finished is None or finished.is_error:
        detail = finished.error_message if finished else "응답 없음"
        logger.warning("인사말 실패(session=%s): %s", session_id, detail)
        raise LlmError("llm_error", "인사말을 받지 못했습니다.")
    return "".join(parts).strip() or finished.text, cli_session_id


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
    """세션을 끝낸다. 이미 끝났으면 정리만 다시 한다(멱등). ended_at: 끝난 시각(기본은 지금).

    정리(CLI 닫기·일지 정리 띄우기)는 턴 잠금을 쥐고 한다. 그 사이 다시 열기(S3-26)가 끼어들어
    막 띄운 CLI를 닫지 않게, 잠금을 얻은 뒤 상태를 다시 읽어 다시 열렸으면 그대로 둔다.
    """
    if convo.status is not SessionStatus.ENDED:
        # 예전 형식 다시 정리 요청이 남아 있으면 이번 정리에서 새 노트를 뽑지 않게 된다
        app.state.reformat_requests.discard(convo.id)
    await _set_status(db, convo.id, SessionStatus.ENDED, ended_at)
    await db.commit()
    runtime = app.state.runtimes.ensure(convo.id)
    await app.state.llm.close(convo.id)  # 진행 중인 턴이 있으면 여기서 끊긴다
    locked = False
    try:
        # 턴 스트림이 정리를 마칠 때까지 기다린다(CLI를 닫았으니 보통 바로 끝난다)
        async with asyncio.timeout(_END_WAIT_S):
            await runtime.turn_lock.acquire()
        locked = True
    except TimeoutError:
        logger.warning("종료 중 턴 정리 대기 시간 초과(session=%s)", convo.id)
    try:
        await db.refresh(convo)  # 턴 중에 바뀐 cli_session_id·상태를 다시 읽는다
        if convo.status is not SessionStatus.ENDED:
            return  # 그사이 다시 열렸다: 새 CLI와 런타임은 다시 연 대화의 것이다
        await teardown(app, convo.id, convo.cli_session_id)
        extract.ensure_extraction(app, convo.id)
    finally:
        if locked:
            runtime.turn_lock.release()


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


async def last_reply(db: AsyncSession, session_id: str, max_chars: int = 200) -> str | None:
    """세션의 마지막 캐릭터 답변(뒤에서 max_chars자). 음성 인식에 문맥 힌트로 준다."""
    text = await db.scalar(
        select(Turn.text)
        .where(Turn.session_id == session_id, Turn.role == TurnRole.ASSISTANT)
        .order_by(Turn.seq.desc())
        .limit(1)
    )
    return text[-max_chars:] if text else None


async def stream_turn(
    app: FastAPI,
    session_id: str,
    text: str,
    *,
    from_voice: bool = False,
    audio: AudioFile | None = None,
    timing: VoiceTiming | None = None,
) -> AsyncIterator[bytes]:
    """사용자 메시지 한 턴을 처리하며 SSE 바이트를 낸다.

    from_voice: 음성 업로드의 인식 결과다. turn 바로 앞에 transcript 이벤트로 알린다.
    audio: 보관할 녹음(프로필 keep_audio가 켜진 음성 턴, S3-05). 사용자 턴에 붙여 저장한다.
    timing: 음성 턴의 지연 측정(S3-07). 단계별 시각을 turn_latency에 남긴다.

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
            turn = _run_turn(app, db, runtime, session_id, text, from_voice, audio, timing)
            async with aclosing(turn) as chunks:
                async for chunk in chunks:
                    yield chunk
        finally:
            # 연결이 끊겨 취소된 중에도 커넥션을 온전히 돌려준다(닫기가 다시 취소되면 망가진
            # 커넥션이 풀에 남아 다음 요청이 실패한다)
            with anyio.CancelScope(shield=True):
                await db.close()


# 캐릭터가 아무 말 없이 시작하면 검색 안내 음성을 대신 들려줄 도구
_SEARCH_TOOLS = {"web_search", "web_fetch", "search_conversations"}  # 찾는 동안 안내 음성


async def _run_turn(
    app: FastAPI,
    db: AsyncSession,
    runtime: ConversationRuntime,
    session_id: str,
    text: str,
    from_voice: bool,
    audio: AudioFile | None = None,
    timing: VoiceTiming | None = None,
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
    user_turn_id = user_turn.id  # 아래 커밋·롤백 뒤에도 쓰도록 미리 꺼내 둔다
    if audio is not None:
        await _keep_audio(app, db, session_id, user_turn_id, audio)

    assistant_id = new_id()
    if timing is not None:
        await _start_latency(db, session_id, assistant_id, timing)
    if from_voice:
        yield encode_sse(TranscriptEvent(text=text))
    yield encode_sse(TurnEvent(turn_id=assistant_id))
    runtime.requested_status = None
    runtime.current_user_turn_id = user_turn_id
    # 합성 중이거나 보낼 차례를 기다리는 문장(순서대로). 분할기가 한 번에 내놓은 문장들의
    # 소리는 동시에 만들고, 보낼 때는 순서를 지킨다
    pending: list[tuple[str, asyncio.Task[str | None] | None]] = []
    # 끼어들기 API가 진행 중인 턴으로 알아보게 바로 표시한다(CLI 세션은 연 뒤에 채운다)
    runtime.active_turn = (assistant_id, None)
    try:
        with anyio.CancelScope(shield=True):
            await db.refresh(convo)  # 그사이 종료 API가 끝냈으면 CLI를 다시 띄우지 않는다
            if convo.status is SessionStatus.ENDED:
                raise SessionEnded()
            session, loaded, profile_style = await open_llm(app, db, convo)
        runtime.active_turn = (assistant_id, session)  # 끼어들기 API가 인터럽트를 보낸다
        # 음성 세션이면 문장마다 소리를 만든다(텍스트로 보낸 턴도 마찬가지)
        voice = profile_style if convo.mode is ConversationMode.VOICE else None
        speech = app.state.speech
        splitter = SentenceSplitter()
        index = 0
        parts: list[str] = []
        sent: list[str] = []  # 클라이언트에 보낸 문장(부분 답변으로 저장)
        runtime.remember_sentences(assistant_id, sent)  # 들려준 문장까지 자를 때 쓴다(S3-04)
        reply_saved = False
        tool_names: dict[str, str] = {}
        finished: TurnFinished | None = None
        sources: dict[str, dict] = {}  # 이번 답변이 본 출처(URL → {title, url}), 일지 인용용(S3-23)

        def queue(items: list[str], with_audio: bool = True) -> None:
            for item in items:
                synth = voice and with_audio
                task = asyncio.create_task(speech.synthesize(app, item, voice)) if synth else None
                pending.append((item, task))

        def head_ready() -> bool:
            """맨 앞 문장을 기다리지 않고 바로 보낼 수 있는가(소리가 없거나 합성이 끝남)."""
            return bool(pending) and (pending[0][1] is None or pending[0][1].done())

        def drop_audio() -> None:
            """남은 문장의 합성을 그만둔다(끊긴 턴: 들을 사람이 없다). 글은 그대로 보낸다."""
            for i, (item, task) in enumerate(pending):
                if task is not None and not task.done():  # 이미 만든 소리는 그대로 보낸다
                    task.cancel()
                    pending[i] = (item, None)

        async def next_sentence() -> bytes:
            """맨 앞 문장의 소리를 기다린 뒤 먼저 커밋하고 보낸다. 클라이언트가 받은 문장은 서버가
            죽어도 남는다(보내기 직전에 끊기면 못 받은 문장이 하나 더 남을 수 있다). 끝나기 전에는
            interrupted로 둔다."""
            nonlocal index, reply_saved, spoken
            item, task = pending[0]
            audio = await task if task is not None else None
            spoken = spoken or audio is not None
            pending.pop(0)
            sent.append(item)
            with anyio.CancelScope(shield=True):
                await _save_reply(
                    db,
                    assistant_id,
                    session_id,
                    seq + 1,
                    " ".join(sent),
                    True,
                    reply_saved,
                    list(sources.values()),
                )
                await db.commit()
            reply_saved = True
            chunk = encode_sse(SentenceEvent(index=index, text=item, audio=audio))
            index += 1
            if timing is not None and timing.first_sentence_ms is None:
                timing.first_sentence_ms = timing.elapsed_ms()
            return chunk

        notice_sent = False
        spoken = False  # 이번 턴에 소리 있는 문장을 보냈는가(검색 안내 조건)

        # 직전 답변을 끊었으면 사용자가 어디까지 들었는지 CLI에만 알린다(기록에는 남기지 않는다)
        cli_text, runtime.heard_note = (runtime.heard_note or "") + text, None
        # CLI 오류(크래시·시간 초과)로 끝나도 받은 글은 아래에서 마저 보내고 저장한 뒤 다시 던진다
        stream_error: LlmError | None = None
        try:
            async with aclosing(session.send(cli_text)) as stream:
                async for event in stream:
                    if isinstance(event, TurnStarted):
                        if event.cli_session_id and event.cli_session_id != convo.cli_session_id:
                            convo.cli_session_id = event.cli_session_id
                            with anyio.CancelScope(shield=True):
                                await db.commit()
                    elif isinstance(event, TextDelta):
                        # 합성을 띄우기만 하고 CLI를 계속 읽는다. 소리가 다 된 문장은 아래에서
                        # 보낸다(합성을 기다리는 시간이 턴 시간 제한에 더해지지 않게)
                        if timing is not None and timing.first_token_ms is None:
                            timing.first_token_ms = timing.elapsed_ms()
                        parts.append(event.text)
                        queue(splitter.feed(event.text))
                    elif isinstance(event, ToolStarted):
                        # 도구 앞의 말("잠깐 찾아볼게요")은 기다리지 않고 바로 문장으로 보낸다
                        queue(splitter.flush())
                        while pending:
                            yield await next_sentence()
                        if parts and not parts[-1][-1:].isspace():
                            parts.append("\n\n")
                        name = public_tool_name(event.name)
                        tool_names[event.tool_use_id] = name
                        notice = None
                        if voice and name in _SEARCH_TOOLS and not spoken and not notice_sent:
                            # 아무 말 없이 검색을 시작했다: 기다리는 동안의 침묵을 안내로 메운다
                            notice_sent = True
                            notice = VoiceNotice(
                                text=voice.search_notice,
                                audio=await speech.cached(app, voice.search_notice, voice),
                            )
                        yield encode_sse(
                            ToolEvent(
                                phase="start",
                                tool_use_id=event.tool_use_id,
                                name=name,
                                notice=notice,
                            )
                        )
                    elif isinstance(event, ToolCalled):
                        while pending:  # 도구 이벤트보다 앞선 문장을 먼저 보낸다(순서 유지)
                            yield await next_sentence()
                        name = tool_names.setdefault(
                            event.tool_use_id, public_tool_name(event.name)
                        )
                        yield encode_sse(
                            ToolEvent(
                                phase="call",
                                tool_use_id=event.tool_use_id,
                                name=name,
                                input=event.input,
                            )
                        )
                    elif isinstance(event, ToolFinished):
                        _collect_sources(sources, event.summary)
                        while pending:
                            yield await next_sentence()
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
                    while head_ready():
                        yield await next_sentence()
        except LlmError as exc:
            stream_error = exc
        stopped = stream_error is not None or finished is None or finished.interrupted
        queue(splitter.flush(), with_audio=not stopped)
        if stopped:
            drop_audio()  # 끝내기 API·끊김·CLI 오류로 멈춘 턴: 남은 문장은 글만 저장하고 보낸다
        while pending:
            yield await next_sentence()
        if stream_error is not None:
            raise stream_error  # 아래 except AppError가 상태 요청 반영·오류 이벤트를 맡는다

        if finished is None or (finished.is_error and not finished.interrupted):
            detail = finished.error_message if finished else "응답 없음"
            logger.warning("턴 실패(session=%s): %s", session_id, detail)
            error = LlmError("llm_error", "답변을 만들지 못했습니다.")
            yield _error(await _settle_after_error(app, db, runtime, session_id, error))
            return  # 보낸 문장은 끊긴 답변으로 남는다
        reply = "".join(parts).strip() or finished.text
        with anyio.CancelScope(shield=True):
            await _save_reply(
                db,
                assistant_id,
                session_id,
                seq + 1,
                reply,
                finished.interrupted,
                reply_saved,
                list(sources.values()),
            )
            requested = runtime.pop_requested_status()
            if requested is not None:
                await _set_status(db, session_id, requested)
            await db.commit()
            await db.refresh(convo)  # 같은 시간에 종료 API가 바꿨을 수 있다
            if requested is SessionStatus.ENDED:
                await teardown(app, session_id, convo.cli_session_id)
                extract.ensure_extraction(app, session_id)
        if timing is not None:
            timing.done_ms = timing.elapsed_ms()  # 클라이언트가 마지막 이벤트를 읽는 시간은 뺀다
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
        # 끊김·오류로 끝났으면 아직 합성 중인 소리는 버린다
        for _, task in pending:
            if task is not None:
                task.cancel()
        runtime.current_user_turn_id = None
        runtime.active_turn = None
        if timing is not None:
            await _finish_latency(db, assistant_id, timing)
        # 도구가 쉬기·끝내기를 요청한 뒤 턴이 오류나 연결 끊김으로 끝났어도 요청은 반영한다
        # (정상 종료면 위에서 이미 꺼냈다). 끊김으로 취소된 중에도 끝까지 처리한다
        leftover = runtime.pop_requested_status()
        if leftover is not None:
            with anyio.CancelScope(shield=True):
                await _apply_leftover_status(app, db, session_id, leftover)


_CANCEL_WAIT_S = 10.0
_HEARD_MAX_CHARS = 100  # 안내에 넣는 마지막으로 들은 문장의 길이


async def cancel_turn(
    app: FastAPI, db: AsyncSession, session_id: str, turn_id: str, last_played: int
) -> None:
    """끼어들기(S3-04): 답변을 멈추고 들려준 문장(last_played번까지)만 남긴다. 멱등이다.

    진행 중인 턴이면 CLI에 인터럽트를 보내고 턴이 끝나기를 기다린 뒤 자른다. 끝난 턴도 자른다.
    인사말(seq 0, 다시 연 대화의 인사말)은 문장 번호 없이 재생돼 클라이언트가 늘 -1을 보내므로
    자르지 않는다.
    자르기와 다음 턴 안내는 턴 락 안에서 한다. 그래야 바로 뒤 턴이 안내를 놓치지 않고, 끝내기
    API(같은 락을 기다린다)의 일지 정리가 자르기 전 원문을 읽지 않는다.
    """
    await get_session(db, session_id)
    runtime = app.state.runtimes.get(session_id)
    if runtime is None:
        # 서버 재시작 뒤: 진행 중인 턴도 메모리 기록도 없다. 저장된 답변만 자른다(안내는 CLI가 새로
        # 열리므로 생략)
        await _trim_reply(db, session_id, turn_id, last_played, None)
        return
    running = runtime.active_turn is not None and runtime.active_turn[0] == turn_id
    if running and runtime.active_turn[1] is not None:  # CLI를 여는 중이면 인터럽트할 것이 없다
        try:
            await runtime.active_turn[1].interrupt()
        except Exception:
            # 이미 끝나는 중이거나 프로세스가 없다. 턴이 끝나기를 기다린 뒤 자른다
            logger.warning("끼어들기 인터럽트 실패(session=%s)", session_id, exc_info=True)
    try:
        async with asyncio.timeout(_CANCEL_WAIT_S):
            await runtime.turn_lock.acquire()
    except TimeoutError:
        if running:
            # 아직 끝나지 않은 턴을 지금 자르면 그 턴이 끝날 때 전체 답변으로 덮어쓴다
            logger.warning(
                "끼어들기 중 턴 정리 대기 시간 초과, 자르지 않음(session=%s)", session_id
            )
            return
        # 다른(다음) 턴이 진행 중이다: 끝난 이 답변만 자르고 안내는 붙이지 않는다
        await _trim_reply(db, session_id, turn_id, last_played, None)
        return
    try:
        await _trim_reply(db, session_id, turn_id, last_played, runtime)
    finally:
        runtime.turn_lock.release()


async def _trim_reply(
    db: AsyncSession,
    session_id: str,
    turn_id: str,
    last_played: int,
    runtime: ConversationRuntime | None,
) -> None:
    """답변 기록을 last_played번 문장까지로 자른다. runtime을 주면 다음 턴 안내도 남긴다."""
    turn = await db.scalar(
        select(Turn).where(Turn.id == turn_id).execution_options(populate_existing=True)
    )
    if turn is None or turn.session_id != session_id or turn.role is not TurnRole.ASSISTANT:
        # 첫 문장 전에 연결이 끊겨 답변 기록이 없는 턴도 여기에 온다(클라이언트는 무시한다)
        raise TurnNotFound()
    if turn.seq == 0 or turn.greeting:
        return
    sentences = runtime.reply_sentences.get(turn_id) if runtime is not None else None
    if sentences is None:
        # 기억이 없으면(서버 재시작, 최근 답변이 아님) 저장된 답변을 다시 나눈다. 스트리밍 때는
        # 도구 앞에서 끊어 짧은 조각도 한 문장이 되므로 번호가 조금 어긋날 수 있다(알려진 한계)
        splitter = SentenceSplitter()
        sentences = splitter.feed(turn.text) + splitter.flush()
    keep = last_played + 1
    if keep >= len(sentences):
        return  # 다 들었다
    heard = sentences[:keep]
    text = " ".join(heard)
    if turn.interrupted and turn.text == text:
        return  # 이미 잘랐다(같은 요청을 다시 받았다): 안내도 다시 붙이지 않는다
    await db.execute(
        update(Turn)
        .where(Turn.id == turn_id)
        .values(text=text, interrupted=True)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    latest = await db.scalar(
        select(func.max(Turn.seq)).where(
            Turn.session_id == session_id, Turn.role == TurnRole.ASSISTANT
        )
    )
    if runtime is not None and latest == turn.seq:  # 직전 답변일 때만 다음 턴에 알린다
        runtime.heard_note = _heard_note(heard)


def _heard_note(heard: list[str]) -> str:
    if not heard:
        return INTERRUPTED_NOTHING
    # 앱 안내의 틀(괄호·따옴표)을 깨지 않게 인용할 문장의 따옴표·괄호를 정리한다(검색 결과를 옮긴
    # 문장일 수도 있다)
    last = heard[-1][-_HEARD_MAX_CHARS:]
    last = last.replace('"', "'").translate(str.maketrans("", "", "()[]{}"))
    return INTERRUPTED_HEARD.format(heard=last)


async def _start_latency(
    db: AsyncSession, session_id: str, turn_id: str, timing: VoiceTiming
) -> None:
    """측정 행을 턴 시작 때 만든다(웹 보고가 턴이 끝나기 전에 올 수 있다). 실패해도 계속한다."""
    try:
        with anyio.CancelScope(shield=True):
            db.add(
                TurnLatency(
                    turn_id=turn_id,
                    session_id=session_id,
                    audio_bytes=timing.audio_bytes,
                    upload_ms=timing.upload_ms,
                    stt_ms=timing.stt_ms,
                )
            )
            await db.commit()
    except Exception:
        logger.exception("지연 측정 기록 실패(session=%s)", session_id)
        with anyio.CancelScope(shield=True), contextlib.suppress(Exception):
            await db.rollback()


async def _finish_latency(db: AsyncSession, turn_id: str, timing: VoiceTiming) -> None:
    """첫 글자·첫 문장·끝 시각을 채운다(정상·오류·끊긴 턴 모두). 실패해도 로그만 남긴다."""
    done_ms = timing.done_ms if timing.done_ms is not None else timing.elapsed_ms()
    try:
        with anyio.CancelScope(shield=True):
            await db.execute(
                update(TurnLatency)
                .where(TurnLatency.turn_id == turn_id)
                .values(
                    first_token_ms=timing.first_token_ms,
                    first_sentence_ms=timing.first_sentence_ms,
                    done_ms=done_ms,
                )
                .execution_options(synchronize_session=False)
            )
            await db.commit()
    except Exception:
        logger.exception("지연 측정 기록 실패(turn=%s)", turn_id)
        with anyio.CancelScope(shield=True), contextlib.suppress(Exception):
            await db.rollback()


async def record_offline_turn(app: FastAPI, db: AsyncSession, session_id: str, text: str) -> None:
    """오프라인 큐의 말을 대답 없이 사용자 턴으로만 남긴다(S3-12). 끝난 대화도 받는다.

    대답할 수 없는 경우(서버가 이미 대화를 끝냄, 페이지를 새로 열어 대화가 사라짐)의 기록
    보존용이다. 끝난 대화면 일지를 다시 정리한다(새 말에서 나온 노트만 더해진다: 기존 노트와
    겹치면 거른다). 같은 대화의 기록·턴은 세션별 잠금으로 줄을 세워 순번(seq)이 겹치지 않게 한다.
    """
    await get_session(db, session_id)
    runtime = app.state.runtimes.get(session_id)
    if runtime is not None and runtime.turn_lock.locked():
        raise TurnBusy()
    # 런타임이 없으면(끝난 대화·서버 재시작) 기록끼리만 줄을 세운다
    lock = runtime.turn_lock if runtime is not None else _record_lock(app, session_id)
    async with lock:
        last_seq = await db.scalar(select(func.max(Turn.seq)).where(Turn.session_id == session_id))
        seq = (last_seq if last_seq is not None else -1) + 1
        db.add(Turn(session_id=session_id, seq=seq, role=TurnRole.USER, text=text))
        # 끝남 여부는 커밋 직전에 읽는다(그사이 끝내기 API가 끝냈을 수 있다)
        status = await db.scalar(
            select(ConversationSession.status).where(ConversationSession.id == session_id)
        )
        ended = status is SessionStatus.ENDED
        if ended:
            await db.execute(
                update(ConversationSession)
                .where(ConversationSession.id == session_id)
                .values(extract_status=ExtractStatus.PENDING)
                .execution_options(synchronize_session=False)
            )
        await db.commit()
    if ended:
        extract.ensure_extraction(app, session_id)


_DELETE_EXTRACT_WAIT_S = 5.0
_DELETE_LOCK_WAIT_S = 5.0


async def delete_session(app: FastAPI, db: AsyncSession, session_id: str) -> None:
    """대화를 지운다(전문·노트·지연 기록은 외래 키 CASCADE, 보관한 녹음은 폴더째). 진행 중이면 거절.

    턴·오프라인 기록과 같은 잠금을 쥔 채 지워, 쉬는 중인 대화에 막 시작한 턴이 CLI를 다시 띄우거나
    지운 대화에 턴을 쓰지 않게 한다. 돌던 일지 정리는 멈추고 그 결과 쓰기가 끝난 뒤 지운다.
    """
    convo = await get_session(db, session_id)
    if convo.status is SessionStatus.ACTIVE:
        raise SessionActive()
    # 런타임이 없어도(서버 재시작 뒤 쉬는 대화) 만들어서 그 잠금을 쥔다. 턴도 같은 런타임의 잠금을
    # 쓰므로 지우는 동안 시작한 턴은 거절되고(TurnBusy) 지운 뒤에는 SessionNotFound가 된다.
    # 답변 중이면 잠깐 기다렸다가 그래도 안 끝나면 거절한다(같은 대화를 동시에 지우면 뒤 요청은 404)
    runtime = app.state.runtimes.ensure(session_id)
    try:
        async with asyncio.timeout(_DELETE_LOCK_WAIT_S):
            await runtime.turn_lock.acquire()
    except TimeoutError:
        raise TurnBusy() from None
    try:
        # 잠금을 기다리는 사이 바뀐 상태를 다시 읽는다(같은 대화를 동시에 지웠으면 404)
        convo = await db.scalar(
            select(ConversationSession)
            .where(ConversationSession.id == session_id)
            .execution_options(populate_existing=True)
        )
        if convo is None:
            app.state.runtimes.discard(session_id)  # 방금 만든 런타임을 남기지 않는다
            raise SessionNotFound()
        if convo.status is SessionStatus.ACTIVE:  # 그사이 턴이 시작됐다(런타임은 그 턴이 쓴다)
            raise SessionActive()
        cli_session_id = convo.cli_session_id
        await extract.cancel_extraction(app, session_id, _DELETE_EXTRACT_WAIT_S)
        await db.delete(convo)
        await db.commit()
        # 행을 먼저 지운 뒤 정리한다(그 뒤 오는 턴은 SessionNotFound라 CLI를 다시 띄우지 않는다).
        # 끝난 대화도 부른다(멱등): 끝내기가 정리를 마치기 전에 지워도 CLI·기록 파일이 남지 않게
        await teardown(app, session_id, cli_session_id)
    finally:
        runtime.turn_lock.release()
    try:
        await asyncio.to_thread(remove_session_audio, app.state.settings.audio_dir, session_id)
    except OSError:
        logger.warning("지운 대화의 녹음 삭제 실패(session=%s)", session_id, exc_info=True)


async def reopen_session(
    app: FastAPI, db: AsyncSession, session_id: str, mode: ConversationMode
) -> tuple[ConversationSession, Turn, list[Turn], LoadedPersona, VoiceStyle]:
    """끝난 대화를 같은 세션으로 다시 연다(S3-26). (세션, 재개 인사말, 전체 전문, 페르소나, 보이스)

    지우기와 같은 턴 잠금을 쥔 채 상태를 다시 읽어, 지우는 중인 대화를 열거나 연 대화를 지우지
    않게 한다. 돌던 일지 정리는 멈추고(다시 끝내면 처음부터 다시 정리한다) 정리 상태를 비운다.
    CLI 기록 파일은 끝낼 때 지웠으므로 --resume 없이 전문을 넣은 새 프롬프트로 새 CLI를 띄운다.
    인사말을 받지 못하면 끝난 상태로 되돌린다. 일지 날짜(started_at)는 그대로다.
    """
    await get_session(db, session_id)  # 없는 대화에 런타임을 만들지 않는다
    runtime = app.state.runtimes.ensure(session_id)
    try:
        async with asyncio.timeout(_DELETE_LOCK_WAIT_S):
            await runtime.turn_lock.acquire()
    except TimeoutError:
        raise TurnBusy() from None
    backup: dict | None = None
    stopped = False  # 돌던 정리를 멈췄다(실패하면 다시 띄운다)
    seen: list[str] = []
    try:
        convo = await db.scalar(
            select(ConversationSession)
            .where(ConversationSession.id == session_id)
            .execution_options(populate_existing=True)
        )
        if convo is None:  # 잠금을 기다리는 사이 지워졌다
            app.state.runtimes.discard(session_id)
            raise SessionNotFound()
        if convo.status is not SessionStatus.ENDED:
            raise SessionNotEnded()  # 진행 중인 대화의 런타임이라 버리지 않는다
        stopped = True
        await extract.cancel_extraction(app, session_id, _DELETE_EXTRACT_WAIT_S)
        app.state.reformat_requests.discard(session_id)
        await db.refresh(convo)  # 멈춘 정리가 쓴 값을 다시 읽는다
        backup = {
            "status": SessionStatus.ENDED,
            "mode": convo.mode,
            "ended_at": convo.ended_at,
            "extract_status": convo.extract_status,
            "cli_session_id": convo.cli_session_id,
            "system_prompt": convo.system_prompt,
            "reopened_at": convo.reopened_at,
        }
        now = utcnow()
        profile, loaded = await _profile(app, db)
        memory = await _memory(app, db, profile, now, exclude_session_id=session_id)
        rows = await db.scalars(
            select(Turn).where(Turn.session_id == session_id).order_by(Turn.seq)
        )
        previous = [PastTurn(t.role.value, t.text, t.interrupted) for t in rows if t.text.strip()]
        summary = await _past_summary(db, convo)
        # 상태와 프롬프트를 한 번에 바꾼다(그 사이 서버가 꺼져도 전문 없는 프롬프트가 남지 않게)
        convo.status = SessionStatus.ACTIVE
        convo.mode = mode
        convo.ended_at = None
        convo.extract_status = None
        convo.cli_session_id = None
        convo.reopened_at = now
        convo.system_prompt = _session_prompt(
            app.state.settings, profile, loaded, mode, now, memory, previous, summary
        )
        await db.commit()
        session, persona, voice = await open_llm(app, db, convo)
        text, cli_session_id = await _receive_greeting(
            session, REOPEN_GREETING_INSTRUCTION, session_id, seen
        )
        last_seq = await db.scalar(select(func.max(Turn.seq)).where(Turn.session_id == session_id))
        greeting = Turn(
            session_id=session_id,
            seq=(last_seq if last_seq is not None else -1) + 1,
            role=TurnRole.ASSISTANT,
            text=text,
            greeting=True,
        )
        db.add(greeting)
        convo.cli_session_id = cli_session_id
        await db.commit()
        await db.refresh(convo)  # 그사이 끝내기가 끼어들었으면 실제 상태를 돌려준다
        turns = list(
            await db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.seq))
        )
    except BaseException as exc:
        # 요청 취소·서버 종료 중에도 끝난 상태로 되돌리도록 취소에서 보호한다
        try:
            with anyio.CancelScope(shield=True):
                if backup is not None:
                    await _restore_ended(app, db, session_id, backup, _last(seen))
                elif stopped:  # 상태를 바꾸기 전에 실패했다: 멈춘 정리만 다시 띄운다
                    extract.ensure_extraction(app, session_id)
        except Exception:
            logger.exception("다시 열기 실패 복구 중 예외(session=%s)", session_id)
        if isinstance(exc, AppError):
            raise start_error(exc) from exc
        raise
    finally:
        runtime.turn_lock.release()
    return convo, greeting, turns, persona, voice


async def _past_summary(db: AsyncSession, convo: ConversationSession) -> PastSummary | None:
    """다시 여는 대화의 일지 정리(S3-27). 정리를 마친(DONE) 일지만 쓴다: 그때는 끝낸 시점의 전문
    (아주 긴 대화는 정리 한도인 뒤쪽 10만 자)으로 정리했다. 정리 뒤 턴이 붙으면(오프라인 기록) 다시
    PENDING이 된다. 정리 중·실패·정리 전이면 None(전문을 그대로 넣는다)."""
    if convo.extract_status is not ExtractStatus.DONE or not convo.summary:
        return None
    rows = await db.execute(  # 최근 노트부터 고른다(다시 열 때마다 새 노트가 빠지지 않게)
        select(Note.kind, Note.content, Note.done)
        .where(Note.session_id == convo.id)
        .order_by(Note.created_at.desc(), Note.id.desc())
        .limit(SUMMARY_NOTES_MAX)
    )
    notes = [PastNote(extract.SAVED_LABELS[kind], content, done) for kind, content, done in rows][
        ::-1
    ]
    return PastSummary(
        title=convo.title,
        summary=[line for line in convo.summary.splitlines() if line.strip()],  # 줄바꿈으로 이은 글
        checks=list(convo.checks or []),
        notes=notes,
    )


async def _restore_ended(
    app: FastAPI, db: AsyncSession, session_id: str, backup: dict, cli_session_id: str | None
) -> None:
    """다시 열기에 실패하면 끝난 상태와 정리 상태를 되돌리고 새로 띄운 CLI를 정리한다."""
    await db.rollback()
    await teardown(app, session_id, cli_session_id)
    await db.execute(
        update(ConversationSession)
        .where(ConversationSession.id == session_id)
        .values(**backup)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    if backup["extract_status"] is ExtractStatus.PENDING:  # 멈췄던 정리를 다시 띄운다
        extract.ensure_extraction(app, session_id)


def _record_lock(app: FastAPI, session_id: str) -> asyncio.Lock:
    # 약한 참조 사전이라 기다리거나 쥔 곳이 없어진 잠금은 저절로 사라진다
    locks: weakref.WeakValueDictionary[str, asyncio.Lock] = app.state.record_locks
    lock = locks.get(session_id)
    if lock is None:
        lock = locks[session_id] = asyncio.Lock()
    return lock


async def report_latency(
    db: AsyncSession,
    session_id: str,
    turn_id: str,
    speech_to_request_ms: int,
    request_to_playback_ms: int,
    first_sound_notice: bool = False,
) -> None:
    """웹이 잰 말 끝 → 요청, 요청 → 첫 소리를 남긴다(다시 보내면 덮어쓴다)."""
    await get_session(db, session_id)
    row = await db.get(TurnLatency, turn_id)
    if row is None or row.session_id != session_id:
        raise TurnNotFound()
    row.speech_to_request_ms = speech_to_request_ms
    row.request_to_playback_ms = request_to_playback_ms
    row.first_sound_notice = first_sound_notice
    await db.commit()


def _write_audio(path: Path, data: bytes) -> None:
    """본인만 읽을 수 있게(폴더 0700, 파일 0600) 쓴다. 녹음은 민감한 개인 정보다."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(data)


async def _set_audio_path(db: AsyncSession, turn_id: str, relative: str) -> None:
    await db.execute(
        update(Turn)
        .where(Turn.id == turn_id)
        .values(audio_path=relative)
        .execution_options(synchronize_session=False)
    )
    await db.commit()


async def _keep_audio(
    app: FastAPI, db: AsyncSession, session_id: str, turn_id: str, audio: AudioFile
) -> None:
    """녹음을 audio_dir/<세션>/<사용자 턴>.<확장자>에 두고 경로(상대)를 사용자 턴에 남긴다.

    부가 기능이라 실패해도 턴은 계속한다. 연결이 끊겨도 쓰기와 커밋은 끝까지 한다. 경로를 남기지
    못하면 쓴 파일을 지운다(DB에 없는 파일은 보관 기간 정리에서도 빠져 영구히 남는다).
    """
    relative = Path(session_id) / f"{turn_id}{Path(audio.filename).suffix or '.webm'}"
    path = app.state.settings.audio_dir / relative
    with anyio.CancelScope(shield=True):
        try:
            await asyncio.to_thread(_write_audio, path, audio.data)
        except OSError:
            logger.exception("음성 원본 저장 실패(session=%s)", session_id)
            return
        try:
            await _set_audio_path(db, turn_id, relative.as_posix())
        except Exception:
            logger.exception("음성 원본 경로 저장 실패, 파일을 지움(session=%s)", session_id)
            with contextlib.suppress(Exception):
                await db.rollback()
            with contextlib.suppress(OSError):
                await asyncio.to_thread(path.unlink, missing_ok=True)


_MAX_TURN_SOURCES = 20


def _collect_sources(sources: dict[str, dict], summary: dict | None) -> None:
    """도구 결과 요약(parser._tool_summary)에서 웹 검색 링크·읽은 페이지 URL을 모은다(중복 없이)."""
    if not summary:
        return
    if summary.get("kind") == "web_search":
        found = [(link.get("title"), link.get("url")) for link in summary.get("links") or []]
    elif summary.get("kind") == "web_fetch":
        found = [(None, summary.get("url"))]
    else:
        return
    for title, url in found:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if len(sources) >= _MAX_TURN_SOURCES and url not in sources:
            return
        known = sources.get(url)
        if known is None or (not known["title"] and title):  # 읽기만 한 페이지에 검색 제목을 붙인다
            sources[url] = {
                "title": " ".join(title.split()) if isinstance(title, str) else None,
                "url": url,
            }


async def _save_reply(
    db: AsyncSession,
    turn_id: str,
    session_id: str,
    seq: int,
    text: str,
    interrupted: bool,
    exists: bool,
    sources: list[dict] | None = None,
) -> None:
    """assistant 턴을 만들거나 고친다(커밋은 부르는 쪽). 문장마다 불리므로 한 줄 쿼리로 끝낸다.
    sources: 그때까지 본 출처(없으면 NULL로 둔다)."""
    if exists:
        statement = (
            update(Turn)
            .where(Turn.id == turn_id)
            .values(text=text, interrupted=interrupted, sources=sources or None)
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
            sources=sources or None,
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
