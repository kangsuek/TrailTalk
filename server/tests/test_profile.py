"""GET/PUT /api/profile(S1-08)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_DIR
from app.db.models import Persona
from app.errors import AppError
from app.main import create_app


def _repo_client_defaults() -> dict:
    return json.loads((REPO_DIR / "shared" / "client-defaults.json").read_text(encoding="utf-8"))


def test_get_creates_default_profile_and_syncs_persona(make_settings):
    # 셸의 IDLE_TIMEOUT_S에 흔들리지 않게 기본값을 명시한다
    with TestClient(create_app(make_settings(idle_timeout_s=1800))) as client:
        _check_default_profile(client)


def _check_default_profile(client):
    response = client.get("/api/profile")
    assert response.status_code == 200
    assert response.json() == {
        "nickname": None,
        "interests": [],
        "persona_id": "jenny",
        "voice": None,
        "speaking_rate": None,
        "email": None,
        "mail_ready": False,
        "keep_audio": False,
        "chat_model": None,
        "default_chat_model": "sonnet",
        "client": _repo_client_defaults(),
    }

    async def persona():
        async with client.app.state.session_factory() as db:
            return await db.get(Persona, "jenny")

    row = client.portal.call(persona)
    assert row.yaml_path.endswith("jenny.yaml") and len(row.version) == 16


def test_put_updates_only_sent_fields(client):
    response = client.put(
        "/api/profile", json={"nickname": "  민수 ", "interests": ["등산", "앱", "등산"]}
    )
    assert response.status_code == 200
    assert response.json()["nickname"] == "민수"
    assert response.json()["interests"] == ["등산", "앱"]

    response = client.put("/api/profile", json={"keep_audio": True})
    body = response.json()
    assert body["nickname"] == "민수" and body["keep_audio"] is True
    assert client.get("/api/profile").json() == body

    assert client.put("/api/profile", json={"nickname": None}).json()["nickname"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"nickname": ""},
        {"nickname": "   "},
        {"nickname": "민\n수"},
        {"nickname": "가" * 21},
        {"interests": ["x"] * 11},
        {"interests": ["가" * 31]},
        {"persona_id": "../etc"},
        {"unknown": 1},
        {"voice": "robot"},
        {"speaking_rate": 0.5},
        {"speaking_rate": 2},
        {"chat_model": "gpt-4"},
        {"chat_model": "claude-opus"},
    ],
)
def test_put_validation(client, body):
    response = client.put("/api/profile", json=body)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_error"


def test_put_unknown_persona_is_404(client):
    response = client.put("/api/profile", json={"persona_id": "nobody"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "persona_not_found"
    assert client.get("/api/profile").json()["persona_id"] == "jenny"


async def test_profile_created_concurrently_keeps_outer_transaction(db_session):
    """다른 요청이 먼저 프로필을 만들었어도 바깥 트랜잭션의 객체를 잃지 않는다(세이브포인트)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.models import ConversationSession, UserProfile
    from app.services.profile import get_profile

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with factory() as other:
        other.add(UserProfile(id=1, nickname="먼저"))
        await other.commit()

    convo = ConversationSession()
    db_session.add(convo)
    await db_session.flush()
    original = db_session.get
    calls = []

    async def first_misses(cls, ident, **kwargs):
        calls.append(ident)
        return None if len(calls) == 1 else await original(cls, ident, **kwargs)

    db_session.get = first_misses  # 처음 조회 때는 아직 없던 것처럼
    profile = await get_profile(db_session)
    assert profile.nickname == "먼저"
    await db_session.commit()
    assert convo.mode.value == "text"  # rollback으로 만료되지 않았다


def test_client_config_follows_server_idle_timeout(make_settings):
    with TestClient(create_app(make_settings(idle_timeout_s=600))) as client:
        body = client.get("/api/profile").json()
        assert body["client"]["session"] == {"idle_timeout_minutes": 10}
        assert (
            client.put("/api/profile", json={"keep_audio": True}).json()["client"] == body["client"]
        )


def test_client_config_is_read_only(client):
    response = client.put("/api/profile", json={"client": {"vad": {}}})
    assert response.status_code == 422


