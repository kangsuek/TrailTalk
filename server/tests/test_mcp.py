import pytest

from app.db.models import ConversationSession, Note, SessionStatus, Turn, TurnRole
from app.mcp.server import mcp_client_config


@pytest.fixture
def mcp(client):
    """대화 세션 하나와 그 토큰으로 MCP 도구를 부르는 헬퍼."""
    app = client.app

    async def make_session():
        async with app.state.session_factory() as db:
            session = ConversationSession()
            db.add(session)
            await db.flush()
            turn = Turn(session_id=session.id, seq=1, role=TurnRole.USER, text="이거 저장해줘")
            db.add(turn)
            await db.commit()
            return session.id, turn.id

    session_id, turn_id = client.portal.call(make_session)
    runtime = app.state.runtimes.ensure(session_id)
    runtime.current_user_turn_id = turn_id

    class Mcp:
        runtime_ = runtime

        @staticmethod
        def request(
            method: str,
            params: dict | None = None,
            token: str | None = None,
            extra_headers: dict | None = None,
        ):
            headers = {
                "Authorization": f"Bearer {token or runtime.token}",
                "X-TrailTalk-Session": session_id,
                "Accept": "application/json, text/event-stream",
                **(extra_headers or {}),
            }
            body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
            return client.post("/internal/mcp/", headers=headers, json=body)

        @classmethod
        def call(cls, name: str, **arguments) -> dict:
            response = cls.request("tools/call", {"name": name, "arguments": arguments})
            assert response.status_code == 200, response.text
            return response.json()["result"]

        @staticmethod
        def notes() -> list[Note]:
            async def load():
                from sqlalchemy import select

                async with app.state.session_factory() as db:
                    return list((await db.execute(select(Note))).scalars())

            return client.portal.call(load)

        @staticmethod
        def nickname() -> str | None:
            async def load():
                from app.services.profile import get_profile

                async with app.state.session_factory() as db:
                    return (await get_profile(db)).nickname

            return client.portal.call(load)

    Mcp.session_id = session_id
    Mcp.turn_id = turn_id
    return Mcp


def text_of(result: dict) -> str:
    return result["content"][0]["text"]


def test_lists_app_tools(mcp):
    tools = mcp.request("tools/list").json()["result"]["tools"]
    assert [t["name"] for t in tools] == [
        "save_note",
        "search_notes",
        "summarize_session",
        "pause_session",
        "set_nickname",
        "end_session",
    ]


