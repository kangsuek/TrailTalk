"""대화 세션 API(설계서 4.6): 시작(인사말), 턴(SSE), 종료(마무리 멘트), 다시 열기(S3-26)."""

import time
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.events import sse_response_doc
from app.api.journal import TurnOut
from app.db.models import ConversationMode, ConversationSession, UserProfile
from app.db.session import DbSession
from app.errors import AppError
from app.jobs import closing, extract
from app.services import attachments, conversation
from app.services.profile import PROFILE_ID, profile_voice, profile_with_persona
from app.voice.audio import prepare_for_stt
from app.voice.tts import has_speech

router = APIRouter(tags=["sessions"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class EventStreamResponse(StreamingResponse):
    """연결이 끊겨도 본문 제너레이터를 바로 닫는다.

    Starlette는 끊긴 스트림의 제너레이터를 닫지 않고 GC에 맡긴다. 그동안 턴 락과 CLI 턴이
    풀리지 않으므로 여기서 직접 닫는다(제너레이터의 finally·aclosing이 CLI 턴을 멈춘다).
    """

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.body_iterator.aclose()  # type: ignore[union-attr]


class SessionOut(BaseModel):
    id: str
    mode: Literal["text", "voice"]
    status: Literal["active", "paused", "ended"]
    started_at: datetime
    ended_at: datetime | None

    @classmethod
    def of(cls, convo: ConversationSession) -> "SessionOut":
        return cls(
            id=convo.id,
            mode=convo.mode.value,
            status=convo.status.value,
            started_at=convo.started_at,
            ended_at=convo.ended_at,
        )


class SavedCounts(BaseModel):
    idea: int
    todo: int
    memo: int


class SessionClosed(BaseModel):
    """끝내기 응답. closing은 캐릭터가 하는 마무리 멘트, saved는 이 대화에서 저장한 노트 개수다.

    journal_status가 pending이면 일지 정리가 아직 끝나지 않은 것이다(개수가 나중에 늘 수 있다).
    """

    session: SessionOut
    closing: str
    closing_audio: str | None  # 마무리 멘트 MP3(base64). 음성 세션에서만, 합성 실패면 null
    saved: SavedCounts
    journal_status: Literal["pending", "done", "failed"] | None


class SessionCreate(BaseModel):
    mode: Literal["text", "voice"] = "text"


class GreetingOut(BaseModel):
    turn_id: str
    text: str
    audio: str | None  # 인사말 MP3(base64). 음성 세션에서만, 합성 실패면 null


class PersonaOut(BaseModel):
    """화면에 보일 캐릭터 정보. 클라이언트는 캐릭터 이름을 코드에 두지 않고 이 값을 쓴다(NFR-08)."""

    id: str
    name: str


class SessionStarted(BaseModel):
    session: SessionOut
    greeting: GreetingOut
    persona: PersonaOut


class SessionReopened(SessionStarted):
    """다시 연 대화. greeting은 재개 인사말, turns는 그 인사말까지 포함한 전체 전문이다."""

    turns: list[TurnOut]


class TurnCreate(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=4000, pattern=r"\S")]


@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate, request: Request, db: DbSession) -> SessionStarted:
    app = request.app
    convo, greeting, loaded, voice = await conversation.start_session(
        app, db, ConversationMode(body.mode)
    )
    audio = None
    if convo.mode is ConversationMode.VOICE:
        audio = await app.state.speech.synthesize(app, greeting.text, voice)
    return SessionStarted(
        session=SessionOut.of(convo),
        greeting=GreetingOut(turn_id=greeting.id, text=greeting.text, audio=audio),
        persona=PersonaOut(id=loaded.persona.id, name=loaded.persona.name),
    )


@router.post("/sessions/{session_id}/reopen")
async def reopen_session(
    session_id: str, body: SessionCreate, request: Request, db: DbSession
) -> SessionReopened:
    """대화를 같은 세션으로 다시 연다(S3-26). 다시 끝내면 일지를 새로 정리한다.

    끝나지 않은 대화도 이어받는다(S3-37, 지금 CLI를 닫고 새로 띄운다). 답변 중이면 409
    turn_in_progress, 없으면 404 session_not_found.
    """
    app = request.app
    convo, greeting, turns, loaded, voice = await conversation.reopen_session(
        app, db, session_id, ConversationMode(body.mode)
    )
    audio = None
    if convo.mode is ConversationMode.VOICE:
        audio = await app.state.speech.synthesize(app, greeting.text, voice)
    return SessionReopened(
        session=SessionOut.of(convo),
        greeting=GreetingOut(turn_id=greeting.id, text=greeting.text, audio=audio),
        persona=PersonaOut(id=loaded.persona.id, name=loaded.persona.name),
        turns=[TurnOut.of(t) for t in turns],
    )


