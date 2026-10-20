from pathlib import Path

import pytest

from app.llm.events import (
    RateLimitUpdated,
    TextDelta,
    ToolCalled,
    ToolFinished,
    ToolStarted,
    TurnFinished,
    TurnStarted,
)
from app.llm.parser import StreamJsonParser, _tool_summary, host_of

FIXTURES = Path(__file__).parent / "fixtures" / "claude_cli"


def parse(name: str) -> list:
    parser = StreamJsonParser()
    return [
        e
        for line in (FIXTURES / f"{name}.jsonl").read_text().splitlines()
        for e in parser.feed(line)
    ]


def split_turns(events: list) -> list[list]:
    turns, current = [], []
    for event in events:
        current.append(event)
        if isinstance(event, TurnFinished):
            turns.append(current)
            current = []
    return turns


def text_of(turn: list) -> str:
    return "".join(e.text for e in turn if isinstance(e, TextDelta))


def test_multiturn_text_matches_result():
    turns = split_turns(parse("multiturn"))
    assert len(turns) == 3
    for turn in turns:
        assert isinstance(turn[0], TurnStarted) and turn[0].cli_session_id
        finished = turn[-1]
        assert not finished.is_error and not finished.interrupted
        assert text_of(turn) == finished.text
    assert turns[2][-1].text == "사과와 바나나입니다."


def test_tool_call_order_and_input():
    turns = split_turns(parse("tool_call"))
    tool_turn = turns[1]
    tool_events = [e for e in tool_turn if isinstance(e, (ToolStarted, ToolCalled, ToolFinished))]
    assert [type(e) for e in tool_events] == [ToolStarted, ToolCalled, ToolFinished]
    started, called, finished = tool_events
    assert started.name == called.name == "mcp__trailtalk__save_note"
    assert started.tool_use_id == called.tool_use_id == finished.tool_use_id
    assert called.input["kind"] == "idea"
    assert finished.summary == {"kind": "result", "result": "저장 완료"}
    assert tool_turn[-1].text.endswith(text_of(tool_turn)[-10:])


def test_web_search_and_fetch_summaries():
    called = [e for e in parse("web_search") if isinstance(e, ToolCalled)]
    finished = {e.tool_use_id: e for e in parse("web_search") if isinstance(e, ToolFinished)}
    names = [c.name for c in called]
    assert names == ["WebSearch", "WebFetch", "mcp__trailtalk__save_note"]
    search, fetch = called[0], called[1]
    assert search.input["query"]
    summary = finished[search.tool_use_id].summary
    assert summary["kind"] == "web_search" and summary["query"] == search.input["query"]
    assert summary["links"][0]["url"].startswith("http")
    # 출처는 링크의 호스트 이름(www. 뗌, 중복 없이 최대 3개, 링크 순서)
    hosts = [host_of(link["url"]) for link in summary["links"]]
    assert summary["sources"] == list(dict.fromkeys(hosts))[:3]
    assert all(not h.startswith("www.") for h in summary["sources"])
    assert fetch.input["url"] == "https://docs.astral.sh/uv/"
    assert finished[fetch.tool_use_id].summary == {
        "kind": "web_fetch",
        "code": 200,
        "bytes": 83236,
        "url": "https://docs.astral.sh/uv/",
        "host": "docs.astral.sh",
    }


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("https://www.example.com/a", "example.com"),
        ("http://sub.example.co.kr:8080/x?y", "sub.example.co.kr"),
        ("not a url", None),
        ("http://[::1", None),
        ("http://www./", None),
        (None, None),
    ],
)
def test_host_of(url, host):
    assert host_of(url) == host


def test_unknown_tool_result_has_no_summary():
    assert _tool_summary({"something": 1}) is None
    assert _tool_summary("text") is None


def test_search_api_tool_result_becomes_web_search_summary():
    """검색 API 도구(search_web) 결과는 내장 WebSearch와 같은 요약(링크·출처)이 된다."""
    raw = {
        "content": [{"type": "text", "text": "..."}],
        "structuredContent": {
            "query": "엔비디아 뉴스",
            "results": [
                {"title": "기사", "url": "https://www.cnbc.com/a"},
                {"title": 7, "url": "https://www.reuters.com/b"},
                {"title": "중복 호스트", "url": "https://cnbc.com/c"},
                {"title": "주소 없음"},
                "x",
            ],
        },
    }
    assert _tool_summary(raw) == {
        "kind": "web_search",
        "query": "엔비디아 뉴스",
        "links": [
            {"title": "기사", "url": "https://www.cnbc.com/a"},
            {"title": None, "url": "https://www.reuters.com/b"},
            {"title": "중복 호스트", "url": "https://cnbc.com/c"},
        ],
        "sources": ["cnbc.com", "reuters.com"],
    }
    assert _tool_summary({"structuredContent": {"query": "q", "results": []}}) == {
        "kind": "web_search",
        "query": "q",
        "links": [],
        "sources": [],
    }


def test_other_mcp_results_keep_result_kind():
    assert _tool_summary({"structuredContent": {"result": "저장 완료"}}) == {
        "kind": "result",
        "result": "저장 완료",
    }
    assert _tool_summary({"structuredContent": {"query": "q", "results": "x"}})["kind"] == "result"


def test_interrupted_turn():
    turns = split_turns(parse("interrupt"))
    first = turns[0][-1]
    assert first.interrupted and first.is_error
    assert first.error_message is None and first.text == ""
    assert text_of(turns[0])  # 중단 전까지 부분 출력은 있었다
    assert not turns[1][-1].interrupted


def test_error_uses_is_error_not_subtype():
    finished = parse("error_invalid_model")[-1]
    assert finished.is_error and not finished.interrupted
    assert "no-such-model-xyz" in finished.error_message
    assert finished.text == ""


def test_rate_limit_event_becomes_usage_update():
    limits = [e for e in parse("multiturn") if isinstance(e, RateLimitUpdated)]
    assert len(limits) == 3
    assert limits[0].info["unifiedWindows"]["five_hour"]["utilization"] == 0.4
    assert StreamJsonParser().feed('{"type": "rate_limit_event", "rate_limit_info": 1}') == []


ODD_LINES = [
    "",
    "not json",
    "[1, 2]",
    '{"type": "rate_limit_event"}',
    '{"type": "system", "subtype": "status"}',
    '{"type": "stream_event", "event": {"type": "content_block_delta", '
    '"delta": {"type": "thinking_delta"}}}',
    '{"type": "user", "message": {"content": "plain"}}',
    '{"type": "user", "message": {"content": [{"type": "tool_result"}]}, '
    '"tool_use_result": {"query": "q", "results": ["x", null]}}',
]


@pytest.mark.parametrize("line", ODD_LINES)
def test_odd_lines_do_not_crash(line):
    events = StreamJsonParser().feed(line)
    assert all(not isinstance(e, TextDelta) for e in events)
