"""캐릭터가 쓰는 앱 도구 MCP 서버(설계서 4.3, 계획서 S1-06).

FastAPI 안의 HTTP 엔드포인트(/internal/mcp/)로 둔다. 도구가 같은 프로세스의 DB와 대화 상태
(쉬기·종료 요청)를 바로 다루기 위해서다. Claude CLI는 대화 세션마다 받은 토큰을
Authorization 헤더로, 세션 ID를 X-TrailTalk-Session 헤더로 보낸다(--mcp-config).
도구 이름은 app/persona/rules.py의 규칙 문구와 맞춘다.

이 경로는 같은 서버의 CLI만 쓴다. 배포 시 터널·리버스 프록시에서 /internal/*를 막아야 하며,
프록시를 거친 요청(전달 헤더가 붙은 요청)은 토큰이 맞아도 거부한다.
"""

import logging
from datetime import timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db.models import Note, NoteKind, SessionStatus, Turn, TurnRole
from app.db.types import utcnow
from app.errors import error_response
from app.services.runtime import ConversationRuntime, RuntimeRegistry

SERVER_NAME = "trailtalk"  # CLI 도구 이름 접두사 mcp__trailtalk__ 와 같다
MOUNT_PATH = "/internal/mcp"
SESSION_HEADER = "x-trailtalk-session"
_SEARCH_LIMIT = 10
# 프록시·터널이 붙이는 헤더. CLI는 루프백으로 바로 접속하므로 이런 헤더가 오지 않는다.
# Tailscale Serve(폰 접속, docs/phone.md)는 X-Forwarded-Host를 늘 붙이고 X-Forwarded-For와
# tailnet 사용자 신원 헤더(사람 계정 기기일 때)를 더한다
_FORWARDED_HEADERS = (
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
    "cf-connecting-ip",
    "tailscale-user-login",
)

logger = logging.getLogger("trailtalk.mcp")


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def mcp_client_config(base_url: str, runtime: ConversationRuntime) -> dict:
    """Claude CLI --mcp-config에 넘길 설정. 토큰이 들어 있으니 로그에 남기지 않는다."""
    return {
        "mcpServers": {
            SERVER_NAME: {
                "type": "http",
                "url": f"{base_url.rstrip('/')}{MOUNT_PATH}/",
                "headers": {
                    "Authorization": f"Bearer {runtime.token}",
                    "X-TrailTalk-Session": runtime.session_id,
                },
            }
        }
    }


