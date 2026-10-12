from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = SERVER_DIR.parent


class Settings(BaseSettings):
    """서버 설정. 값은 환경 변수 또는 저장소 루트의 .env에서 읽는다."""

    model_config = SettingsConfigDict(env_file=REPO_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite+aiosqlite:///{SERVER_DIR / 'trailtalk.db'}"
    log_level: str = "INFO"
    # 앱 시작 때 Alembic 마이그레이션을 head까지 적용한다
    auto_migrate: bool = True

    # Claude CLI (설계서 4.9, docs/spikes/claude-cli.md)
    claude_cli_path: str = "claude"
    claude_code_oauth_token: SecretStr | None = None  # .env의 CLAUDE_CODE_OAUTH_TOKEN
    llm_chat_model: str = "sonnet"
    llm_light_model: str = "haiku"
    cli_work_dir: Path = SERVER_DIR / "data" / "cli-sessions"
    cli_idle_timeout_s: float = 600
    cli_turn_timeout_s: float = 120
    # 자식 CLI에 추가로 넘길 환경 변수 이름 패턴(기본 허용 목록 외). 테스트의 가짜 CLI용
    cli_env_passthrough: tuple[str, ...] = ()

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"알 수 없는 시간대: {value}") from exc
        return value

    persona_dir: Path = SERVER_DIR / "personas"
    default_persona: str = "jenny"
    timezone: str = "Asia/Seoul"
    web_dist_dir: Path = REPO_DIR / "web" / "dist"


settings = Settings()
