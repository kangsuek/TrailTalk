"""실제 OpenAI 음성 API 왕복 테스트. 과금되므로 RUN_REAL_OPENAI=1일 때만 실행한다.

(cd server && RUN_REAL_OPENAI=1 uv run pytest tests/test_voice_real.py -q)

TTS로 문장 하나를 만들고, 웹(webm/opus)·ogg/opus 업로드 형식으로 바꿔
각각 음성 인식에 넣는다. 호출 수: TTS 1회, STT 2회.
"""

import os
import subprocess

import httpx2
import pytest

from app.config import Settings
from app.persona.loader import load_persona
from app.voice.audio import prepare_for_stt
from app.voice.stt import OpenAiStt
from app.voice.tts import OpenAiTts

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_REAL_OPENAI") != "1", reason="RUN_REAL_OPENAI=1일 때만"
)

SENTENCE = "오늘은 북한산 둘레길을 걸으면서 새 앱 아이디어를 정리했어요."


def encode(settings: Settings, mp3: bytes, fmt: str) -> bytes:
    return subprocess.run(
        [settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-f", fmt, "pipe:1"],
        input=mp3,
        check=True,
        capture_output=True,
    ).stdout  # fmt: skip


async def test_tts_then_stt_round_trip():
    settings = Settings()
    assert settings.openai_api_key, ".env에 OPENAI_API_KEY(또는 WHISPER_API_KEY)가 필요합니다"
    voice = load_persona(settings.persona_dir, settings.default_persona).persona.voice
    async with httpx2.AsyncClient() as client:
        mp3 = await OpenAiTts.from_settings(client, settings).synthesize(SENTENCE, voice)
        assert len(mp3) > 1000
        stt = OpenAiStt.from_settings(client, settings)
        for content_type, fmt in [("audio/webm;codecs=opus", "webm"), ("audio/ogg", "ogg")]:
            audio = await prepare_for_stt(
                encode(settings, mp3, fmt),
                content_type,
                max_bytes=settings.stt_max_bytes,
                ffmpeg_path=settings.ffmpeg_path,
                timeout_s=settings.ffmpeg_timeout_s,
            )
            text = await stt.transcribe(audio, prompt="산책하며 제니와 나누는 대화")
            print(f"{fmt}: {text}")
            for word in ("북한산", "둘레길", "아이디어"):
                assert word in text, text
