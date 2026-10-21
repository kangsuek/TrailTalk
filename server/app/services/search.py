"""웹 검색 API(Tavily, docs/tavily-search-plan.md). 캐릭터의 search_USA 도구가 쓴다.

키는 요청 머리말에만 쓰고 로그에 남기지 않는다. 검색어도 길이만 남긴다. 실패는 SearchError로
통일하고, 다시 시도하지 않는다(응답이 느려진다). 빈 결과·재검색은 호출하는 쪽과 규칙이 맡는다."""

import asyncio
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Protocol

import httpx2
from pydantic import SecretStr

from app.config import Settings
from app.llm.parser import host_of

logger = logging.getLogger("trailtalk.search")

Topic = Literal["general", "news"]
TimeRange = Literal["day", "week", "month"]
ErrorKind = Literal["unavailable", "rate_limited", "timeout", "failed"]


class SearchError(Exception):
    """kind: unavailable(키 없음·키 오류·한도 소진), rate_limited, timeout, failed."""

    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    published: date | None  # news 주제만 온다
    host: str | None  # 출처로 보일 호스트(www. 뗌)


class SearchProvider(Protocol):
    async def search(
        self,
        query: str,
        *,
        topic: Topic = "general",
        time_range: TimeRange | None = None,
        domains: list[str] | None = None,
    ) -> list[SearchResult]: ...


