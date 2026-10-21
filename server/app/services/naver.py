"""네이버 뉴스 검색 API(docs/naver-search-plan.md). 캐릭터의 search_naver 도구가 쓴다.

키는 요청 머리말에만 쓰고 로그에 남기지 않는다. 검색어도 길이만 남긴다. 네이버에는 날짜 범위
필터와 언론사 필드가 없어서, 기간(time_range)이나 매체(domains)를 지정하면 날짜순으로 여러 건을
받아 발행일·원문 주소 호스트로 직접 거른다. 실패는 SearchError로 통일하고 다시 시도하지 않는다."""

import asyncio
import html
import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx2
from pydantic import SecretStr

from app.config import Settings
from app.llm.parser import host_of
from app.services.search import (
    SearchError,
    SearchResult,
    TimeRange,
    Topic,
    clean_text,
    dedupe_by_title,
    safe_url,
)

logger = logging.getLogger("trailtalk.search")

_EXTRA_FETCH = 5  # 기간·매체 지정이 없을 때, 같은 기사 중복을 걸러도 건수가 모자라지 않게 더 받는다

_TAG = re.compile(r"<[^>]+>")
_WINDOWS: dict[str, timedelta] = {
    "day": timedelta(hours=24),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
}


def parse_pub_date(value: Any) -> datetime | None:
    """네이버 발행 시각('Wed, 21 Oct 2026 09:42:00 +0900' 형식)을 시각으로. 못 읽으면 None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clean(value: Any) -> str:
    """<b> 같은 태그와 HTML 엔티티를 지우고 한 줄로 정리한다."""
    if not isinstance(value, str):
        return ""
    return clean_text(_TAG.sub("", html.unescape(_TAG.sub("", value))))


def _domain(value: str) -> str:
    """사용자가 말한 매체 주소('https://www.YTN.co.kr:443/news?x=1')에서 도메인만."""
    text = value.strip().lower()
    if "://" not in text:
        text = "//" + text
    try:
        host = urlsplit(text).hostname or ""
    except ValueError:
        return ""
    return host.removeprefix("www.")


def _host_matches(host: str | None, domains: list[str]) -> bool:
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in domains if d)


class NaverNewsSearch:
    def __init__(
        self,
        client: httpx2.AsyncClient,
        *,
        client_id: SecretStr | None,
        client_secret: SecretStr | None,
        base_url: str,
        timeout_s: float,
        max_results: int,
        fetch_count: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._max_results = max_results
        self._fetch_count = fetch_count
        self._now = now

    @classmethod
    def from_settings(cls, client: httpx2.AsyncClient, settings: Settings) -> "NaverNewsSearch":
        return cls(
            client,
            client_id=settings.naver_client_id,
            client_secret=settings.naver_client_secret,
            base_url=settings.naver_base_url,
            timeout_s=settings.search_timeout_s,
            max_results=settings.search_max_results,
            fetch_count=settings.naver_fetch_count,
        )

    async def search(
        self,
        query: str,
        *,
        topic: Topic = "news",
        time_range: TimeRange | None = None,
        domains: list[str] | None = None,
    ) -> list[SearchResult]:
        if (
            self._client_id is None
            or self._client_secret is None
            or not self._client_id.get_secret_value()
            or not self._client_secret.get_secret_value()
        ):
            raise SearchError("unavailable", "네이버 API 키가 설정되지 않았습니다.")
        sites = [d for d in (_domain(x) for x in domains or []) if d]
        filtering = bool(time_range or sites)
        # 매체를 지정하면 검색어를 두 가지로 동시에 보낸다: 모델이 쓴 검색어(매체 이름이 들어
        # 있으면 그 매체 최신 기사가 잘 나온다)와 첫 도메인을 붙인 검색어(한경·연합 등은 이쪽이
        # 낫고, 매체에 따라 오래된 기사가 섞인다). 합쳐서 최신순으로 거른다. 여러 매체여도 첫
        # 도메인만 붙이고 결과는 모든 매체의 호스트로 거른다
        queries = [query]
        if sites and sites[0] not in query.lower():
            queries.append(f"{query} {sites[0]}")
        sort = "date" if filtering else "sim"
        display = self._fetch_count if filtering else self._max_results + _EXTRA_FETCH
        started = time.monotonic()
        outcomes = await asyncio.gather(
            *(self._fetch(q, sort, display) for q in queries), return_exceptions=True
        )
        for outcome in outcomes:
            if isinstance(outcome, BaseException) and not isinstance(outcome, SearchError):
                raise outcome  # 코드 버그나 취소는 삼키지 않는다
        errors = [o for o in outcomes if isinstance(o, SearchError)]
        pages = [o for o in outcomes if not isinstance(o, SearchError)]
        if not pages:  # 모두 실패: 첫 오류를 그대로 올린다(원인은 fetch에서 이미 기록했다)
            raise errors[0]
        raw_items = [item for page in pages for item in page]
        parsed = self._results(raw_items)
        if len(queries) > 1:
            parsed.sort(key=lambda pair: pair[1] or datetime.min.replace(tzinfo=UTC), reverse=True)
        results = self._filter(parsed, time_range, sites)
        logger.info(
            "네이버 검색 완료 sort=%s range=%s site=%s query_len=%d requests=%d fetched=%d "
            "results=%d %dms",
            sort,
            time_range,
            bool(sites),
            len(query),
            len(queries),
            len(raw_items),
            len(results),
            int((time.monotonic() - started) * 1000),
        )
        return results

    async def _fetch(self, query: str, sort: str, display: int) -> list[Any]:
        """검색 한 번. 실패는 SearchError로 통일하고 원인을 기록한다."""
        try:
            # httpx의 시간 제한은 연결·읽기 단계별이라, 전체 시간은 asyncio.timeout으로 묶는다
            async with asyncio.timeout(self._timeout_s):
                response = await self._client.get(
                    f"{self._base_url}/v1/search/news.json",
                    params={"query": query, "sort": sort, "display": display},
                    headers={
                        "X-Naver-Client-Id": self._client_id.get_secret_value(),
                        "X-Naver-Client-Secret": self._client_secret.get_secret_value(),
                    },
                    timeout=self._timeout_s,
                )
        except (TimeoutError, httpx2.TimeoutException) as exc:
            logger.warning("네이버 검색 시간 초과 (%.1f초)", self._timeout_s)
            raise SearchError("timeout", "검색 시간이 초과되었습니다.") from exc
        except httpx2.HTTPError as exc:
            logger.warning("네이버 검색 요청 실패: %s", type(exc).__name__)
            raise SearchError("failed", "검색 서비스에 연결하지 못했습니다.") from exc
        status = response.status_code
        if status in (401, 403):  # 키 오류, 또는 개발자 센터에서 검색 API를 켜지 않음
            logger.error("네이버 검색 사용 불가: HTTP %d (키 또는 검색 API 권한 확인)", status)
            raise SearchError("unavailable", "검색 서비스를 쓸 수 없습니다.")
        if status == 429:  # 하루 호출 한도(25,000회) 초과 포함
            logger.warning("네이버 검색 한도 또는 속도 제한: HTTP 429")
            raise SearchError("rate_limited", "검색 요청이 잠시 많습니다.")
        if status >= 400:
            logger.warning("네이버 검색 오류: HTTP %d %s", status, _error_text(response))
            raise SearchError("failed", "검색에 실패했습니다.")
        try:
            items = response.json()["items"]
            if not isinstance(items, list):
                raise TypeError("items")
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("네이버 검색 응답을 읽지 못했습니다")
            raise SearchError("failed", "검색 응답을 읽지 못했습니다.") from exc
        return items

    def _filter(
        self,
        items: list[tuple[SearchResult, datetime | None]],
        time_range: TimeRange | None,
        sites: list[str],
    ) -> list[SearchResult]:
        cutoff = self._now() - _WINDOWS[time_range] if time_range else None
        kept = []
        for result, published_at in items:
            if cutoff is not None and (published_at is None or published_at < cutoff):
                continue  # 기간을 지정했는데 발행 시각을 모르거나 오래된 기사
            if sites and not _host_matches(result.host, sites):
                continue
            kept.append(result)
        # 매체 지정 필터를 거친 뒤에 중복을 거른다(지정한 매체 기사가 다른 매체 기사와 제목이
        # 같다는 이유로 빠지지 않게)
        return dedupe_by_title(kept)[: self._max_results]

    @staticmethod
    def _results(raw_items: list[Any]) -> list[tuple[SearchResult, datetime | None]]:
        results: list[tuple[SearchResult, datetime | None]] = []
        seen: set[str] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            # 언론사 원문 주소를 먼저 쓴다(출처 매체를 알 수 있다). 없거나 위험하면 네이버 뉴스 주소
            url = next(
                (
                    u
                    for u in (item.get("originallink"), item.get("link"))
                    if isinstance(u, str) and safe_url(u)
                ),
                None,
            )
            if url is None or url in seen:
                continue
            seen.add(url)
            published_at = parse_pub_date(item.get("pubDate"))
            results.append(
                (
                    SearchResult(
                        title=_clean(item.get("title")),
                        url=url,
                        snippet=_clean(item.get("description")),
                        published=published_at.date() if published_at else None,
                        host=host_of(url),
                    ),
                    published_at,
                )
            )
        return results


def _error_text(response: httpx2.Response) -> str:
    """네이버 오류 본문({"errorMessage": ..., "errorCode": ...})에서 코드와 문구만."""
    try:
        body = response.json()
        return f"{body.get('errorCode')} {str(body.get('errorMessage'))[:80]}"
    except (ValueError, AttributeError):
        return "-"
