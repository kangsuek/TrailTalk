"""일지·노트 API(계획서 S2-07, 설계서 4.6): 일지 목록·상세·제목 수정·삭제·다시 정리,
노트 별표·완료·내용 수정.

날짜는 서버 시간대(settings.timezone)의 현지 날짜다. 목록 항목에 현지 날짜(date)를 실어 클라이언트가
시간대 계산 없이 날짜별로 묶게 한다. 요약은 줄 목록으로 준다.
"""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from pydantic import AfterValidator, BaseModel, ConfigDict, StrictBool
from sqlalchemy import exists, func, select
from sqlalchemy.orm import defer

from app.db.models import (
    ConversationSession,
    ExtractStatus,
    Note,
    NoteKind,
    SessionStatus,
    Turn,
    TurnRole,
)
from app.db.session import DbSession
from app.errors import AppError
from app.jobs import extract
from app.services import conversation
from app.services.conversation import SessionNotFound
from app.services.profile import profile_with_persona

router = APIRouter(tags=["journal"])

DEFAULT_DAYS = 30
MAX_DAYS = 366
# 시간대 변환이 넘치지 않는 범위(0001-01-01·9999-12-31 근처는 UTC로 바꿀 때 OverflowError)
MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(9998, 12, 31)


class NoteNotFound(AppError):
    def __init__(self) -> None:
        super().__init__("note_not_found", "노트를 찾을 수 없습니다.", 404)


class NoteCounts(BaseModel):
    idea: int
    todo: int
    memo: int


class JournalItem(BaseModel):
    id: str
    date: date  # 대화를 시작한 현지 날짜
    started_at: datetime
    ended_at: datetime | None
    status: Literal["active", "paused", "ended"]
    title: str | None
    summary: list[str]
    tags: list[str]
    # 이 대화에서 다룬 아이디어 주제. 같은 이름끼리 아이디어별로 묶는다(S3-17). 정리 전이면 빈 목록
    topics: list[str]
    # 일지 정리 상태. null이면 아직 끝나지 않은 대화다
    journal_status: Literal["pending", "done", "failed"] | None
    counts: NoteCounts


class NoteOut(BaseModel):
    id: str
    kind: Literal["idea", "todo", "memo"]
    content: str
    starred: bool
    done: bool
    created_at: datetime
    cites: list[int]  # 메모의 근거 출처 번호(citations의 n, S3-23). 없으면 빈 목록

    @classmethod
    def of(cls, note: Note, cites: list[int] | None = None) -> "NoteOut":
        return cls(
            id=note.id,
            kind=note.kind.value,
            content=note.content,
            starred=note.starred,
            done=note.done,
            created_at=note.created_at,
            cites=cites or [],
        )


class TurnOut(BaseModel):
    id: str
    seq: int
    role: Literal["user", "assistant"]
    text: str
    interrupted: bool  # 끝까지 말하지 못한 답변(연결 끊김·끼어들기 등)
    created_at: datetime


class CitationOut(BaseModel):
    n: int
    title: str  # 기사·문서 제목(없으면 호스트 이름)
    url: str


class JournalDetail(BaseModel):
    session: JournalItem
    # 일지 인용(S3-23): session.summary 줄마다 근거 출처 번호(같은 길이, 없으면 빈 목록)와
    # 인용 목록. 검색하지 않은 대화·인용이 생기기 전 일지는 빈 목록이다
    summary_cites: list[list[int]]
    citations: list[CitationOut]
    # 전문의 assistant 화자 이름(현재 페르소나 YAML). 클라이언트는 캐릭터 이름을 코드에 두지 않는다
    persona_name: str
    notes: list[NoteOut]
    turns: list[TurnOut]


def _content(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 500:
        raise ValueError("1~500자로 입력하세요")
    return value


def _title(value: str) -> str:
    value = " ".join(value.split())  # 목록에 한 줄로 보이므로 줄바꿈·연속 공백은 한 칸으로
    if not 1 <= len(value) <= 200:
        raise ValueError("1~200자로 입력하세요")
    return value


class JournalPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, AfterValidator(_title)]


class NotePatch(BaseModel):
    """보낸 필드만 바꾼다."""

    model_config = ConfigDict(extra="forbid")

    starred: StrictBool | None = None
    done: StrictBool | None = None
    content: Annotated[str, AfterValidator(_content)] | None = None


