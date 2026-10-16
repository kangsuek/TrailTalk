import json
import logging

import httpx2
import pytest
from pydantic import SecretStr

from app.errors import AppError
from app.persona.schema import VoiceStyle
from app.voice.tts import OpenAiTts, speech_text

KEY = "sk-test-secret-key"
VOICE = VoiceStyle(
    tts_voice="coral", speaking_rate=1.05, instructions="밝게 말해요", search_notice="찾아볼게요"
)
MP3 = b"ID3fake-mp3"


def make_tts(handler, *, api_key=KEY, model="gpt-4o-mini-tts") -> OpenAiTts:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return OpenAiTts(
        client,
        api_key=SecretStr(api_key) if api_key else None,
        base_url="https://api.test/v1",
        model=model,
        timeout_s=5,
    )


async def test_synthesize_sends_voice_settings():
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx2.Response(200, content=MP3, headers={"content-type": "audio/mpeg"})

    audio = await make_tts(handler).synthesize("**좋아요!** 가 봐요 😊", VOICE)
    assert audio == MP3
    request = seen["request"]
    assert str(request.url) == "https://api.test/v1/audio/speech"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "model": "gpt-4o-mini-tts",
        "voice": "coral",
        "input": "좋아요! 가 봐요",
        "instructions": "밝게 말해요",
        "speed": 1.05,
        "response_format": "mp3",
    }


async def test_older_models_get_no_instructions():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, content=MP3)

    await make_tts(handler, model="tts-1").synthesize("안녕", VOICE)
    assert seen["body"]["model"] == "tts-1"
    assert "instructions" not in seen["body"]


@pytest.mark.parametrize("text", ["", "   ", "😊", "https://example.com", "**!**"])
async def test_nothing_to_say_skips_request(text):
    def handler(request):
        raise AssertionError("요청하면 안 된다")

    assert await make_tts(handler).synthesize(text, VOICE) == b""


async def test_missing_key_is_unavailable():
    with pytest.raises(AppError) as excinfo:
        await make_tts(lambda r: httpx2.Response(200, content=MP3), api_key=None).synthesize(
            "안녕", VOICE
        )
    assert excinfo.value.code == "voice_unavailable"


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "voice_unavailable"), (400, "tts_failed"), (429, "tts_failed"), (503, "tts_failed")],
)
async def test_error_status_is_mapped(status, code, caplog):
    def handler(request):
        return httpx2.Response(status, json={"error": {"message": "boom"}})

    with caplog.at_level(logging.WARNING), pytest.raises(AppError) as excinfo:
        await make_tts(handler).synthesize("안녕", VOICE)
    assert excinfo.value.code == code
    assert KEY not in caplog.text


async def test_exhausted_quota_is_unavailable():
    def handler(request):
        return httpx2.Response(429, json={"error": {"type": "insufficient_quota"}})

    with pytest.raises(AppError) as excinfo:
        await make_tts(handler).synthesize("안녕", VOICE)
    assert (excinfo.value.code, excinfo.value.status_code) == ("voice_unavailable", 503)


async def test_auth_error_body_is_not_logged(caplog):
    def handler(request):
        body = {
            "error": {
                "message": "Incorrect API key provided: sk-proj-****abcd",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
            }
        }
        return httpx2.Response(401, json=body)  # fmt: skip

    with caplog.at_level(logging.WARNING), pytest.raises(AppError):
        await make_tts(handler).synthesize("안녕", VOICE)
    assert "abcd" not in caplog.text
    assert "invalid_api_key" in caplog.text


async def test_timeout_is_mapped():
    def handler(request):
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(AppError) as excinfo:
        await make_tts(handler).synthesize("안녕", VOICE)
    assert (excinfo.value.code, excinfo.value.status_code) == ("tts_timeout", 504)


async def test_empty_audio_is_failed():
    with pytest.raises(AppError) as excinfo:
        await make_tts(lambda r: httpx2.Response(200, content=b"")).synthesize("안녕", VOICE)
    assert excinfo.value.code == "tts_failed"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**좋아요!** 다음이에요.", "좋아요! 다음이에요."),
        ("__굵게__ `코드` 써요", "굵게 코드 써요"),
        (
            "자세한 건 [나무위키](https://namu.wiki/w/a_(b)) 참고해요.",
            "자세한 건 나무위키 참고해요.",
        ),
        ("출처는 https://example.com/x?y=1 이에요.", "출처는 이에요."),
        ("링크(www.example.com)예요.", "링크예요."),
        ("www.naver.com에서 봤어요.", "에서 봤어요."),
        ("주소는 https://a.com/x_y.", "주소는."),
        ("반가워요! 😊 🚶‍♀️", "반가워요!"),
        ("3*4는 12예요.", "3*4는 12예요."),
        ("기온이 25℃예요. ☀️", "기온이 25℃예요."),
        ("5㎞ 남았고 25°C예요.", "5㎞ 남았고 25°C예요."),
        ("오후 3시 ~ 5시예요.", "오후 3시 ~ 5시예요."),
        ("- 사과 고르기", "사과 고르기"),
        ("• 둘째 항목이에요.", "둘째 항목이에요."),
        ("* 사과\n* 배", "사과\n배"),
        ("기온은 -3도예요.", "기온은 -3도예요."),
        ("좋아요 !", "좋아요!"),
        ("# 제목", "제목"),
        ("평범한 문장이에요.", "평범한 문장이에요."),
    ],
)
def test_speech_text(text, expected):
    assert speech_text(text) == expected


def test_app_exposes_tts(client):
    assert isinstance(client.app.state.tts, OpenAiTts)
