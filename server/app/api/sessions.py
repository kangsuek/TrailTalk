"""대화 세션 API(설계서 4.6): 시작(인사말), 턴(SSE), 종료."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.events import sse_response_doc
from app.db.models import ConversationMode, ConversationSession
from app.db.session import DbSession
from app.services import conversation

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


class SessionCreate(BaseModel):
    mode: Literal["text", "voice"] = "text"


class GreetingOut(BaseModel):
    turn_id: str
    text: str


class SessionStarted(BaseModel):
    session: SessionOut
    greeting: GreetingOut


class TurnCreate(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=4000, pattern=r"\S")]


@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate, request: Request, db: DbSession) -> SessionStarted:
    convo, greeting = await conversation.start_session(request.app, db, ConversationMode(body.mode))
    return SessionStarted(
        session=SessionOut.of(convo), greeting=GreetingOut(turn_id=greeting.id, text=greeting.text)
    )


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


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: str, request: Request, db: DbSession) -> SessionOut:
    convo = await conversation.get_session(db, session_id)
    await conversation.end_session(request.app, db, convo)
    return SessionOut.of(convo)