def build_mcp_server(app) -> MCPServer:
    """앱 도구를 등록한 MCP 서버. DB와 대화 상태는 app.state에서 가져온다."""
    # 구독(subscriptions/listen)을 끈다: CLI가 이 요청을 계속 열어 두면 서버 종료가 멈춘다
    mcp = MCPServer(SERVER_NAME, subscriptions=False)

    def runtime_of(ctx: Context) -> ConversationRuntime:
        headers = ctx.headers or {}
        runtime = app.state.runtimes.get(headers.get(SESSION_HEADER, ""))
        if runtime is None:  # 인증 미들웨어를 통과했으면 일어나지 않는다
            raise ToolError("대화 세션을 찾을 수 없습니다.")
        return runtime

    @mcp.tool()
    async def save_note(
        kind: Literal["idea", "todo", "memo"],
        content: Annotated[str, Field(min_length=1, max_length=1000)],
        ctx: Context,
    ) -> str:
        """아이디어(idea)·할 일(todo)·메모(memo)를 저장한다.

        사용자가 저장을 요청했거나 기억해 둘 만한 내용이 나왔을 때 쓴다.
        """
        runtime = runtime_of(ctx)
        content = content.strip()
        if not content:
            raise ToolError("저장할 내용이 비어 있습니다.")
        try:
            async with app.state.session_factory() as db:
                db.add(
                    Note(
                        session_id=runtime.session_id,
                        turn_id=runtime.current_user_turn_id,
                        kind=NoteKind(kind),
                        content=content,
                    )
                )
                await db.commit()
        except SQLAlchemyError:
            # SQL·파라미터가 담긴 예외 문구를 모델에 넘기지 않는다
            logger.exception("save_note failed session=%s", runtime.session_id)
            raise ToolError("노트를 저장하지 못했습니다.") from None
        return f"저장 완료({kind}): {content}"

    @mcp.tool()
    async def search_notes(
        keyword: Annotated[str, Field(min_length=1, max_length=100)],
        ctx: Context,
        days: Annotated[int, Field(ge=1, le=365)] = 30,
    ) -> str:
        """지난 대화에서 저장한 노트를 키워드로 찾는다(최근 days일, 최대 10건)."""
        runtime_of(ctx)
        keyword = keyword.strip()
        if not keyword:
            raise ToolError("검색어가 비어 있습니다.")
        since = utcnow() - timedelta(days=days)
        pattern = f"%{_escape_like(keyword)}%"
        tz = ZoneInfo(app.state.settings.timezone)
        async with app.state.session_factory() as db:
            rows = (
                await db.execute(
                    select(Note)
                    .where(Note.content.like(pattern, escape="\\"), Note.created_at >= since)
                    .order_by(Note.created_at.desc())
                    .limit(_SEARCH_LIMIT)
                )
            ).scalars()
            found = [
                f"{n.created_at.astimezone(tz):%Y-%m-%d} [{n.kind.value}] {n.content}" for n in rows
            ]
        return "\n".join(found) if found else f"'{keyword}'에 해당하는 노트가 없습니다."

    @mcp.tool()
    async def summarize_session(ctx: Context) -> str:
        """이번 대화의 노트 목록과 사용자 발화 수를 돌려준다. 정리 문장은 이 결과로 만든다."""
        runtime = runtime_of(ctx)
        async with app.state.session_factory() as db:
            notes = (
                (
                    await db.execute(
                        select(Note)
                        .where(Note.session_id == runtime.session_id)
                        .order_by(Note.created_at)
                    )
                )
                .scalars()
                .all()
            )
            turns = await db.scalar(
                select(func.count())
                .select_from(Turn)
                .where(Turn.session_id == runtime.session_id, Turn.role == TurnRole.USER)
            )
        lines = [f"사용자 발화 수: {turns}", f"저장한 노트: {len(notes)}개"]
        lines += [f"- [{n.kind.value}] {n.content}" for n in notes]
        return "\n".join(lines)

    @mcp.tool()
    async def pause_session(ctx: Context) -> str:
        """사용자가 '잠깐 쉬자'고 하면 부른다. 이번 답변이 끝난 뒤 대화를 쉬기 상태로 둔다."""
        runtime_of(ctx).requested_status = SessionStatus.PAUSED
        return "이번 답변 뒤 대화를 쉬기 상태로 둡니다. 짧게 인사하세요."

    @mcp.tool()
    async def end_session(ctx: Context) -> str:
        """사용자가 '오늘은 여기까지'라고 하면 부른다. 이번 답변이 끝난 뒤 대화를 마친다."""
        runtime_of(ctx).requested_status = SessionStatus.ENDED
        return "이번 답변 뒤 대화를 마칩니다. 짧게 마무리 인사를 하세요."

    return mcp


class McpAuthMiddleware:
    """대화 세션 토큰이 맞을 때만 MCP 요청을 통과시킨다."""

    def __init__(self, app: ASGIApp, registry: RuntimeRegistry) -> None:
        self.app = app
        self.registry = registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # MCP는 HTTP만 쓴다. 그 밖의 연결은 받지 않는다
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if any(name in headers for name in _FORWARDED_HEADERS):
            # HTTP_PROXY가 루프백까지 가로채도 여기서 막힌다(NO_PROXY에 127.0.0.1 필요)
            logger.warning("MCP request with proxy headers rejected")
            response = error_response(403, "forbidden", "내부 경로입니다.")
            await response(scope, receive, send)
            return
        auth = headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else None
        if self.registry.authenticate(headers.get(SESSION_HEADER), token) is None:
            response = error_response(
                401,
                "unauthorized",
                "대화 세션 토큰이 필요합니다.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def mount_mcp(app) -> MCPServer:
    """MCP 서버를 만들어 /internal/mcp/에 붙인다. 세션 매니저는 앱 lifespan에서 돌린다."""
    mcp = build_mcp_server(app)
    asgi = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,  # 요청마다 독립(대화 상태는 RuntimeRegistry에 있다)
        json_response=True,
        # 모든 요청에 대화 세션 토큰이 필요하므로 Host 검사(DNS 리바인딩 방어)는 끈다
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    app.mount(MOUNT_PATH, McpAuthMiddleware(asgi, app.state.runtimes))
    return mcp