def _number(
    convo: ConversationSession, notes: list[Note]
) -> tuple[list[list[int]], dict[str, list[int]], list[dict]]:
    """일지 인용 번호(S3-23): 남아 있는 요약 줄 → 메모(만든 순) 차례로 처음 인용된 출처부터 1번.
    (요약 줄마다 번호, 노트 ID → 번호, 인용 목록)"""
    lines = (convo.summary or "").splitlines()
    stored = list(convo.summary_cites or [])
    summary_urls = [
        stored[i] if i < len(stored) and isinstance(stored[i], list) else []
        for i in range(len(lines))
    ]
    memos = [n for n in notes if n.kind is NoteKind.MEMO and n.cites]
    titles = {c["url"]: c["title"] for c in convo.citations or [] if isinstance(c, dict)}
    summary_ids, memo_ids, citations = extract.number_citations(
        summary_urls, [n.cites for n in memos], titles
    )
    return summary_ids, {n.id: ids for n, ids in zip(memos, memo_ids, strict=True)}, citations


def _item(convo: ConversationSession, counts: dict[NoteKind, int], tz: ZoneInfo) -> JournalItem:
    return JournalItem(
        id=convo.id,
        date=convo.started_at.astimezone(tz).date(),
        started_at=convo.started_at,
        ended_at=convo.ended_at,
        status=convo.status.value,
        title=convo.title,
        summary=(convo.summary or "").splitlines(),
        tags=list(convo.tags or []),
        topics=list(convo.topics or []),
        journal_status=convo.extract_status.value if convo.extract_status else None,
        counts=NoteCounts(**{kind.value: counts.get(kind, 0) for kind in NoteKind}),
    )


async def _counts(db, session_ids: list[str]) -> dict[str, dict[NoteKind, int]]:
    result: dict[str, dict[NoteKind, int]] = {sid: {} for sid in session_ids}
    if not session_ids:
        return result
    rows = await db.execute(
        select(Note.session_id, Note.kind, func.count())
        .where(Note.session_id.in_(session_ids))
        .group_by(Note.session_id, Note.kind)
    )
    for session_id, kind, count in rows:
        result[session_id][kind] = count
    return result


