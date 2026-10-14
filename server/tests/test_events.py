import json

import pytest

from app.api.events import (
    DoneEvent,
    ErrorEvent,
    SentenceEvent,
    ToolEvent,
    TurnEvent,
    encode_sse,
    parse_sse_data,
    public_tool_name,
)


@pytest.mark.parametrize(
    "event",
    [
        TurnEvent(turn_id="t-1"),
        SentenceEvent(index=0, text="안녕하세요, 다니엘님!"),
        ToolEvent(phase="start", tool_use_id="t1", name="web_search"),
        ToolEvent(phase="call", tool_use_id="t1", name="web_search", input={"query": "q"}),
        ToolEvent(phase="end", tool_use_id="t1", name="web_search", summary={"links": []}),
        DoneEvent(turn_id="x", text="끝", session_status="ended"),
        ErrorEvent(code="llm_timeout", message="시간 초과"),
    ],
)
def test_encode_round_trip(event):
    raw = encode_sse(event).decode()
    assert raw.startswith(f"event: {event.type}\ndata: ") and raw.endswith("\n\n")
    data = raw.split("data: ", 1)[1].rstrip("\n")
    assert "\n" not in data  # 한 줄 JSON(본문 줄바꿈은 이스케이프된다)
    assert json.loads(data)["type"] == event.type
    assert parse_sse_data(data) == event


def test_multiline_text_stays_single_data_line():
    raw = encode_sse(SentenceEvent(index=1, text="첫 줄\n둘째 줄")).decode()
    assert raw.count("\n") == 3  # event 줄, data 줄, 빈 줄


@pytest.mark.parametrize(
    ("cli", "public"),
    [
        ("mcp__trailtalk__save_note", "save_note"),
        ("mcp__trailtalk__end_session", "end_session"),
        ("WebSearch", "web_search"),
        ("WebFetch", "web_fetch"),
        ("SomethingElse", "SomethingElse"),
    ],
)
def test_public_tool_name(cli, public):
    assert public_tool_name(cli) == public


def test_openapi_includes_event_schemas(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in [
        "StreamEvent",
        "TurnEvent",
        "SentenceEvent",
        "ToolEvent",
        "DoneEvent",
        "ErrorEvent",
    ]:
        assert name in schemas
        if name != "StreamEvent":
            # 기본값이 있어도 항상 보내는 필드는 required(생성 타입의 type 좁히기)
            assert set(schemas[name]["required"]) == set(schemas[name]["properties"]), name
    mapping = schemas["StreamEvent"]["discriminator"]["mapping"]
    assert set(mapping) == {"turn", "sentence", "tool", "done", "error"}
    assert schemas["ToolEvent"]["properties"]["phase"]["enum"] == ["start", "call", "end"]
