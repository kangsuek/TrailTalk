from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = SERVER_DIR.parent


class Settings(BaseSettings):
    """서버 설정. 값은 환경 변수 또는 저장소 루트의 .env에서 읽는다."""

    model_config = SettingsConfigDict(env_file=REPO_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{SERVER_DIR / 'trailtalk.db'}"
    persona_dir: Path = SERVER_DIR / "personas"
    default_persona: str = "jenny"
    web_dist_dir: Path = REPO_DIR / "web" / "dist"


settings = Settings()