@router.get("/journal")
async def list_journal(
    request: Request,
    db: DbSession,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> list[JournalItem]:
    """현지 날짜 범위(from~to, 둘 다 포함)의 일지. 기본은 최근 30일. 최신순.

    사용자가 한마디도 하지 않은 대화(인사말만 있는 것)는 빼고 준다.
    """
    tz = ZoneInfo(request.app.state.settings.timezone)
    to = to or datetime.now(tz).date()
    from_ = from_ or to - timedelta(days=DEFAULT_DAYS - 1)
    if not (MIN_DATE <= from_ and to <= MAX_DATE):
        raise AppError("invalid_range", "조회할 수 없는 날짜입니다.", 422)
    if from_ > to:
        raise AppError("invalid_range", "시작 날짜가 끝 날짜보다 늦습니다.", 422)
    if (to - from_).days >= MAX_DAYS:
        raise AppError("invalid_range", f"한 번에 {MAX_DAYS}일까지 조회할 수 있습니다.", 422)
    start = datetime.combine(from_, time.min, tz)
    end = datetime.combine(to + timedelta(days=1), time.min, tz)
    spoke = exists().where(Turn.session_id == ConversationSession.id, Turn.role == TurnRole.USER)
    rows = await db.execute(
        select(ConversationSession)
        .options(defer(ConversationSession.system_prompt))  # 응답에 쓰지 않는 큰 글
        .where(
            ConversationSession.started_at >= start,
            ConversationSession.started_at < end,
            spoke,
        )
        .order_by(ConversationSession.started_at.desc())
    )
    sessions = list(rows.scalars())
    counts = await _counts(db, [s.id for s in sessions])
    return [_item(s, counts[s.id], tz) for s in sessions]


@router.get("/journal/{session_id}")
async def get_journal(session_id: str, request: Request, db: DbSession) -> JournalDetail:
    """일지 상세. 목록에서 빠지는 대화(사용자 발화 없음)도 ID로는 조회된다."""
    convo = await db.get(ConversationSession, session_id)
    if convo is None:
        raise SessionNotFound()
    tz = ZoneInfo(request.app.state.settings.timezone)
    notes = await db.execute(
        select(Note).where(Note.session_id == session_id).order_by(Note.created_at, Note.id)
    )
    turns = await db.execute(select(Turn).where(Turn.session_id == session_id).order_by(Turn.seq))
    note_rows = list(notes.scalars())
    _, loaded = await profile_with_persona(db, request.app.state.settings)
    await db.commit()
    counts = {kind: sum(n.kind is kind for n in note_rows) for kind in NoteKind}
    summary_ids, note_ids, citations = _number(convo, note_rows)
    return JournalDetail(
        session=_item(convo, counts, tz),
        summary_cites=summary_ids,
        citations=[CitationOut(**c) for c in citations],
        persona_name=loaded.persona.name,
        notes=[NoteOut.of(n, note_ids.get(n.id)) for n in note_rows],
        turns=[
            TurnOut(
                id=t.id,
                seq=t.seq,
                role=t.role.value,
                text=t.text,
                interrupted=t.interrupted,
                created_at=t.created_at,
            )
            for t in turns.scalars()
        ],
    )


@router.patch("/journal/{session_id}")
async def update_journal(
    session_id: str, body: JournalPatch, request: Request, db: DbSession
) -> JournalItem:
    """대화 제목을 고친다. 고친 제목은 일지를 다시 정리해도 바뀌지 않는다."""
    convo = await db.get(ConversationSession, session_id)
    if convo is None:
        raise SessionNotFound()
    convo.title = body.title
    convo.title_edited = True
    await db.commit()
    tz = ZoneInfo(request.app.state.settings.timezone)
    counts = await _counts(db, [session_id])
    return _item(convo, counts[session_id], tz)


@router.delete("/journal/{session_id}", status_code=204)
async def delete_journal(session_id: str, request: Request, db: DbSession) -> None:
    """대화를 지운다(전문·노트·지연 기록·보관한 녹음까지). 진행 중인 대화는 409 session_active,
    답변을 만드는 중이면 409 turn_in_progress. 쉬는 중이면 CLI를 정리하고, 돌던 일지 정리는 멈춘다.
    """
    await conversation.delete_session(request.app, db, session_id)


@router.patch("/notes/{note_id}")
async def update_note(note_id: str, body: NotePatch, db: DbSession) -> NoteOut:
    note = await db.get(Note, note_id)
    if note is None:
        raise NoteNotFound()
    for field in body.model_fields_set:
        value = getattr(body, field)
        if value is None:
            raise AppError("validation_error", f"{field}에는 null을 쓸 수 없습니다.", 422)
        setattr(note, field, value)
    await db.commit()
    cites: list[int] = []
    if note.kind is NoteKind.MEMO and note.cites:
        # 상세와 같은 번호를 돌려준다(그 일지의 요약·메모 전체로 매긴다)
        convo = await db.get(ConversationSession, note.session_id)
        rows = await db.execute(
            select(Note)
            .where(Note.session_id == note.session_id)
            .order_by(Note.created_at, Note.id)
        )
        _, note_ids, _ = _number(convo, list(rows.scalars()))
        cites = note_ids.get(note.id, [])
    return NoteOut.of(note, cites)


class SessionNotEnded(AppError):
    def __init__(self) -> None:
        super().__init__("session_not_ended", "아직 끝나지 않은 대화입니다.", 409)


@router.post("/journal/{session_id}/retry", status_code=202)
async def retry_journal(session_id: str, request: Request, db: DbSession) -> JournalItem:
    """정리에 실패한(또는 정리 기록이 없는) 끝난 대화를 다시 정리한다. 정리 중·완료면 그대로 둔다.

    정리는 백그라운드로 돈다. 응답의 journal_status가 pending이면 상세를 다시 불러와 끝을 본다.
    """
    convo = await db.get(ConversationSession, session_id)
    if convo is None:
        raise SessionNotFound()
    if convo.status is not SessionStatus.ENDED:
        raise SessionNotEnded()
    if convo.extract_status in (None, ExtractStatus.FAILED):
        convo.extract_status = ExtractStatus.PENDING
        await db.commit()
        extract.ensure_extraction(request.app, session_id)
    tz = ZoneInfo(request.app.state.settings.timezone)
    counts = await _counts(db, [session_id])
    return _item(convo, counts[session_id], tz)