def parse_published(value: Any) -> date | None:
    """Tavily 발행일(RFC 2822, 예: 'Tue, 20 Oct 2026 07:53:00 GMT')을 날짜로. 못 읽으면 None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, IndexError):
        return None


def _error_text(response: httpx2.Response) -> str:
    try:
        return str(response.json()["detail"]["error"])[:100]
    except (ValueError, KeyError, TypeError):
        return "-"


_URL_MAX = 2000
_EXTRA_FETCH = 3  # 같은 기사 중복을 걸러도 건수가 모자라지 않게 더 받는다


def safe_url(url: str) -> bool:
    """http(s) 주소이고 공백·제어·서식 문자가 없다. 아니면 그 결과를 버린다(목록 형식 위조 방지)."""
    return (
        url.startswith(("http://", "https://"))
        and len(url) <= _URL_MAX
        and not any(c.isspace() or unicodedata.category(c) in {"Cc", "Cf"} for c in url)
    )


_SOURCE_SUFFIX = re.compile(r"\s[-|–—]\s[^-|–—]{2,40}$")
_NON_WORD = re.compile(r"[^\w]+")


def title_key(title: str, host: str | None = None) -> str:
    """같은 기사를 여러 매체가 실은 중복을 알아보는 키: 끝의 ' - 매체명'을 떼고 글자만 남긴다.

    접미사가 매체명으로 보일 때만(그 결과의 호스트에 접미사의 낱말이 들어 있을 때) 뗀다. 제목
    안의 ' - '(예: 'Dow rises - oil jumps')를 매체명으로 오해해 다른 기사를 같은 기사로 보지
    않게 한다."""
    text = title.strip()
    match = _SOURCE_SUFFIX.search(text)
    if match and host:
        host_key = _NON_WORD.sub("", host.casefold())
        words = [w for w in _NON_WORD.split(match.group(0).casefold()) if len(w) >= 3]
        if any(w in host_key for w in words):
            text = text[: match.start()]
    return _NON_WORD.sub("", text.casefold())


def dedupe_by_title(results: list[SearchResult]) -> list[SearchResult]:
    """제목이 같은 결과는 먼저 나온 것만 남긴다(순서 유지). 제목이 비면 중복으로 보지 않는다."""
    seen: set[str] = set()
    kept = []
    for result in results:
        key = title_key(result.title, result.host)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        kept.append(result)
    return kept


def clean_text(value: Any) -> str:
    """한 줄로 정리한다: 제어·서식 문자(줄바꿈 위조, 방향 전환 문자 등)를 지우고 공백을 접는다."""
    if not isinstance(value, str):
        return ""
    kept = (c for c in value if c.isspace() or unicodedata.category(c) not in {"Cc", "Cf"})
    return " ".join("".join(kept).split())


class TavilySearch:
    def __init__(
        self,
        client: httpx2.AsyncClient,
        *,
        api_key: SecretStr | None,
        base_url: str,
        depth: str,
        timeout_s: float,
        max_results: int,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._depth = depth
        self._timeout_s = timeout_s
        self._max_results = max_results

    @classmethod
    def from_settings(cls, client: httpx2.AsyncClient, settings: Settings) -> "TavilySearch":
        return cls(
            client,
            api_key=settings.tavily_api_key,
            base_url=settings.tavily_base_url,
            depth=settings.search_depth,
            timeout_s=settings.search_timeout_s,
            max_results=settings.search_max_results,
        )

    async def search(
        self,
        query: str,
        *,
        topic: Topic = "general",
        time_range: TimeRange | None = None,
        domains: list[str] | None = None,
    ) -> list[SearchResult]:
        if self._api_key is None or not self._api_key.get_secret_value():
            # 키 없는 요청이 200으로 돌아온 사례가 있어(스파이크 3절) 호출하지 않는다
            raise SearchError("unavailable", "검색 API 키가 설정되지 않았습니다.")
        body: dict[str, Any] = {
            "query": query,
            "topic": topic,
            "search_depth": self._depth,
            "max_results": min(self._max_results + _EXTRA_FETCH, 20),
            "include_usage": True,
        }
        if time_range:
            body["time_range"] = time_range
        if domains:
            body["include_domains"] = domains
        started = time.monotonic()
        try:
            # httpx의 시간 제한은 연결·읽기 단계별이라, 전체 시간은 asyncio.timeout으로 묶는다
            async with asyncio.timeout(self._timeout_s):
                response = await self._client.post(
                    f"{self._base_url}/search",
                    headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                    json=body,
                    timeout=self._timeout_s,
                )
        except (TimeoutError, httpx2.TimeoutException) as exc:
            logger.warning("검색 시간 초과 (%.1f초)", self._timeout_s)
            raise SearchError("timeout", "검색 시간이 초과되었습니다.") from exc
        except httpx2.HTTPError as exc:
            logger.warning("검색 요청 실패: %s", type(exc).__name__)
            raise SearchError("failed", "검색 서비스에 연결하지 못했습니다.") from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)
        status = response.status_code
        if status in (401, 403, 432, 433):  # 키 오류·플랜/종량제 한도 초과: 다시 해도 안 풀린다
            logger.error("검색 사용 불가: HTTP %d (키 또는 한도 확인)", status)
            raise SearchError("unavailable", "검색 서비스를 쓸 수 없습니다.")
        if status == 429:
            logger.warning("검색 속도 제한: HTTP 429")
            raise SearchError("rate_limited", "검색 요청이 잠시 많습니다.")
        if status >= 400:
            # 본문에 검색어가 되풀이될 수 있어 오류 문구(detail.error)만 남긴다
            logger.warning("검색 오류: HTTP %d %s", status, _error_text(response))
            raise SearchError("failed", "검색에 실패했습니다.")
        try:
            data = response.json()
            raw_results = data["results"]
            if not isinstance(raw_results, list):
                raise TypeError("results")
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("검색 응답을 읽지 못했습니다")
            raise SearchError("failed", "검색 응답을 읽지 못했습니다.") from exc
        results = dedupe_by_title(self._results(raw_results))[: self._max_results]
        usage = data.get("usage") if isinstance(data, dict) else None
        credits = usage.get("credits") if isinstance(usage, dict) else None
        # 무료 한도(월 1,000크레딧) 추적용. 검색어는 길이만 남긴다
        logger.info(
            "검색 완료 topic=%s depth=%s range=%s query_len=%d results=%d credits=%s %dms",
            topic,
            self._depth,
            time_range,
            len(query),
            len(results),
            credits,
            elapsed_ms,
        )
        return results

    @staticmethod
    def _results(raw_results: list[Any]) -> list[SearchResult]:
        results = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not safe_url(url):
                continue
            results.append(
                SearchResult(
                    title=clean_text(item.get("title")),
                    url=url,
                    snippet=clean_text(item.get("content")),
                    published=parse_published(item.get("published_date")),
                    host=host_of(url),
                )
            )
        return results
