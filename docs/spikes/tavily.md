# Tavily Search API 스파이크 (TS-01)

2026-10-21. 공식 문서([Search 엔드포인트](https://docs.tavily.com/documentation/api-reference/endpoint/search))와 실제 키로 호출해 확인했다. 계획서: [tavily-search-plan.md](../tavily-search-plan.md).

## 1. 확인한 사양

| 항목 | 내용 |
|---|---|
| 호출 | `POST https://api.tavily.com/search`, 헤더 `Authorization: Bearer tvly-…`, JSON 본문 |
| 필수 | `query`(최소 2자, 1자면 400) |
| `topic` | `general`(기본), `news`, `finance` |
| `search_depth` | `basic`(기본), `advanced`(2크레딧), `fast`, `ultra-fast`. `basic`·`fast`·`ultra-fast`는 실측 1크레딧 |
| 기간 | `time_range`(`day`/`week`/`month`/`year`), `start_date`/`end_date`. **`days`는 스펙에 없고 보내도 무시된다**(3일로 요청했는데 기간 제한 없이 돌아옴). 계획서의 가정을 `time_range`로 고친다 |
| 개수 | `max_results` 0~20(기본 10) |
| 도메인 | `include_domains`(최대 300), `exclude_domains`(최대 150) |
| 사용량 | `include_usage: true`를 주면 응답에 `usage.credits`가 온다. 안 주면 `usage`는 없음 |
| 오류 | 401 키 없음/잘못됨, 400 잘못된 요청(`detail.error`), 429 속도 제한(`Retry-After`), 432 플랜 한도 초과, 433 종량제 한도 초과 |

응답 `results[]`: `title`, `url`, `content`(스니펫), `score`, `published_date`, `raw_content`(요청 시), `id`. 최상위: `query`, `answer`(요청 시), `response_time`, `request_id`.

## 2. 실측

질의 3종을 실제 키로 호출했다.

| 질의 | 설정 | 응답 시간(왕복) | 결과 |
|---|---|---|---|
| 미국 증시 마감 시황 이번 주 | news, basic | 3.6~4.2초 | 5건, 전부 발행일 있음, 최근 7일 이내, Yahoo Finance·MarketWatch·CNBC·Kitco |
| 같은 질의 | news, `fast` | **1.0초** | 5건, 발행일 있음 |
| 같은 질의 | news, `ultra-fast` | 1.0초 | 5건, 발행일 있음 |
| Nvidia AI chip news this week | news, basic, 도메인 지정(CNBC·Bloomberg·Reuters) | 4.1초 | 5건, CNBC·Reuters, 발행일 있음 |
| 같은 질의 | topic `finance` | 2.9초 | 5건, **발행일 없음**(Yahoo Finance만) |
| 북한산 둘레길 코스 추천 | general, basic | 5.6초 | **결과 0건**(빈 배열, 일시적) |
| 같은 질의(재호출) | general, basic | 2.2초 | 5건, 서울시 길 정보·블로그 |
| 같은 질의 | general, `fast` | 1.7초 | 5건, 블로그·유튜브 |

- 발행일 형식은 RFC 2822 문자열이다(`Tue, 20 Oct 2026 07:53:00 GMT`). `topic: news`일 때는 자동으로 오고, `general`·`finance`에서는 없을 수 있다.
- 스니펫 `content`는 건당 약 60~1,450자다. 도구에서 자른다.
- 한국어 질의도 한국어 결과가 온다. 한국어 뉴스 품질은 폰 검증(TS-11)에서 따로 본다.

## 3. 결론과 계획 반영

1. `days` 대신 `time_range`를 쓴다(`week`가 7일 규칙에 대응).
2. **`search_depth`는 `fast`를 기본으로 한다.** 크레딧은 같고 1~3초 빠르다. 음성 응답 지연이 중요하므로 맞다. 품질이 모자라면 `basic`으로 바꾸는 설정 값으로 둔다.
3. 같은 호출이 가끔 **빈 결과**를 돌려준다. 도구는 "결과 없음"을 그대로 알려 주고, 규칙의 자동 재검색(검색어 바꿔 최대 2회)에 맡긴다. 어댑터에서 자동 재시도는 하지 않는다(지연이 두 배가 된다).
4. 시간 초과는 8초로 충분하다(최장 5.6초 관측).
5. 뉴스 기사의 발행일 문자열은 어댑터에서 날짜로 파싱해 `YYYY-MM-DD`로 보여 준다. 날짜가 없으면 "날짜 없음"이라고 표시해 규칙의 "날짜 확인 필요"와 맞춘다.
6. 키가 없는 요청(`Bearer ` 뒤가 빈 문자열)도 200으로 응답한 사례가 있었다. 이 동작에 의존하지 않고, 키가 없으면 호출하지 않고 폴백 문구를 돌려준다.
7. 잘못된 키는 401이다. 어댑터는 401·432·433을 "서비스 사용 불가"로, 429를 "잠시 후"로 구분해 로그를 남긴다.
