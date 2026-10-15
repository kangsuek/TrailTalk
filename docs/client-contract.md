# 클라이언트 규약 (초안)

웹 앱과 안드로이드 앱이 함께 지키는 규약이다. 설계서 4.8을 기준으로 하며, 3단계([구현 계획서](implementation-plan.md) S3-15)에서 확정한다. 확정 전까지는 각 절이 비어 있을 수 있다.

## 1. API

- 모든 서버 API는 `/api` 아래에 둔다(예: `/api/health`, `/api/sessions`).
- 타입은 FastAPI OpenAPI 스키마에서 생성한다: 웹은 openapi-typescript(`npm run gen:api` → `web/src/api/schema.d.ts`, 서버 `python -m app.openapi`), 안드로이드는 openapi-generator.
- 턴 SSE는 POST 응답이라 `EventSource` 대신 스트림을 직접 읽는다. 파서는 `web/src/core/sse.ts`(줄 끝은 `\r\n`·`\r`·`\n`만, 빈 줄로 끝나지 않은 마지막 메시지는 버림).

## 2. SSE 이벤트

턴 요청(`POST /api/sessions/{id}/turns`)의 응답은 `text/event-stream`이다. 메시지마다 `event: <type>` 줄과 `data: <한 줄 JSON>` 줄, 빈 줄로 이뤄지고 JSON에도 `type`이 들어 있다. 스키마는 OpenAPI components(`StreamEvent`, 서버 `app/api/events.py`)가 기준이다. 1단계 초안이며 3단계(S3-15)에서 확정한다.

| type | 필드 | 의미 |
|---|---|---|
| `turn` | `turn_id` | 스트림의 첫 이벤트. 이번 답변(assistant 턴)의 ID. 끼어들기 `POST /api/sessions/{id}/turns/{turn_id}/cancel`(3단계)에 쓴다 |
| `sentence` | `index`, `text` | 답변 한 문장. `index`는 턴 안에서 0부터. 3단계에서 `audio`(문장 MP3) 추가 |
| `tool` | `phase`(`start`/`call`/`end`), `tool_use_id`, `name`, `input`, `summary`, `is_error` | 도구 사용. `start`에는 이름만 온다(검색 중 표시용). `input`은 `call`에서만, `summary`·`is_error`는 `end`에서만 의미가 있고 나머지 단계에서는 `null`/`false` |
| `done` | `turn_id`, `text`, `interrupted`, `session_status`(`active`/`paused`/`ended`) | 턴 끝. `turn_id`는 `turn` 이벤트와 같다. 전체 답변과 세션 상태 |
| `error` | `code`, `message` | 스트림 도중 오류. 코드는 7절 공통 오류와 같다. 이 뒤에는 이벤트가 오지 않는다 |
| `transcript` | `text` | 3단계에서 추가(현재 스키마에는 없음). 음성 업로드의 STT 결과 |

**도구 이름(`name`)**: `save_note`, `search_notes`, `summarize_session`, `pause_session`, `end_session`, `web_search`, `web_fetch`. 결과 요약(`summary`)은 `web_search`면 `{query, links: [{title, url}]}`, `web_fetch`면 `{code, bytes}`, 앱 도구면 `{result}`다. 결과 형식을 알 수 없으면 `{}`가 온다.

**세션 API**: 대화 화면이 "시작 전"·"끝남" 상태가 되면 `POST /api/sessions/prepare` `{mode}` → 204를 보낸다. 서버가 다음 대화의 CLI를 미리 띄워 인사말 대기를 약 1.4초 줄인다. 대화 탭이 보일 때만 보내고, 화면이 열려 있는 동안 4분마다 다시 보낸다. 결과를 기다리지 않고 실패해도 무시한다. 같은 조건이면 여러 번 불러도 하나만 준비된다. 준비된 지 5분이 지나면 다음 요청 때 새 시각으로 다시 띄우고, 요청이 끊겨 쓰지 않으면 닫힌다. 준비 뒤 프롬프트(호칭·페르소나 등)나 날짜·오전/오후가 바뀌면 시작할 때 새로 띄운다. `POST /api/sessions` `{mode: "text"|"voice"}` → 201 `{session, greeting: {turn_id, text}, persona: {id, name}}`. 화면의 캐릭터 이름은 `persona.name`을 쓰고 코드에 넣지 않는다(NFR-08). `POST /api/sessions/{id}/turns` `{text}`(1~4000자) → 위 SSE. `POST /api/sessions/{id}/end` → `{session, closing, saved: {idea, todo, memo}, journal_status}`(여러 번 불러도 같다). 서버는 세션을 끝내고 일지 정리(추출)를 띄운 뒤 최대 45초 기다려, 이 대화에서 저장한 노트 개수로 만든 마무리 멘트(`closing`, 캐릭터 말풍선으로 보인다)를 준다. `journal_status`가 `pending`이면 정리가 아직 끝나지 않은 것이다(개수가 나중에 늘 수 있다). 기다리는 동안 클라이언트는 정리 중 안내를 보인다. 끝내기 도구로 턴이 끝나 대화가 끝났을 때(`done`의 `session_status: ended`, 또는 `turn` 뒤 `session_ended` 오류)도 클라이언트는 이어서 이 API를 불러 마무리 멘트를 받는다. 쉬기(`paused`) 상태에서 턴을 보내면 다시 `active`가 된다. 서버는 사용자 메시지를 받자마자, 답변은 `sentence`를 보내기 전에 문장마다 저장한다. 그래서 턴 도중 연결이 끊기거나 오류가 나거나 서버가 죽어도 사용자 메시지와 클라이언트가 받은 문장은 모두 기록되고(보내려던 문장이 하나 더 남을 수 있다), 그 답변은 끊긴 답변(`interrupted`)으로 남는다. 첫 문장 전에 끊기면 사용자 메시지만 남는다. 쉬기·끝내기 도구가 불린 뒤 턴이 오류나 연결 끊김으로 끝나도 그 요청은 반영된다. 턴 요청이 `session_ended`·`session_not_found`로 실패하면(시작 전 JSON 오류든 SSE `error` 이벤트든) 클라이언트는 대화를 끝난 상태로 바꾼다. 끝내기 요청 뒤 턴이 오류로 끝나면 서버는 `error` 이벤트를 `session_ended`("대화를 마쳤어요.")로 보낸다. `turn` 이벤트 전에 온 `error`는 서버가 사용자 메시지를 받지 못한 것이므로 클라이언트는 그 메시지를 목록에서 빼고 입력창으로 되돌린다.

