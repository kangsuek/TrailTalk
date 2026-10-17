import os
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = SERVER_DIR.parent


class Settings(BaseSettings):
    """서버 설정. 값은 환경 변수 또는 저장소 루트의 .env에서 읽는다."""

    model_config = SettingsConfigDict(
        env_file=REPO_DIR / ".env",
        extra="ignore",
        populate_by_name=True,
        # 빈 값(KEY=)은 없는 것으로 본다. 셸의 빈 환경 변수가 .env 값을 가리지 않게 한다
        env_ignore_empty=True,
    )

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
    # 화면이 열릴 때 미리 띄운 CLI(대화 시작 대기 단축)를 쓰지 않으면 이 시간 뒤 닫는다
    session_prepare_ttl_s: float = 300
    # CLI가 앱 도구 MCP 서버(/internal/mcp/)에 접속할 이 서버의 주소
    internal_base_url: str = "http://127.0.0.1:8000"
    # 세션 종료 추출(일지 정리) CLI 한 번의 시간 제한과, 끝내기 API가 정리를 기다리는 최대 시간
    # (넘으면 그때까지 저장된 개수로 마무리 멘트를 만들고 정리는 백그라운드에서 계속한다)
    extract_timeout_s: float = 60
    extract_wait_s: float = 45
    # 일지 인용(S3-23)의 제목이 도메인뿐이면(검색 결과가 기사 제목을 주지 않음) 정리할 때
    # 그 페이지를 열어 기사 제목을 읽는다. 테스트·E2E는 끈다(외부 네트워크)
    fetch_source_titles: bool = True
    # 무발화 타임아웃(app/jobs/idle.py): 마지막 턴 뒤 이 시간이 지나면 서버가 세션을 끝낸다
    idle_timeout_s: float = 1800
    idle_check_interval_s: float = 60
    # 다음 세션 프롬프트의 기억 블록 예산(글자 수, app/persona/memory.py)
    memory_budget_chars: int = 1200
    # 자식 CLI에 추가로 넘길 환경 변수 이름 패턴(기본 허용 목록 외). 테스트의 가짜 CLI용
    cli_env_passthrough: tuple[str, ...] = ()

    # 음성 인식·합성(OpenAI, 결정 D2·D3). 키가 없어도 서버는 시작하고 음성 호출만 실패한다.
    # 예전 이름 WHISPER_API_KEY도 받는다(OPENAI_API_KEY가 비어 있을 때만 쓴다)
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    whisper_api_key: SecretStr | None = Field(default=None, validation_alias="WHISPER_API_KEY")
    openai_base_url: str = "https://api.openai.com/v1"
    stt_model: str = "gpt-transcribe"
    stt_language: str = "ko"
    stt_timeout_s: float = 15
    stt_max_bytes: int = 10 * 1024 * 1024
    tts_model: str = "gpt-4o-mini-tts"
    tts_timeout_s: float = 15
    # openai: 실제 API, fake: 가짜(app/voice/fake.py, run.sh --fake·E2E용, 과금 없음)
    voice_backend: Literal["openai", "fake"] = "openai"
    # 가짜 음성 인식이 돌려줄 문장(업로드가 b"FAKE_STT:"로 시작하면 그 뒤 글을 쓴다)
    fake_stt_text: str = "오늘 산책하면서 생각난 아이디어가 있어"
    # 업로드 오디오 변환(app/voice/audio.py)
    ffmpeg_path: str = "ffmpeg"
    ffmpeg_timeout_s: float = 10
    # 음성 원본 보관(S3-05): 프로필 keep_audio가 켜져 있으면 음성 턴 녹음을 여기에 두고,
    # audio_retention_days가 지나면 지운다(app/jobs/audio.py)
    audio_dir: Path = SERVER_DIR / "data" / "audio"
    audio_retention_days: int = Field(default=30, gt=0)

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"알 수 없는 시간대: {value}") from exc
        return value

    @field_validator("ffmpeg_path")
    @classmethod
    def _expand_home(cls, value: str) -> str:
        # 실행 파일 경로의 ~는 셸이 아닌 곳(create_subprocess_exec)에서 풀리지 않는다
        return os.path.expanduser(value)

    @model_validator(mode="after")
    def _voice_key(self) -> "Settings":
        """빈 키 줄(OPENAI_API_KEY=)은 없는 것으로 보고, 비어 있지 않은 첫 키를 쓴다."""
        keys = (self.openai_api_key, self.whisper_api_key)
        values = (k.get_secret_value().strip() for k in keys if k)
        self.openai_api_key = next((SecretStr(v) for v in values if v), None)
        return self

    persona_dir: Path = SERVER_DIR / "personas"
    default_persona: str = "jenny"
    timezone: str = "Asia/Seoul"
    web_dist_dir: Path = REPO_DIR / "web" / "dist"
    # 클라이언트 설정값 기본값(app/client_config.py, /api/profile의 client)
    client_defaults_path: Path = REPO_DIR / "shared" / "client-defaults.json"


settings = Settings()
