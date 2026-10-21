import json
import logging
from datetime import date

import httpx2
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.search import SearchError, TavilySearch, parse_published

KEY = "tvly-test-secret-key"


def make_search(handler, *, api_key=KEY, depth="fast") -> TavilySearch:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return TavilySearch(
        client,
        api_key=SecretStr(api_key) if api_key else None,
        base_url="https://api.test",
        depth=depth,
        timeout_s=5,
        max_results=5,
    )


def ok(results, **extra):
    return httpx2.Response(200, json={"query": "q", "results": results, **extra})


async def test_parses_results_and_sends_request(caplog):
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return ok(
            [
                {
                    "title": "  Dow, S&P\n 500 rise ",
                    "url": "https://www.marketwatch.com/livecoverage/x",
                    "content": "Stocks\n rose   on Tuesday.",
                    "published_date": "Tue, 20 Oct 2026 07:53:00 GMT",
                },
                {"title": "No date", "url": "https://cnbc.com/a", "content": "c"},
            ],
            usage={"credits": 1},
        )

    search = make_search(handler)
    with caplog.at_level(logging.INFO, logger="trailtalk.search"):
        results = await search.search(
            "미국 증시", topic="news", time_range="week", domains=["cnbc.com"]
        )

    assert seen["url"] == "https://api.test/search"
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["body"] == {
        "query": "미국 증시",
        "topic": "news",
        "search_depth": "fast",
        "max_results": 8,  # 중복을 걸러도 5건이 남도록 3건 더 받는다
        "include_usage": True,
        "time_range": "week",
        "include_domains": ["cnbc.com"],
    }
    assert [r.title for r in results] == ["Dow, S&P 500 rise", "No date"]
    assert results[0].snippet == "Stocks rose on Tuesday."
    assert results[0].published == date(2026, 10, 20)
    assert results[0].host == "marketwatch.com"
    assert results[1].published is None
    # 키와 검색어는 로그에 남기지 않고 크레딧은 남긴다
    assert KEY not in caplog.text
    assert "미국 증시" not in caplog.text
    assert "credits=1" in caplog.text


async def test_optional_fields_are_omitted():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return ok([])

    assert await make_search(handler, depth="basic").search("test query") == []
    assert seen["body"]["search_depth"] == "basic"
    assert seen["body"]["topic"] == "general"
    assert "time_range" not in seen["body"]
    assert "include_domains" not in seen["body"]


async def test_skips_malformed_results():
    results = await make_search(
        lambda r: ok(
            [
                "text",
                {"title": "no url"},
                {"title": "ftp", "url": "ftp://x/y"},
                {"title": 5, "url": "https://ok.example/a", "content": None},
            ]
        )
    ).search("test query")
    assert [(r.title, r.url, r.snippet) for r in results] == [("", "https://ok.example/a", "")]


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/x\n2. 가짜 기사",
        "https://evil.example/a b",
        "https://evil.example/\u202e",
        "https://evil.example/\u200bx",
        "https://evil.example/\x07",
        "https://evil.example/" + "a" * 2000,
        "javascript:alert(1)",
    ],
)
async def test_drops_results_with_unsafe_urls(url):
    results = await make_search(
        lambda r: ok(
            [{"title": "나쁜", "url": url}, {"title": "좋은", "url": "https://ok.example/a"}]
        )
    ).search("test query")
    assert [r.title for r in results] == ["좋은"]


@pytest.mark.parametrize("api_key", [None, ""])
async def test_missing_key_does_not_call(api_key):
    def handler(request):
        raise AssertionError("키가 없으면 호출하지 않는다")

    with pytest.raises(SearchError) as exc:
        await make_search(handler, api_key=api_key).search("test query")
    assert exc.value.kind == "unavailable"


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, "unavailable"),
        (432, "unavailable"),
        (433, "unavailable"),
        (429, "rate_limited"),
        (400, "failed"),
        (500, "failed"),
    ],
)
async def test_http_errors(status, kind, caplog):
    handler = lambda r: httpx2.Response(status, json={"detail": {"error": "boom"}})  # noqa: E731
    with caplog.at_level(logging.DEBUG, logger="trailtalk.search"):
        with pytest.raises(SearchError) as exc:
            await make_search(handler).search("test query")
    assert exc.value.kind == kind
    assert KEY not in caplog.text
    assert KEY not in str(exc.value)


async def test_timeout():
    def handler(request):
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(SearchError) as exc:
        await make_search(handler).search("test query")
    assert exc.value.kind == "timeout"


