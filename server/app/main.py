import asyncio
import mimetypes
import weakref
from contextlib import asynccontextmanager

import httpx2
from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette._utils import get_route_path
from starlette.routing import Match, Mount
from starlette.types import Scope

from app.api import barge_in, health, journal, latency, profile, sessions, usage
from app.api.events import register_event_schemas
from app.client_config import load_client_config
from app.config import Settings, settings
from app.db.migrate import upgrade_to_head
from app.db.session import create_engine_for, create_session_factory
from app.errors import install_error_handlers
from app.jobs import extract, idle
from app.llm.claude_cli import ClaudeCliBackend
from app.llm.manager import LlmSessionManager
from app.llm.usage import UsageTracker
from app.mcp.server import mount_mcp
from app.request_context import RequestContextMiddleware, configure_logging
from app.services import conversation
from app.services.runtime import RuntimeRegistry
from app.services.search import TavilySearch
from app.voice.fake import FakeStt, FakeTts
from app.voice.speech import Speech
from app.voice.stt import OpenAiStt
from app.voice.tts import OpenAiTts


class WebMount(Mount):
    """빌드된 웹 앱 마운트. /api 경로는 맡지 않아 라우터의 404·405가 그대로 나간다."""

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        path = get_route_path(scope)  # 프록시 root_path를 뺀 경로
        if path == "/api" or path.startswith("/api/"):
            return Match.NONE, {}
        return super().matches(scope)


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or settings
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app_settings.auto_migrate:
            await upgrade_to_head(app_settings.database_url)
        engine = create_engine_for(app_settings.database_url)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        llm = LlmSessionManager(
            ClaudeCliBackend(app_settings, on_rate_limit=app.state.usage.update),
            idle_timeout_s=app_settings.cli_idle_timeout_s,
            # 턴 시간 초과 처리가 끝날 여유를 더 둔다(스트림을 버린 경우의 안전망)
            stuck_timeout_s=app_settings.cli_turn_timeout_s + 30,
        )
        await llm.start()
        app.state.llm = llm
        # 음성 API(OpenAI) 호출에 같이 쓰는 연결. 아래 정리가 모두 끝난 뒤 닫힌다
        async with httpx2.AsyncClient() as http:
            # 음성 합성 동시 수 제한·안내 캐시(app/voice/speech.py). 세마포어가 서버 루프에 묶이도록
            # 여기서 만든다
            app.state.speech = Speech()
            if app_settings.voice_backend == "fake":
                app.state.stt = FakeStt(app_settings.fake_stt_text)
                app.state.tts = FakeTts()
            else:
                app.state.stt = OpenAiStt.from_settings(http, app_settings)
                app.state.tts = OpenAiTts.from_settings(http, app_settings)
            app.state.search = TavilySearch.from_settings(http, app_settings)
            idle_watch = asyncio.create_task(idle.run(app), name="idle-watch")
            try:
                async with mcp.session_manager.run():
                    yield
            finally:
                idle_watch.cancel()
                await asyncio.wait([idle_watch])
                await conversation.cancel_prepared(app)
                await llm.shutdown()
                # CLI를 닫으면서 끝난 턴이 추출을 띄울 수 있어 그 뒤에 멈춘다
                await extract.cancel_all(app)
                await engine.dispose()

    app = FastAPI(title="TrailTalk", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.client_config = load_client_config(app_settings)  # 틀린 파일이면 시작하지 않는다
    app.state.runtimes = RuntimeRegistry()
    app.state.usage = UsageTracker()  # Claude 구독 사용 한도의 마지막 값(GET /api/usage)
    app.state.prepared = None  # 미리 띄운 CLI(services/conversation.py PreparedSession)
    app.state.prepare_lock = asyncio.Lock()
    app.state.extractions = {}  # 세션별 추출 작업(app/jobs/extract.py)
    app.state.extract_writes = set()  # 취소에서 보호하는 추출 결과 쓰기
    app.state.extract_closed = False
    # 예전 형식 일지를 새 형식으로 '다시 정리'해 달라는 요청(S3-24). 이 요청으로 시작한 정리 한 번만
    # 노트를 새로 넣지 않는다(오프라인 큐 등 다른 이유로 다시 도는 정리는 노트를 그대로 뽑는다)
    app.state.reformat_requests = set()
    # 런타임 없는 대화의 기록만 남기기 잠금(services/conversation.py, 약한 참조)
    app.state.record_locks = weakref.WeakValueDictionary()
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    register_event_schemas(app)

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(sessions.router)
    api.include_router(profile.router)
    api.include_router(journal.router)
    api.include_router(latency.router)
    api.include_router(barge_in.router)
    api.include_router(usage.router)

    app.include_router(api)
    mcp = mount_mcp(app)  # /internal/mcp/ (웹 정적 마운트보다 먼저)

    # 빌드된 웹 앱이 있으면 같은 서버에서 정적 파일로 서빙한다(설계서 5장 배포).
    # 라우터는 모두 이 마운트보다 먼저 등록해야 한다(뒤에 붙인 라우트는 가려진다).
    if app_settings.web_dist_dir.is_dir():
        # PWA manifest·음성 감지 wasm의 형식을 OS의 MIME 표에 기대지 않고 정한다(폰 모드, S3-14)
        mimetypes.add_type("application/manifest+json", ".webmanifest")
        mimetypes.add_type("application/wasm", ".wasm")
        static = StaticFiles(directory=app_settings.web_dist_dir, html=True)
        app.router.routes.append(WebMount("/", app=static, name="web"))
    return app


app = create_app()