def test_rejects_missing_or_wrong_token(mcp, client):
    assert mcp.request("tools/list", token="wrong").status_code == 401
    response = client.post(
        "/internal/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.json()["error"]["request_id"]
    assert response.headers["www-authenticate"] == "Bearer"


def test_non_ascii_token_is_401_not_500(mcp, client):
    headers = {
        "Authorization": "Bearer \xe9\xe9".encode("latin-1"),
        "X-TrailTalk-Session": mcp.session_id,
        "Accept": "application/json, text/event-stream",
    }
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert client.post("/internal/mcp/", headers=headers, json=body).status_code == 401


def test_rejects_token_of_another_session(mcp, client):
    other = client.app.state.runtimes.ensure("other-session")
    # 다른 세션의 올바른 토큰을 이 세션 ID와 함께 보내면 거부한다
    assert mcp.request("tools/list", token=other.token).status_code == 401
    assert (
        mcp.request(
            "tools/list", extra_headers={"Authorization": f"Basic {mcp.runtime_.token}"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "header",
    [
        "X-Forwarded-For",
        "X-Forwarded-Host",
        "X-Forwarded-Proto",
        "CF-Connecting-IP",
        "Forwarded",
        "Tailscale-User-Login",
    ],
)
def test_rejects_proxied_requests(mcp, header):
    response = mcp.request("tools/list", extra_headers={header: "203.0.113.7"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_save_note_links_current_user_turn(mcp):
    result = mcp.call("save_note", kind="idea", content="  등산로 쓰레기통 지도  ")
    assert not result["isError"]
    assert "등산로 쓰레기통 지도" in text_of(result)
    [note] = mcp.notes()
    assert note.session_id == mcp.session_id and note.turn_id == mcp.turn_id
    assert note.kind.value == "idea" and note.content == "등산로 쓰레기통 지도"


def test_save_note_without_current_turn(mcp):
    mcp.runtime_.current_user_turn_id = None
    assert not mcp.call("save_note", kind="memo", content="턴 밖 메모")["isError"]
    [note] = mcp.notes()
    assert note.turn_id is None


@pytest.mark.parametrize(
    "arguments",
    [
        {"kind": "wrong", "content": "x"},
        {"kind": "idea", "content": ""},
        {"kind": "idea", "content": "가" * 1001},
        {"kind": "idea", "content": "   "},
        {"content": "종류 없음"},
    ],
)
def test_save_note_validation(mcp, arguments):
    result = mcp.call("save_note", **arguments)
    assert result["isError"]
    assert mcp.notes() == []


def test_search_and_summarize(mcp):
    mcp.call("save_note", kind="idea", content="쓰레기통 지도 앱")
    mcp.call("save_note", kind="todo", content="지도 API 조사")
    found = text_of(mcp.call("search_notes", keyword="지도"))
    assert "쓰레기통 지도 앱" in found and "지도 API 조사" in found
    assert "없습니다" in text_of(mcp.call("search_notes", keyword="없는말"))
    summary = text_of(mcp.call("summarize_session"))
    assert "사용자 발화 수: 1" in summary and "저장한 노트: 2개" in summary
    assert "[todo] 지도 API 조사" in summary


def test_search_treats_wildcards_literally(mcp):
    mcp.call("save_note", kind="memo", content="할인 50% 쿠폰")
    mcp.call("save_note", kind="memo", content="file_name 규칙")
    mcp.call("save_note", kind="memo", content="평범한 메모")
    assert "평범한 메모" not in text_of(mcp.call("search_notes", keyword="%"))
    assert "50% 쿠폰" in text_of(mcp.call("search_notes", keyword="50%"))
    assert "평범한 메모" not in text_of(mcp.call("search_notes", keyword="_"))
    assert "file_name" in text_of(mcp.call("search_notes", keyword="e_n"))
    assert mcp.call("search_notes", keyword="   ")["isError"]


@pytest.mark.parametrize(
    ("tool", "status"),
    [("pause_session", SessionStatus.PAUSED), ("end_session", SessionStatus.ENDED)],
)
def test_pause_and_end_set_requested_status(mcp, tool, status):
    assert mcp.runtime_.requested_status is None
    assert not mcp.call(tool)["isError"]
    assert mcp.runtime_.requested_status is status
    assert mcp.runtime_.pop_requested_status() is status
    assert mcp.runtime_.requested_status is None


def set_user_text(mcp, client, text: str) -> None:
    async def update():
        async with client.app.state.session_factory() as db:
            (await db.get(Turn, mcp.turn_id)).text = text
            await db.commit()

    client.portal.call(update)


def test_set_nickname_saves_profile(mcp, client):
    set_user_text(mcp, client, "앞으로 길동 이라고 불러줘")
    result = mcp.call("set_nickname", nickname="  길동님  ")
    assert not result["isError"]
    assert "'길동님'" in text_of(result)
    assert mcp.nickname() == "길동님"
    assert client.get("/api/profile").json()["nickname"] == "길동님"


@pytest.mark.parametrize("nickname", ["", "   ", "가" * 21, "길동\n님"])
def test_set_nickname_validation(mcp, client, nickname):
    set_user_text(mcp, client, "길동이라고 불러줘 " + "가" * 21)
    mcp.call("set_nickname", nickname="길동")
    assert mcp.call("set_nickname", nickname=nickname)["isError"]
    assert mcp.nickname() == "길동"


def test_set_nickname_requires_name_from_user_turn(mcp, client):
    """검색 결과 속 지시 같은, 사용자가 말하지 않은 호칭은 저장하지 않는다."""
    set_user_text(mcp, client, "uv 최신 버전 찾아줘")
    result = mcp.call("set_nickname", nickname="주인님")
    assert result["isError"] and "말한 호칭" in text_of(result)
    mcp.runtime_.current_user_turn_id = None  # 인사말처럼 사용자 턴 밖
    assert mcp.call("set_nickname", nickname="길동님")["isError"]
    assert mcp.nickname() is None


def test_set_nickname_schema_has_length_limit(mcp):
    tools = mcp.request("tools/list").json()["result"]["tools"]
    [tool] = [t for t in tools if t["name"] == "set_nickname"]
    prop = tool["inputSchema"]["properties"]["nickname"]
    assert prop["maxLength"] == 20 and prop["minLength"] == 1


def test_client_config_shape(mcp):
    config = mcp_client_config("http://127.0.0.1:8000/", mcp.runtime_)
    server = config["mcpServers"]["trailtalk"]
    assert server["type"] == "http"
    assert server["url"] == "http://127.0.0.1:8000/internal/mcp/"
    assert server["headers"]["Authorization"] == f"Bearer {mcp.runtime_.token}"
    assert server["headers"]["X-TrailTalk-Session"] == mcp.session_id
