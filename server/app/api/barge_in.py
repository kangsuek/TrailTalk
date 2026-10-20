"""POST /api/barge-in-events: 기기가 모은 끼어들기 기록을 배치로 받는다(V2-M0-05)."""

from typing import Annotated

from fastapi import APIRouter
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.dialects.sqlite import insert

from app.db.models import BargeInEvent
from app.db.session import DbSession

router = APIRouter(tags=["barge-in"])

MAX_BATCH = 200


class BargeInEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=36)]  # 기기가 만든 ID(다시 올려도 한 행)
    session_id: Annotated[str, Field(min_length=1, max_length=36)]
    turn_id: Annotated[str, Field(min_length=1, max_length=36)]
    occurred_at: AwareDatetime  # 시간대 없는 시각은 거절한다(DB 저장 형식이 UTC 시간대를 요구한다)
    probe_to_confirm_ms: Annotated[int | None, Field(ge=0)] = None
    stop_ms: Annotated[int | None, Field(ge=0)] = None
    played_ratio: Annotated[float | None, Field(ge=0, le=1)] = None
    result: Annotated[str, Field(min_length=1, max_length=32)] = "real"
    next_turn_id: Annotated[str | None, Field(max_length=36)] = None


class BargeInEventsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: Annotated[list[BargeInEventIn], Field(max_length=MAX_BATCH)]


class BargeInEventsOut(BaseModel):
    accepted: int  # 이번에 새로 저장한 수(이미 있던 id는 세지 않는다)


@router.post("/barge-in-events")
async def post_barge_in_events(body: BargeInEventsIn, db: DbSession) -> BargeInEventsOut:
    """멱등: 이미 있는 id는 건너뛴다(같은 id가 한 배치에 겹치거나 동시에 올라와도 한 번만)."""
    accepted = 0
    for event in body.events:
        result = await db.execute(
            insert(BargeInEvent).values(**event.model_dump()).on_conflict_do_nothing()
        )
        accepted += result.rowcount
    await db.commit()
    return BargeInEventsOut(accepted=accepted)