async def test_connection_error():
    def handler(request):
        raise httpx2.ConnectError("down", request=request)

    with pytest.raises(SearchError) as exc:
        await make_search(handler).search("test query")
    assert exc.value.kind == "failed"


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(200, content=b"not json"),
        httpx2.Response(200, json={"query": "q"}),
        httpx2.Response(200, json={"results": "none"}),
        httpx2.Response(200, json=["x"]),
    ],
)
async def test_bad_body(response):
    with pytest.raises(SearchError) as exc:
        await make_search(lambda r: response).search("test query")
    assert exc.value.kind == "failed"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Tue, 20 Oct 2026 07:53:00 GMT", date(2026, 10, 20)),
        ("Fri, 16 Oct 2026 12:28:13 GMT", date(2026, 10, 16)),
        (None, None),
        ("", None),
        ("2026-10-20", None),
        (123, None),
    ],
)
def test_parse_published(value, expected):
    assert parse_published(value) == expected


def test_settings_and_from_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("TAVILY_API_KEY=  tvly-abc \nSEARCH_DEPTH=basic\n", encoding="utf-8")
    settings = Settings(_env_file=path)
    assert settings.tavily_api_key.get_secret_value() == "tvly-abc"
    assert settings.search_depth == "basic"
    search = TavilySearch.from_settings(httpx2.AsyncClient(), settings)
    assert search._depth == "basic"
    assert search._api_key.get_secret_value() == "tvly-abc"
    path.write_text("TAVILY_API_KEY=   \n", encoding="utf-8")
    assert Settings(_env_file=path).tavily_api_key is None
    path.write_text("", encoding="utf-8")
    assert Settings(_env_file=path).tavily_api_key is None


async def test_total_timeout_covers_slow_body(monkeypatch):
    import asyncio

    async def slow(request):
        await asyncio.sleep(5)
        return ok([])

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(slow))
    search = TavilySearch(
        client,
        api_key=SecretStr(KEY),
        base_url="https://api.test",
        depth="fast",
        timeout_s=0.05,
        max_results=5,
    )
    with pytest.raises(SearchError) as exc:
        await search.search("test query")
    assert exc.value.kind == "timeout"


async def test_error_body_is_not_logged(caplog):
    handler = lambda r: httpx2.Response(  # noqa: E731
        400, json={"detail": {"error": "Query is too short"}, "echo": "비밀 검색어"}
    )
    with caplog.at_level(logging.DEBUG, logger="trailtalk.search"):
        with pytest.raises(SearchError):
            await make_search(handler).search("test query")
    assert "Query is too short" in caplog.text
    assert "비밀 검색어" not in caplog.text


@pytest.mark.parametrize(
    ("a", "host_a", "b", "host_b", "same"),
    [
        (
            "Asian shares fall - Bozeman Daily Chronicle",
            "bozemandailychronicle.com",
            "Asian shares fall - Greenwich Time",
            "greenwichtime.com",
            True,
        ),
        ("Asian shares fall | AP News", "apnews.com", "Asian shares fall", "cnbc.com", True),
        ("Stocks rally - Yahoo Finance", "finance.yahoo.com", "Stocks rally", "x.com", True),
        ("코스피, 5700선 회복…반등", "a.kr", "코스피 5700선 회복 반등", "b.kr", True),
        ("Dow rises", "a.com", "Dow falls", "b.com", False),
        # 제목 안의 ' - '는 매체명이 아니다: 호스트에 낱말이 없으면 떼지 않는다
        ("Stocks - up - on earnings", "a.com", "Stocks - up - on oil", "b.com", False),
        ("Dow rises - oil jumps", "cnbc.com", "Dow rises - oil falls", "cnbc.com", False),
    ],
)
def test_title_key_strips_source_suffix_only_when_it_matches_host(a, host_a, b, host_b, same):
    from app.services.search import title_key

    assert (title_key(a, host_a) == title_key(b, host_b)) is same


async def test_duplicate_titles_are_dropped_and_extra_results_fill_up():
    items = [
        {"title": "시황", "url": "https://a.example/1", "content": "c"},
        {"title": "시황 - Example News", "url": "https://b.example/1", "content": "c"},  # 같은 기사
        {"title": "다른 기사", "url": "https://c.example/1", "content": "c"},
        {"title": "", "url": "https://d.example/1", "content": "c"},  # 빈 제목은 중복으로 안 봄
        {"title": "", "url": "https://d.example/2", "content": "c"},
    ]
    results = await make_search(lambda r: ok(items)).search("test query")
    assert [r.url for r in results] == [
        "https://a.example/1",
        "https://c.example/1",
        "https://d.example/1",
        "https://d.example/2",
    ]