@router.post("/sessions/prepare", status_code=204)
async def prepare_session(body: SessionCreate, request: Request, db: DbSession) -> Response:
    """대화 화면이 열리면 부른다. 다음 대화의 CLI를 미리 띄워 인사말 대기를 줄인다(사용량 없음)."""
    await conversation.prepare_session(request.app, db, ConversationMode(body.mode))
    return Response(status_code=204)


@router.post(
    "/sessions/{session_id}/turns",
    response_class=StreamingResponse,
    responses=sse_response_doc("턴 이벤트 스트림(turn → sentence·tool → done 또는 error)"),
)
async def create_turn(
    session_id: str, body: TurnCreate, request: Request, db: DbSession
) -> StreamingResponse:
    convo = await conversation.get_session(db, session_id)
    conversation.check_turn_allowed(request.app, convo)
    # 요청 세션의 커넥션을 스트림 내내 쥐지 않는다. 끊김으로 취소된 채 닫히면 망가진 커넥션이
    # 풀로 돌아간다. 스트림은 자기 세션을 따로 연다
    await db.close()
    return EventStreamResponse(
        conversation.stream_turn(request.app, session_id, body.text.strip()),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


# 파일 첨부 턴(FR-22): multipart/form-data. text는 질문, files는 첨부(반복)
_FILES_REQUEST = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["text", "files"],
                    "properties": {
                        "text": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "files": {
                            "type": "array",
                            "items": {"type": "string", "format": "binary"},
                        },
                    },
                }
            }
        },
    }
}
_FORM_OVERHEAD = 1024 * 1024  # 본문에서 파일 외 부분(경계·헤더·글)의 여유


