"""일지 인용 제목 보완(S3-22). 네트워크는 쓰지 않는다(가짜 fetch)."""

import asyncio

import pytest

from app.jobs import page_title
from app.jobs.page_title import extract_title, improve_titles, is_weak_title


def test_extract_title_prefers_og_title():
    doc = """<html><head><title>사이트 | 목록</title>
    <meta content="서울 &quot;낮 최고&quot; 26도" property="og:title"></head></html>"""
    assert extract_title(doc) == '서울 "낮 최고" 26도'
    assert extract_title("<TITLE>\n 기사\n 제목 </TITLE>") == "기사 제목"
    assert extract_title("<p>제목 없음</p>") is None


@pytest.mark.parametrize(
    ("title", "weak"),
    [
        (None, True),
        ("", True),
        ("www.ytn.co.kr", True),
        ("ytn.co.kr", True),
        ("news.example.com", True),  # 다른 도메인 이름도 기사 제목이 아니다
        ("[오늘 날씨] 맑음", False),
        ("Claude Code v1.0.11", False),
    ],
)
def test_is_weak_title(title, weak):
    assert is_weak_title(title, "https://www.ytn.co.kr/_ln/1") is weak


def test_improve_titles_only_for_cited_weak_sources():
    sources = [
        {"title": "www.ytn.co.kr", "url": "https://www.ytn.co.kr/a"},
        {"title": "좋은 제목", "url": "https://b.example.com/b"},
        {"title": None, "url": "https://c.example.com/c"},
        {"title": "www.ytn.co.kr", "url": "https://www.ytn.co.kr/d"},  # 인용되지 않음
    ]
    asked: list[str] = []

    async def fake_fetch(_client, url):
        asked.append(url)
        if url.endswith("/c"):
            raise OSError("연결 실패")
        return "서울 아침 기온 역대 최고"

    improved = asyncio.run(improve_titles(sources, [1, 2, 3, 99], fetch=fake_fetch))
    assert sorted(asked) == ["https://c.example.com/c", "https://www.ytn.co.kr/a"]
    assert improved[0]["title"] == "서울 아침 기온 역대 최고"
    assert improved[1]["title"] == "좋은 제목"
    assert improved[2]["title"] is None  # 실패하면 원래 값
    assert improved[3]["title"] == "www.ytn.co.kr"
    assert sources[0]["title"] == "www.ytn.co.kr"  # 원본은 바꾸지 않는다


def test_improve_titles_gives_up_after_total_timeout(monkeypatch):
    monkeypatch.setattr(page_title, "TOTAL_TIMEOUT_S", 0.05)

    async def slow(_client, _url):
        await asyncio.sleep(5)
        return "늦은 제목"

    improved = asyncio.run(
        improve_titles([{"title": None, "url": "https://a.example.com/"}], [1], fetch=slow)
    )
    assert improved[0]["title"] is None


def test_extract_title_is_fast_on_hostile_html():
    """정규식 대신 html.parser로 앞부분만 읽어 악성 HTML에도 금방 끝난다(서버 멈춤 방지)."""
    import time

    started = time.monotonic()
    assert extract_title("<meta " + "a" * 300_000 + ">") is None
    extract_title("<title>" * 50_000)
    assert time.monotonic() - started < 2


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/api/journal",
        "http://localhost/",
        "http://192.168.0.1/",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://[64:ff9b::7f00:1]/",  # NAT64로 감싼 127.0.0.1
        "http://[::127.0.0.1]/",
        "http://[::ffff:192.168.0.1]/",
        "https://example.com:8443/",  # 기본 포트만
        "ftp://example.com/",
        "file:///etc/passwd",
    ],
)
def test_unsafe_urls_are_not_opened(url):
    assert asyncio.run(page_title.is_safe_url(url)) is False


def test_redirect_to_private_address_is_not_followed(monkeypatch):
    async def safe(url):
        return "127.0.0.1" not in url  # 첫 주소는 공인, 리다이렉트 대상은 내부

    monkeypatch.setattr(page_title, "is_safe_url", safe)
    seen: list[str] = []

    def handler(request):
        seen.append(str(request.url))
        return page_title.httpx2.Response(302, headers={"location": "http://127.0.0.1:8000/secret"})

    async def go():
        transport = page_title.httpx2.MockTransport(handler)
        async with page_title.httpx2.AsyncClient(transport=transport) as client:
            return await page_title.fetch_title(client, "https://news.example.com/a")

    assert asyncio.run(go()) is None
    assert seen == ["https://news.example.com/a"]  # 내부 주소로는 요청하지 않았다


def test_fetch_title_reads_meta_charset(monkeypatch):
    async def safe(_url):
        return True

    monkeypatch.setattr(page_title, "is_safe_url", safe)
    body = '<html><head><meta charset="euc-kr"><title>서울 날씨</title></head>'.encode("euc-kr")

    def handler(_request):
        stream = page_title.httpx2.ByteStream(body)  # 실제처럼 아직 읽지 않은 본문
        return page_title.httpx2.Response(200, headers={"content-type": "text/html"}, stream=stream)

    async def go():
        transport = page_title.httpx2.MockTransport(handler)
        async with page_title.httpx2.AsyncClient(transport=transport) as client:
            return await page_title.fetch_title(client, "https://news.example.com/a")

    assert asyncio.run(go()) == "서울 날씨"