**프로필 API**: `GET /api/profile` → `{nickname, interests, persona_id, voice, keep_audio}`(처음 조회하면 기본값으로 만든다). `PUT /api/profile`은 보낸 필드만 바꾼다. `nickname`은 앞뒤 공백을 빼고 1~20자 한 줄이고, `null`이면 기본 호칭으로 돌아간다. `interests`는 최대 10개, 각 1~30자이며 중복은 제거한다. 없는 `persona_id`는 404 `persona_not_found`다. 프로필을 바꾸면 다음 세션부터 반영된다. 진행 중인 세션의 프롬프트는 시작 때 고정돼(서버 `conversation_session.system_prompt`) CLI를 다시 띄우거나 서버를 재시작해도 그대로다.

**순서**: 한 턴은 `turn`으로 시작해 `sentence`·`tool`이 섞여 오다가 `done` 또는 `error` 하나로 끝난다. 모든 필드는 항상 실려 온다(스키마상 required). `summary`의 도구별 타입은 3단계 확정 때 스키마로 고정한다. 시작 전 오류(세션 없음, 진행 중인 턴 등)는 SSE가 아니라 7절의 JSON 오류 응답으로 온다.

## 3. 오디오 형식

업로드 16kHz 모노 Opus, 응답 문장별 MP3.

## 4. 세션 상태 머신

상태: 대기, 듣기, 처리 중, 말하기, 쉬기, 오프라인 보관, 정리. 전이 표는 `shared/fixtures/transitions.json`(S3-09).

## 5. 클라이언트 설정값

기본값은 `shared/client-defaults.json`, 실제 값은 서버 `/api/profile`이 내려준다(3단계 S3-06에서 추가, 지금 응답에는 없다).

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
| 404 | `session_not_found` | 없는 대화 세션 |
| 409 | `session_ended` | 이미 끝난 세션에 턴 요청 |
| 409 | `turn_in_progress` | 같은 세션의 이전 답변이 아직 진행 중 |
| 500 | `persona_invalid` | 서버의 페르소나 YAML 오류(프로필 요청에서 올 수 있다. 세션 시작에서는 일반 문구로 바뀐다) |
| 401·403·409·429 등 | `unauthorized`·`forbidden`·`conflict`·`too_many_requests`, 그 밖은 HTTP 상태 이름 | 일반 HTTP 오류(`server/app/errors.py`) |
| 404 | `persona_not_found` | 없는 페르소나(`PUT /api/profile`) |
| 502 | `llm_error` | 인사말·답변을 만들지 못함(SSE에서는 `error` 이벤트) |
| 502 | `llm_process_exited` | Claude CLI 프로세스가 끝남. 다음 요청에서 맥락을 이어 다시 띄운다 |
| 504 | `llm_timeout` | 답변 시간 초과 |

기능별 코드(예: `session_not_found`)는 해당 API를 만들 때 이 표에 추가한다.

**클라이언트 측 코드**(서버가 보내지 않고 클라이언트가 만든다, 웹 `src/api/conversation.ts`): `network_error`(서버에 연결할 수 없음, 또는 JSON 본문 없는 502·503·504: 개발 프록시·터널이 서버 중단 때 주는 응답), `http_error`(오류 응답이 공통 형식이 아님), `stream_closed`(턴 스트림이 `done`·`error` 없이 끊김), `bad_event`(SSE `data`가 JSON이 아님). 안드로이드도 같은 코드를 쓴다.

**요청 ID**: 클라이언트는 `X-Request-ID` 헤더(영문·숫자·`._-`, 64자 이내)를 보낼 수 있고, 없거나 형식이 맞지 않으면 서버가 새로 만든다. 서버는 모든 응답 헤더에 `X-Request-ID`를 넣는다.