@router.post(
    "/sessions/{session_id}/turns/files",
    response_class=StreamingResponse,
    responses=sse_response_doc("턴 이벤트 스트림(turn → sentence·tool → done 또는 error)"),
    openapi_extra=_FILES_REQUEST,
)
async def create_files_turn(session_id: str, request: Request, db: DbSession) -> StreamingResponse:
    """질문에 파일(이미지·텍스트)을 붙인 글 턴(FR-22). 텍스트 세션에서만 받는다.

    순서: 세션·턴 가능 확인 → DB 닫기 → 본문 크기 선검사 → multipart 파싱 → 검증·가공 → SSE.
    잘못된 첨부는 JSON 오류(attachment_invalid 400, attachment_too_large 413)로 나간다."""
    app = request.app
    settings = app.state.settings
    convo = await conversation.get_session(db, session_id)
    conversation.check_turn_allowed(app, convo)
    if convo.mode is not ConversationMode.TEXT:
        raise attachments.invalid("파일은 글 대화에서만 보낼 수 있어요.")
    used = await attachments.session_usage(db, session_id)
    await db.close()  # 업로드를 받는 동안 커넥션을 쥐지 않는다
    per_file = max(settings.attachment_image_upload_max_bytes, settings.attachment_pdf_max_bytes)
    limit = settings.attachment_max_files * per_file
    length = request.headers.get("content-length")
    if length is None or not length.isdigit():
        # 크기를 모르는 업로드는 받지 않는다(파싱 전에 디스크를 채울 수 있다)
        raise attachments.invalid("요청 크기를 알 수 없어요.")
    if int(length) > limit + _FORM_OVERHEAD:
        raise attachments.too_large("보내는 파일이 너무 커요.")
    try:
        form = await request.form(max_files=settings.attachment_max_files, max_fields=4)
    except StarletteHTTPException:
        raise attachments.invalid("파일은 한 번에 보낼 수 있는 개수를 넘었어요.") from None
    try:
        text = str(form.get("text") or "").strip()
        if not text:
            raise attachments.invalid("파일과 함께 질문을 적어 주세요.")
        if len(text) > _TEXT_MAX:
            raise attachments.invalid(f"질문은 {_TEXT_MAX}자까지 적을 수 있어요.")
        files = form.getlist("files")
        attachments.check_count(settings, len(files))
        uploads = []
        for item in files:
            if not isinstance(item, UploadFile):
                raise attachments.invalid("파일 형식이 올바르지 않아요.")
            data = await item.read(
                max(settings.attachment_image_upload_max_bytes, settings.attachment_pdf_max_bytes)
                + 1
            )
            uploads.append(attachments.Upload(item.filename or "", data))
    finally:
        await form.close()
    prepared = await attachments.prepare(settings, session_id, uploads, used)
    return EventStreamResponse(
        conversation.stream_turn(app, session_id, text, attachments=prepared),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


class TurnCancel(BaseModel):
    """끼어들기: 다 들려준 마지막 문장 번호(sentence.index). 하나도 못 들려줬으면 -1."""

    model_config = ConfigDict(extra="forbid")

    last_played: Annotated[int, Field(ge=-1)]


@router.post("/sessions/{session_id}/turns/{turn_id}/cancel", status_code=204)
async def cancel_turn(
    session_id: str, turn_id: str, body: TurnCancel, request: Request, db: DbSession
) -> Response:
    """끼어들기(계획서 S3-04): 답변을 멈추고 들려준 문장까지만 기록한다. 끝난 턴도 받는다(멱등)."""
    await conversation.cancel_turn(request.app, db, session_id, turn_id, body.last_played)
    return Response(status_code=204)


# 음성 업로드 본문(오디오 바이트 그대로). 웹은 audio/webm
_AUDIO_BODY = {"type": "string", "format": "binary"}
_AUDIO_REQUEST = {
    "requestBody": {
        "required": True,
        "content": {
            mime: {"schema": _AUDIO_BODY}
            for mime in ("audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/mpeg")
        },
    }
}
_TEXT_MAX = 4000  # 텍스트 턴(TurnCreate)과 같은 상한
_LATENCY_MAX_MS = 10 * 60 * 1000  # 보고받는 지연의 상한(10분, 그보다 크면 잘못 잰 값)


async def _read_body(request: Request, max_bytes: int) -> bytes:
    """본문을 읽되 상한을 넘으면 끝까지 받지 않고 413을 낸다."""
    too_large = AppError("audio_invalid", "오디오가 너무 큽니다.", 413)
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > max_bytes:
        raise too_large
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/sessions/{session_id}/turns/audio",
    response_class=StreamingResponse,
    responses=sse_response_doc(
        "음성 턴 이벤트 스트림(transcript → turn → sentence·tool → done 또는 error)"
    ),
    openapi_extra=_AUDIO_REQUEST,
)
async def create_audio_turn(session_id: str, request: Request, db: DbSession) -> StreamingResponse:
    """말 한 번(오디오)을 받아 인식한 뒤 텍스트 턴과 같은 SSE로 답한다(계획서 S3-03).

    인식은 SSE를 열기 전에 하므로 오디오·인식 오류와 말 없음(no_speech)은 JSON 오류로 간다."""
    app = request.app
    settings = app.state.settings
    started = time.monotonic()  # 지연 측정(S3-07)의 기준: 서버가 요청 처리를 시작한 때
    convo = await conversation.get_session(db, session_id)
    conversation.check_turn_allowed(app, convo)
    hint = await conversation.last_reply(db, session_id)
    profile = await db.get(UserProfile, PROFILE_ID)  # 읽기만 한다(없으면 기본값: 보관 안 함)
    keep_audio = profile is not None and profile.keep_audio
    await db.close()  # 인식하는 동안 커넥션을 쥐지 않는다
    body = await _read_body(request, settings.stt_max_bytes)
    upload_ms = round((time.monotonic() - started) * 1000)
    stt_started = time.monotonic()  # 인식 시간에는 형식 변환(ffmpeg)도 넣는다
    audio = await prepare_for_stt(
        body,
        request.headers.get("content-type"),
        max_bytes=settings.stt_max_bytes,
        ffmpeg_path=settings.ffmpeg_path,
        timeout_s=settings.ffmpeg_timeout_s,
    )
    text = (await app.state.stt.transcribe(audio, prompt=hint))[:_TEXT_MAX].strip()
    timing = conversation.VoiceTiming(
        started=started,
        audio_bytes=len(body),
        upload_ms=upload_ms,
        stt_ms=round((time.monotonic() - stt_started) * 1000),
    )
    if not has_speech(text):
        raise AppError("no_speech", "말소리를 알아듣지 못했어요.", 422)
    return EventStreamResponse(
        conversation.stream_turn(
            app,
            session_id,
            text,
            from_voice=True,
            audio=audio if keep_audio else None,
            timing=timing,
        ),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


class RecordedTurn(BaseModel):
    text: str  # 인식해 저장한 말


@router.post(
    "/sessions/{session_id}/turns/audio/record",
    status_code=201,
    openapi_extra=_AUDIO_REQUEST,
)
async def record_audio_turn(session_id: str, request: Request, db: DbSession) -> RecordedTurn:
    """오프라인 큐의 말을 대답 없이 기록만 남긴다(계획서 S3-12). 끝난 대화도 받는다.

    서버가 이미 대화를 끝냈거나(30분 넘게 끊김) 페이지를 새로 열어 대답할 수 없는 말의
    유실을 막는다."""
    app = request.app
    settings = app.state.settings
    await conversation.get_session(db, session_id)
    audio = await prepare_for_stt(
        await _read_body(request, settings.stt_max_bytes),
        request.headers.get("content-type"),
        max_bytes=settings.stt_max_bytes,
        ffmpeg_path=settings.ffmpeg_path,
        timeout_s=settings.ffmpeg_timeout_s,
    )
    text = (await app.state.stt.transcribe(audio))[:_TEXT_MAX].strip()
    if not has_speech(text):
        raise AppError("no_speech", "말소리를 알아듣지 못했어요.", 422)
    await conversation.record_offline_turn(app, db, session_id, text)
    return RecordedTurn(text=text)


class LatencyReport(BaseModel):
    """웹이 잰 지연(ms, S3-07): 말 끝 → 요청 시작, 요청 시작 → 첫 소리.
    first_sound_notice: 첫 소리가 검색 안내 음성이었다.
    ack_ms: 맞장구가 재생되기 시작한 시각(요청 시작 대비, V2 첫 반응 지연). 없으면 생략."""

    model_config = ConfigDict(extra="forbid")

    speech_to_request_ms: Annotated[int, Field(ge=0, le=_LATENCY_MAX_MS)]
    request_to_playback_ms: Annotated[int, Field(ge=0, le=_LATENCY_MAX_MS)]
    first_sound_notice: bool = False
    ack_ms: Annotated[int, Field(ge=0, le=_LATENCY_MAX_MS)] | None = None


@router.post("/sessions/{session_id}/turns/{turn_id}/latency", status_code=204)
async def report_latency(
    session_id: str, turn_id: str, body: LatencyReport, db: DbSession
) -> Response:
    """음성 턴의 지연을 보고한다(계획서 S3-07). 측정 행이 없으면 404 turn_not_found."""
    await conversation.report_latency(
        db,
        session_id,
        turn_id,
        body.speech_to_request_ms,
        body.request_to_playback_ms,
        body.first_sound_notice,
        body.ack_ms,
    )
    return Response(status_code=204)


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, request: Request, db: DbSession) -> SessionClosed:
    """세션을 끝내고 일지 정리를 띄운 뒤, 정리가 끝나길 잠깐 기다려 마무리 멘트를 준다(멱등)."""
    app = request.app
    convo = await conversation.get_session(db, session_id)
    await conversation.end_session(app, db, convo)
    # 기다리는 동안 이 요청의 트랜잭션을 열어 두지 않는다(추출 결과 쓰기와 잠금이 겹치지 않게)
    await db.commit()
    await extract.wait_extraction(app, session_id, app.state.settings.extract_wait_s)
    await db.refresh(convo)
    counts = await closing.count_notes(db, session_id, since=convo.reopened_at)
    profile, loaded = await profile_with_persona(db, app.state.settings)
    await db.commit()
    message = closing.closing_message(loaded.persona, counts)
    audio = None
    if convo.mode is ConversationMode.VOICE:
        audio = await app.state.speech.synthesize(app, message, profile_voice(profile, loaded))
    return SessionClosed(
        session=SessionOut.of(convo),
        closing=message,
        closing_audio=audio,
        saved=SavedCounts(**{kind.value: count for kind, count in counts.items()}),
        journal_status=convo.extract_status.value if convo.extract_status else None,
    )
