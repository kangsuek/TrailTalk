from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import health
from app.config import settings

app = FastAPI(title="TrailTalk")
app.include_router(health.router, prefix="/api")

# 빌드된 웹 앱이 있으면 같은 서버에서 정적 파일로 서빙한다(설계서 5장 배포).
if settings.web_dist_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.web_dist_dir, html=True), name="web")
