"""일지 인용 제목 보완(S3-22): 웹 검색 결과가 기사 제목 대신 도메인만 준 출처는 정리할 때 그
페이지를 열어 기사 제목(og:title, 없으면 <title>)을 읽는다. 인용된 출처만, 짧은 시간 제한
안에서 한다. 실패하면 원래 값(도메인)을 그대로 둔다.

URL은 모델이 고른 것이라(웹 검색·페이지 읽기 결과) 서버 쪽 요청 위조를 막는다: http(s)·기본
포트만, 이름을 풀어 사설·루프백·링크 로컬 등 공인이 아닌 주소면 열지 않고, 리다이렉트도 단계마다
다시 검사한다. 본문은 압축 없이 앞부분만 읽고, 파싱은 표준 html.parser로 스레드에서 한다.
남은 위험: 검사와 연결 사이에 이름 해석이 바뀌는 DNS 리바인딩은 막지 않는다(GET만 하고 제목 한 줄만
쓰는 본인용 앱이라 둔다. 막으려면 검사한 IP로 직접 연결하는 transport를 쓴다).
"""

import asyncio
import html
import ipaddress
import logging
import re
import socket
from collections.abc import Awaitable, Callable, Iterable, Sequence
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx2

from app.llm.parser import host_of

logger = logging.getLogger("trailtalk.page_title")

FETCH_TIMEOUT_S = 5.0
TOTAL_TIMEOUT_S = 10.0
MAX_BYTES = 64_000  # 제목은 <head>에 있다
MAX_PAGES = 10
MAX_REDIRECTS = 3
MAX_TITLE = 200
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (TrailTalk journal)",
    "Accept": "text/html",
    "Accept-Encoding": "identity",  # 압축 폭탄을 피한다
}
_DOMAIN = re.compile(r"^(www\.)?[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63}){1,10}$", re.IGNORECASE)
_CHARSET = re.compile(rb"""charset=["']?([A-Za-z0-9_-]{1,40})""")


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.og: str | None = None
        self.title_parts: list[str] = []
        self._in_title = False
        self.done = False

    def handle_starttag(self, tag, attrs):
        if tag == "meta" and self.og is None:
            values = {k.lower(): (v or "") for k, v in attrs}
            if values.get("property", values.get("name", "")).lower() in (
                "og:title",
                "twitter:title",
            ):
                self.og = values.get("content") or None
        elif tag == "title":
            self._in_title = True
        elif tag == "body":
            self.done = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(html.unescape(text).split())
    return text[:MAX_TITLE] or None


def extract_title(document: str) -> str | None:
    """HTML에서 기사 제목: og:title(또는 twitter:title) → <title>."""
    parser = _TitleParser()
    try:
        parser.feed(document[:MAX_BYTES])
        parser.close()
    except Exception:  # 깨진 HTML: 읽은 데까지만 쓴다
        pass
    return _clean(parser.og) or _clean("".join(parser.title_parts))


def is_weak_title(title: str | None, url: str) -> bool:
    """제목이 없거나 도메인뿐인가(언론사 이름만으로는 어떤 기사인지 알 수 없다)."""
    if not title:
        return True
    name = title.strip().lower()
    return name.removeprefix("www.") == (host_of(url) or "") or bool(_DOMAIN.match(name))


_EMBEDS_IPV4 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("::/96"))


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    # IPv6 안에 넣은 IPv4(매핑·NAT64·호환)는 꺼내서 다시 본다(64:ff9b::7f00:1 → 127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif any(ip in net for net in _EMBEDS_IPV4):
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip.is_global and not ip.is_multicast


async def is_safe_url(url: str) -> bool:
    """공인 주소의 http(s) 기본 포트만 연다(내부망·이 서버 자신을 열지 않게)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    if parts.port not in (None, 80, 443):
        return False
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname, None, type=socket.SOCK_STREAM
        )
    except (OSError, UnicodeError):
        return False
    return bool(infos) and all(_public(info[4][0]) for info in infos)


def _decode(body: bytes, header_encoding: str | None) -> str:
    encoding = header_encoding
    if encoding is None:
        match = _CHARSET.search(body[:4096])
        encoding = match.group(1).decode("ascii") if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def fetch_title(client: httpx2.AsyncClient, url: str) -> str | None:
    for _ in range(MAX_REDIRECTS + 1):
        if not await is_safe_url(url):
            logger.info("인용 제목: 열지 않는 주소(%s)", host_of(url))
            return None
        async with client.stream("GET", url) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    return None
                url = urljoin(url, location)
                continue
            if response.status_code >= 400:
                return None
            if "html" not in response.headers.get("content-type", "html"):
                return None
            body = b""
            async for chunk in response.aiter_raw():
                body += chunk
                if len(body) >= MAX_BYTES:
                    break
            charset = response.charset_encoding
        return await asyncio.to_thread(extract_title, _decode(body[:MAX_BYTES], charset))
    return None


Fetch = Callable[[httpx2.AsyncClient, str], Awaitable[str | None]]


async def improve_titles(
    sources: Sequence[dict], cited: Iterable[int], fetch: Fetch = fetch_title
) -> list[dict]:
    """cited(1부터 번호)의 출처 중 제목이 약한 것만 페이지에서 제목을 읽어 바꾼 사본을 돌려준다."""
    improved = [dict(src) for src in sources]
    targets = [
        i
        for i in sorted(set(cited))
        if 1 <= i <= len(improved)
        and is_weak_title(improved[i - 1].get("title"), improved[i - 1]["url"])
    ][:MAX_PAGES]
    if not targets:
        return improved

    # 리다이렉트는 직접 따라가며 단계마다 주소를 검사한다
    async with httpx2.AsyncClient(
        timeout=FETCH_TIMEOUT_S, follow_redirects=False, headers=_HEADERS
    ) as client:

        async def one(i: int) -> None:
            try:
                title = await fetch(client, improved[i - 1]["url"])
            except Exception as exc:  # 네트워크·형식 오류는 원래 값을 둔다
                logger.info("인용 제목을 읽지 못함(%s): %s", host_of(improved[i - 1]["url"]), exc)
                return
            if title and not is_weak_title(title, improved[i - 1]["url"]):
                improved[i - 1]["title"] = title

        tasks = [asyncio.create_task(one(i)) for i in targets]
        _, pending = await asyncio.wait(tasks, timeout=TOTAL_TIMEOUT_S)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    return improved