async def test_persona_row_inserted_concurrently_is_reused(db_session, make_settings, monkeypatch):
    """다른 요청이 같은 페르소나 행을 먼저 넣었어도 실패하지 않는다(새 DB에서 동시에 부를 때)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.services.profile import sync_persona

    settings = make_settings()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with factory() as other:
        other.add(Persona(id="jenny", yaml_path="old.yaml", version="old"))
        await other.commit()

    # 이 요청은 행이 없다고 본 뒤(첫 조회) 넣으려 한다
    original = db_session.get
    calls = 0

    async def first_get_misses(entity, ident, **kwargs):
        nonlocal calls
        calls += 1
        return None if calls == 1 else await original(entity, ident, **kwargs)

    monkeypatch.setattr(db_session, "get", first_get_misses)
    loaded = await sync_persona(db_session, settings, "jenny")
    await db_session.commit()
    row = await original(Persona, "jenny")
    assert row.version == loaded.version and row.yaml_path == str(loaded.path)


def test_put_voice_and_rate_and_reset(client):
    body = client.put("/api/profile", json={"voice": "coral", "speaking_rate": 0.85}).json()
    assert (body["voice"], body["speaking_rate"]) == ("coral", 0.85)
    body = client.put("/api/profile", json={"voice": None, "speaking_rate": None}).json()
    assert (body["voice"], body["speaking_rate"]) == (None, None)  # 캐릭터 기본으로


def test_put_chat_model_and_reset(client):
    body = client.get("/api/profile").json()
    assert body["chat_model"] is None and body["default_chat_model"] == "sonnet"  # 서버 기본값
    assert client.put("/api/profile", json={"chat_model": "opus"}).json()["chat_model"] == "opus"
    assert client.put("/api/profile", json={"chat_model": None}).json()["chat_model"] is None


def test_voices_lists_openai_voices_and_persona_defaults(client):
    body = client.get("/api/voices").json()
    assert "nova" in body["voices"] and "coral" in body["voices"]
    assert body["default_voice"] == "nova"  # 페르소나 YAML
    assert body["min_rate"] == 0.75 and body["max_rate"] == 1.5
    assert body["min_rate"] <= body["default_rate"] <= body["max_rate"]


def test_voice_sample_is_mp3_and_cached(make_settings):
    with TestClient(create_app(make_settings(voice_backend="fake"))) as client:
        calls = []
        tts = client.app.state.tts
        original = tts.synthesize

        async def counting(text, voice):
            calls.append((voice.tts_voice, voice.speaking_rate))
            return await original(text, voice)

        tts.synthesize = counting
        for _ in range(2):
            response = client.get("/api/voices/coral/sample?rate=1.2")
            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/mpeg"
            assert response.content
        assert calls == [("coral", 1.2)]  # 두 번째는 캐시
        assert client.get("/api/voices/robot/sample").status_code == 422
        assert client.get("/api/voices/coral/sample?rate=3").status_code == 422


def test_voice_sample_unavailable_is_503(make_settings):
    with TestClient(create_app(make_settings(voice_backend="fake"))) as client:

        async def broken(text, voice):
            raise AppError("voice_unavailable", "키 없음", 503)

        client.app.state.tts.synthesize = broken
        response = client.get("/api/voices/coral/sample")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "voice_unavailable"


def test_voice_sample_rate_is_rounded_for_cache(make_settings):
    with TestClient(create_app(make_settings(voice_backend="fake"))) as client:
        rates = []
        tts = client.app.state.tts
        original = tts.synthesize

        async def counting(text, voice):
            rates.append(voice.speaking_rate)
            return await original(text, voice)

        tts.synthesize = counting
        for rate in ("0.85", "0.851", "0.8501"):
            assert client.get(f"/api/voices/coral/sample?rate={rate}").status_code == 200
        assert rates == [0.85]


def test_unknown_stored_voice_falls_back_to_persona(client):
    async def store():
        from app.services.profile import get_profile

        async with client.app.state.session_factory() as db:
            (await get_profile(db)).voice = "옛날 자유 문자열"
            await db.commit()

    client.portal.call(store)
    assert client.get("/api/profile").json()["voice"] is None


async def test_speech_cache_keeps_recent_items_only():
    from types import SimpleNamespace

    from app.persona.schema import VoiceStyle
    from app.voice import speech as speech_module

    calls = []

    class Tts:
        async def synthesize(self, text, voice):
            calls.append(text)
            return b"mp3"

    app = SimpleNamespace(state=SimpleNamespace(tts=Tts()))
    voice = VoiceStyle(
        tts_voice="nova", speaking_rate=1.0, instructions="밝게", search_notice="잠깐"
    )
    cache = speech_module.Speech()
    for i in range(speech_module.MAX_CACHED + 1):
        await cache.cached(app, f"문구{i}", voice)
    await cache.cached(app, f"문구{speech_module.MAX_CACHED}", voice)  # 최근 것은 캐시에 있다
    await cache.cached(app, "문구0", voice)  # 가장 오래된 것은 밀려났다
    assert calls.count(f"문구{speech_module.MAX_CACHED}") == 1
    assert calls.count("문구0") == 2


def test_put_email_and_reset(client):
    body = client.put("/api/profile", json={"email": "  me@example.com "}).json()
    assert body["email"] == "me@example.com"
    assert client.put("/api/profile", json={"nickname": "민수"}).json()["email"] == "me@example.com"
    assert client.put("/api/profile", json={"email": None}).json()["email"] is None


@pytest.mark.parametrize(
    "email",
    [
        "",
        "plain",
        "a@b",
        "a b@example.com",
        "한글@example.com",
        "a@example.com\nBcc: x@example.com",
        "x" * 250 + "@a.co",
    ],
)
def test_put_rejects_bad_email(client, email):
    assert client.put("/api/profile", json={"email": email}).status_code == 422
    assert client.get("/api/profile").json()["email"] is None


def test_mail_ready_follows_smtp_settings(make_settings):
    settings = make_settings(smtp_host="smtp.example.com", smtp_user="bot@example.com")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/profile").json()["mail_ready"] is True
