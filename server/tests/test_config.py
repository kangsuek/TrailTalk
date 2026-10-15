import os

import pytest

from app.config import Settings


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WHISPER_API_KEY", raising=False)
    monkeypatch.delenv("FFMPEG_PATH", raising=False)

    def _write(text: str) -> Settings:
        path = tmp_path / ".env"
        path.write_text(text, encoding="utf-8")
        return Settings(_env_file=path)

    return _write


def key(settings: Settings) -> str | None:
    return settings.openai_api_key.get_secret_value() if settings.openai_api_key else None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("OPENAI_API_KEY=sk-new\n", "sk-new"),
        ("WHISPER_API_KEY=sk-old\n", "sk-old"),
        # 새 예시대로 빈 OPENAI_API_KEY 줄이 있어도 예전 이름의 키를 쓴다
        ("OPENAI_API_KEY=\nWHISPER_API_KEY=sk-old\n", "sk-old"),
        ("OPENAI_API_KEY=sk-new\nWHISPER_API_KEY=sk-old\n", "sk-new"),
        ("OPENAI_API_KEY=\nWHISPER_API_KEY=\n", None),
        ("OPENAI_API_KEY=   \n", None),
        ("", None),
    ],
)
def test_voice_key_uses_first_non_empty(env_file, text, expected):
    assert key(env_file(text)) == expected


def test_key_is_trimmed(env_file):
    assert key(env_file("OPENAI_API_KEY=  sk-new  \n")) == "sk-new"


def test_empty_shell_variable_does_not_hide_dotenv_key(env_file, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("WHISPER_API_KEY", "")
    assert key(env_file("OPENAI_API_KEY=sk-dotenv\n")) == "sk-dotenv"


def test_init_argument_wins(env_file, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    assert key(Settings(_env_file=None, openai_api_key="sk-arg")) == "sk-arg"


def test_ffmpeg_path_expands_home(env_file):
    settings = env_file("FFMPEG_PATH=~/.local/bin/ffmpeg\n")
    assert settings.ffmpeg_path == os.path.expanduser("~/.local/bin/ffmpeg")
    assert not settings.ffmpeg_path.startswith("~")
