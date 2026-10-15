"""음성 합성(계획서 S3-02, 결정 D3: OpenAI TTS). 문장 하나를 MP3로 만든다."""

import re
import unicodedata
from typing import Protocol

import httpx2
from pydantic import SecretStr

from app.config import Settings
from app.persona.schema import VoiceStyle
from app.voice import openai_http

_MD_LINK = re.compile(r"\[([^\]]*)\]\((?:[^()\s]|\([^()\s]*\))*\)")
# URL 글자(괄호 제외)로 이어지고 문장부호로 끝나지 않는다("example.com에서", "(www.a.com)")
_URL = re.compile(r"(?:https?://|www\.)[A-Za-z0-9_\-.~:/?#@!$&'*+,;=%]*[A-Za-z0-9_/#=&%-]")
# 숫자 사이의 *(곱하기, 3*4)는 남긴다
_MD_MARKS = re.compile(r"(?<!\d)\*+|\*+(?!\d)|__+|`+|^#{1,6}\s*|^>\s*", re.MULTILINE)
_SPACES = re.compile(r"[ \t\u00a0]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,!?…~])")
_EMPTY_PARENS = re.compile(r"\(\s*\)")


def speech_text(sentence: str) -> str:
    """읽을 문장만 남긴다: 마크다운 표시·링크 주소·URL·이모지를 지운다.

    화면에 보이는 문장(sentence 이벤트의 text)은 그대로 두고 음성에만 쓴다."""
    text = _MD_LINK.sub(r"\1", sentence)
    text = _URL.sub("", text)
    text = _MD_MARKS.sub("", text)
    text = "".join(c for c in text if not _is_symbol(c))
    text = _EMPTY_PARENS.sub("", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    return _SPACES.sub(" ", text).strip()


_UNIT_SYMBOLS = "°℃℉"


def _is_symbol(char: str) -> bool:
    """이모지·기호·이모지 이체 선택자(U+FE0F 등). 단위 기호(℃, °, ㎞ 등)는 남긴다."""
    if char in _UNIT_SYMBOLS or "\u3300" <= char <= "\u33ff":  # CJK 호환 단위(㎞, ㎏)
        return False
    return "\ufe00" <= char <= "\ufe0f" or unicodedata.category(char) in {"So", "Cf", "Sk", "Cn"}


def has_speech(text: str) -> bool:
    """글자나 숫자가 하나라도 있어야 읽을 것이 있다(문장부호만 남은 경우 제외)."""
    return any(c.isalnum() for c in text)


class TtsProvider(Protocol):
    async def synthesize(self, text: str, voice: VoiceStyle) -> bytes:
        """MP3. 읽을 글자가 없으면 빈 bytes."""
        ...


class OpenAiTts:
    def __init__(
        self,
        client: httpx2.AsyncClient,
        *,
        api_key: SecretStr | None,
        base_url: str,
        model: str,
        timeout_s: float,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._timeout_s = timeout_s

    @classmethod
    def from_settings(cls, client: httpx2.AsyncClient, settings: Settings) -> "OpenAiTts":
        return cls(
            client,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.tts_model,
            timeout_s=settings.tts_timeout_s,
        )

    async def synthesize(self, text: str, voice: VoiceStyle) -> bytes:
        spoken = speech_text(text)
        if not has_speech(spoken):
            return b""
        response = await openai_http.post(
            self._client,
            base_url=self._base_url,
            api_key=self._api_key,
            path="/audio/speech",
            timeout_s=self._timeout_s,
            error_prefix="tts",
            json={
                "model": self._model,
                "voice": voice.tts_voice,
                "input": spoken,
                "instructions": voice.instructions,
                "speed": voice.speaking_rate,
                "response_format": "mp3",
            },
        )
        if not response.content:
            raise openai_http.failed("tts")
        return response.content
