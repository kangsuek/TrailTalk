"""GET/PUT /api/profile(S1-08)."""

import pytest

from app.db.models import Persona


def test_get_creates_default_profile_and_syncs_persona(client):
    response = client.get("/api/profile")
    assert response.status_code == 200
    assert response.json() == {
        "nickname": None,
        "interests": [],
        "persona_id": "jenny",
        "voice": None,
        "keep_audio": False,
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
