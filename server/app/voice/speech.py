"""대화에서 쓰는 음성 합성 도우미(계획서 S3-03).

합성 실패는 대화를 멈추지 않는다: 로그를 남기고 None을 돌려주면 클라이언트는 그 문장을 글로
보이거나 기기 TTS로 대신한다. 동시 합성 수를 제한하고, 늘 같은 안내 문구는 결과를 캐시한다.
"""

import asyncio
import base64
import logging

from fastapi import FastAPI

from app.errors import AppError
from app.persona.schema import VoiceStyle

logger = logging.getLogger("trailtalk.voice")

MAX_CONCURRENT = 3


class Speech:
    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self._cache: dict[tuple[str, VoiceStyle], str] = {}

    async def synthesize(self, app: FastAPI, text: str, voice: VoiceStyle) -> str | None:
        """문장의 MP3(base64). 읽을 글자가 없거나 실패하면 None."""
        async with self._semaphore:
            try:
                audio = await app.state.tts.synthesize(text, voice)
            except AppError as exc:
                logger.warning("음성 합성 실패(code=%s): %s", exc.code, exc.message)
                return None
            except Exception:
                logger.exception("음성 합성 중 예외")
                return None
        return base64.b64encode(audio).decode("ascii") if audio else None

    async def cached(self, app: FastAPI, text: str, voice: VoiceStyle) -> str | None:
        """같은 문구(검색 안내 등)는 한 번만 합성한다. 실패는 캐시하지 않는다."""
        key = (text, voice)
        if key not in self._cache:
            audio = await self.synthesize(app, text, voice)
            if audio is None:
                return None
            self._cache[key] = audio
        return self._cache[key]
