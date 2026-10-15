"""보이스 고르기용 샘플 MP3를 만든다(실제 OpenAI TTS 호출, 과금).

(cd server && uv run python -m tests.voice_samples)                 # 기본 보이스 6종
(cd server && uv run python -m tests.voice_samples marin coral)     # 원하는 보이스만

결과는 server/data/voice-samples/<보이스>.mp3(커밋하지 않음). 문장과 말투 지시는
현재 페르소나 YAML(examples, voice.instructions, voice.speaking_rate)을 쓴다.
"""

import asyncio
import sys

import httpx2

from app.config import SERVER_DIR, Settings
from app.persona.loader import load_persona
from app.voice.tts import OpenAiTts

VOICES = ("marin", "cedar", "coral", "nova", "shimmer", "sage")
OUT_DIR = SERVER_DIR / "data" / "voice-samples"


async def main(voices: tuple[str, ...]) -> None:
    settings = Settings()
    persona = load_persona(settings.persona_dir, settings.default_persona).persona
    text = " ".join(e.replace("{호칭}", "다니엘님") for e in persona.examples)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"문장: {text}\n말투 지시: {persona.voice.instructions}\n")
    async with httpx2.AsyncClient() as client:
        tts = OpenAiTts.from_settings(client, settings)
        for name in voices:
            voice = persona.voice.model_copy(update={"tts_voice": name})
            path = OUT_DIR / f"{name}.mp3"
            path.write_bytes(await tts.synthesize(text, voice))
            print(f"{name}: {path}")


if __name__ == "__main__":
    asyncio.run(main(tuple(sys.argv[1:]) or VOICES))
