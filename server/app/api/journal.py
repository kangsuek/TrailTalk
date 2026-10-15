"""일지·노트 API(계획서 S2-07, 설계서 4.6): 일지 목록·상세, 노트 별표·완료·내용 수정.

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

from app.db.models import ConversationSession, Note, NoteKind, Turn, TurnRole
from app.db.session import DbSession
from app.errors import AppError
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

    @classmethod
    def of(cls, note: Note) -> "NoteOut":
        return cls(
            id=note.id,
            kind=note.kind.value,
            content=note.content,
            starred=note.starred,
            done=note.done,
            created_at=note.created_at,
        )


class TurnOut(BaseModel):
    id: str
    seq: int
    role: Literal["user", "assistant"]
    text: str
    interrupted: bool  # 끝까지 말하지 못한 답변(연결 끊김·끼어들기 등)
    created_at: datetime


class JournalDetail(BaseModel):
    session: JournalItem
    # 전문의 assistant 화자 이름(현재 페르소나 YAML). 클라이언트는 캐릭터 이름을 코드에 두지 않는다
    persona_name: str
    notes: list[NoteOut]
    turns: list[TurnOut]


def _content(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 500:
        raise ValueError("1~500자로 입력하세요")
    return value


class NotePatch(BaseModel):
    """보낸 필드만 바꾼다."""

    model_config = ConfigDict(extra="forbid")

    starred: StrictBool | None = None
    done: StrictBool | None = None
    content: Annotated[str, AfterValidator(_content)] | None = None


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
    return JournalDetail(
        session=_item(convo, counts, tz),
        persona_name=loaded.persona.name,
        notes=[NoteOut.of(n) for n in note_rows],
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
    return NoteOut.of(note)
