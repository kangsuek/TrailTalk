# 클라이언트 규약 (초안)

웹 앱과 안드로이드 앱이 함께 지키는 규약이다. 설계서 4.8을 기준으로 하며, 3단계([구현 계획서](implementation-plan.md) S3-15)에서 확정한다. 확정 전까지는 각 절이 비어 있을 수 있다.

## 1. API

- 모든 서버 API는 `/api` 아래에 둔다(예: `/api/health`, `/api/sessions`).
- 타입은 FastAPI OpenAPI 스키마에서 생성한다: 웹은 openapi-typescript, 안드로이드는 openapi-generator.

## 2. SSE 이벤트

`transcript`, `sentence`, `tool`(저장·종료·웹 검색 시작/종료 알림), `done`, `error`. JSON 스키마는 1단계(S1-09)에서 초안, 3단계에서 확정.

## 3. 오디오 형식

업로드 16kHz 모노 Opus, 응답 문장별 MP3.

## 4. 세션 상태 머신

상태: 대기, 듣기, 처리 중, 말하기, 쉬기, 오프라인 보관, 정리. 전이 표는 `shared/fixtures/transitions.json`(S3-09).

## 5. 클라이언트 설정값

기본값은 `shared/client-defaults.json`, 실제 값은 서버 `/api/profile`이 내려준다.

## 6. 알림음·안내 문구

`shared/sounds/`의 효과음과 `shared/client-defaults.json`의 안내 문구를 사용한다.

## 7. 오류 응답

모든 API 오류는 HTTP 상태 코드와 함께 아래 형식으로 내려간다(서버 `app/errors.py`).

```json
{"error": {"code": "not_found", "message": "사람이 읽는 설명", "request_id": "b994ba61…", "details": {}}}
```

- `code`: 클라이언트가 분기에 쓰는 고정 문자열. `message`는 표시용이며 바뀔 수 있다.
- `details`: 선택. `validation_error`이면 필드 오류 목록(`loc`, `msg`, `type`).
- `request_id`: 응답 헤더 `X-Request-ID`와 같다. 문제 보고 시 이 값으로 서버 로그를 찾는다.

| 상태 | `code` | 의미 |
|---|---|---|
| 404 | `not_found` | 없는 경로·리소스 |
| 405 | `method_not_allowed` | 지원하지 않는 메서드 |
| 422 | `validation_error` | 요청 형식 오류 |
| 500 | `internal_error` | 서버 내부 오류(내부 정보는 응답에 넣지 않음) |
| 503 | `db_unavailable` | 데이터베이스 연결 불가 |

기능별 코드(예: `session_not_found`)는 해당 API를 만들 때 이 표에 추가한다.

**요청 ID**: 클라이언트는 `X-Request-ID` 헤더(영문·숫자·`._-`, 64자 이내)를 보낼 수 있고, 없거나 형식이 맞지 않으면 서버가 새로 만든다. 서버는 모든 응답 헤더에 `X-Request-ID`를 넣는다.
