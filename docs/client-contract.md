# 클라이언트 규약

웹 앱이 지키는 클라이언트 규약이다. 설계서 4.8을 기준으로 하며 3단계([구현 계획서](implementation-plan.md) S3-15, 2026-10-17)에서 확정했다. 웹 앱은 이 문서, OpenAPI 스키마, 상태 전이 표(`shared/fixtures/transitions.json`), 클라이언트 설정값(`shared/client-defaults.json`)을 기준으로 만든다.

**바꾸는 규칙**: 규약을 바꾸면 같은 커밋에서 이 문서와 서버 스키마(`npm run gen:api`로 웹 타입), 전이 표를 함께 고친다. 서버가 새 이벤트·필드를 먼저 더할 수 있으므로 클라이언트는 모르는 이벤트 `type`과 필드를 무시한다(앱이 멈추지 않게).

## 1. API

- 모든 서버 API는 `/api` 아래에 둔다(예: `/api/health`, `/api/sessions`).
- 타입은 FastAPI OpenAPI 스키마에서 생성한다: 웹은 openapi-typescript(`npm run gen:api` → `web/src/api/schema.d.ts`, 서버 `python -m app.openapi`).
- 턴 SSE는 POST 응답이라 `EventSource` 대신 스트림을 직접 읽는다. 파서는 `web/src/core/sse.ts`(줄 끝은 `\r\n`·`\r`·`\n`만, 빈 줄로 끝나지 않은 마지막 메시지는 버림).
- 폰 접속(결정 D1): 서버는 집 Mac에서 돌고, 폰은 Tailscale Serve가 tailnet 안에만 여는 HTTPS 주소(`https://<Mac 기기 이름>.<tailnet>.ts.net/`)로 접속한다(`./run.sh --phone`, `docs/phone.md`). 브라우저 마이크는 HTTPS(또는 localhost)에서만 열린다. 서버 API에는 로그인이 없으므로 공개 주소로 열지 않는다. 앱 도구 경로 `/internal/*`은 프록시를 거친 요청을 403으로 막는다.
- Claude 남은 토큰(S3-36): `GET /api/usage` → `{status, five_hour, seven_day, updated_at}`. 한도는 `{utilization, resets_at}`(쓴 비율 0~1, 초기화 시각) 또는 `null`이다. 서버는 CLI가 답변마다 알려 주는 구독 한도(`rate_limit_event`)의 마지막 값을 메모리에 두므로, 서버를 켠 뒤 첫 답변 전에는 모두 `null`이다(따로 조회할 방법이 없다). `status`는 `allowed`·`allowed_warning`·`rejected`. 클라이언트는 화면 위 고정 헤더 아래에 두 한도 중 덜 남은 쪽을 "남은 %·N시간 뒤 초기화"로 보이고(초기화 시각이 지난 한도는 100%), 서버 상태 확인과 함께 30초마다·화면이 다시 보일 때 다시 불러온다. 남은 % 계산은 `web/src/core/usage.ts`.
- 웹 PWA: 서비스 워커는 앱 셸만 미리 저장하고, 음성 감지 자산(5절의 `/vad/<…>/`)은 처음 쓸 때 저장한다. `/api`·`/internal`은 다루지 않아 SSE·업로드는 늘 네트워크로 간다. 새 버전은 자동으로 새로 고치지 않고 화면 위 "새 버전 적용" 버튼으로 바꾼다(대화 중 페이지가 다시 열리지 않게).

## 2. SSE 이벤트

턴 요청(텍스트 `POST /api/sessions/{id}/turns`, 음성 `POST /api/sessions/{id}/turns/audio`)의 응답은 `text/event-stream`이다. 메시지마다 `event: <type>` 줄과 `data: <한 줄 JSON>` 줄, 빈 줄로 이뤄지고 JSON에도 `type`이 들어 있다. 스키마는 OpenAPI components(`StreamEvent`, 서버 `app/api/events.py`)가 기준이다.

| type | 필드 | 의미 |
|---|---|---|
| `turn` | `turn_id` | 스트림의 첫 이벤트. 이번 답변(assistant 턴)의 ID. 끼어들기 `POST /api/sessions/{id}/turns/{turn_id}/cancel`에 쓴다(아래 끼어들기 API) |
| `sentence` | `index`, `text`, `audio` | 답변 한 문장. `index`는 턴 안에서 0부터. `audio`는 그 문장의 MP3(base64)로, 음성 세션에서만 오고 텍스트 세션이나 합성 실패면 `null`이다(클라이언트는 글자를 보이거나 기기 TTS로 대신한다) |
| `tool` | `phase`(`start`/`call`/`end`), `tool_use_id`, `name`, `input`, `summary`, `is_error`, `notice` | 도구 사용. `start`에는 이름만 온다(검색 중 표시용). `input`은 `call`에서만, `summary`·`is_error`는 `end`에서만 의미가 있고 나머지 단계에서는 `null`/`false`. `notice`(`{text, audio}`)는 음성 세션에서 캐릭터가 아무 말 없이 `web_search`·`web_fetch`를 시작할 때만 `start`에 실리는 안내 음성이다(턴마다 한 번). 답변 문장이 아니라 `index`·`done.text`에 들어가지 않는다. 클라이언트는 문장처럼 재생 대기열에 넣는다 |
| `done` | `turn_id`, `text`, `interrupted`, `session_status`(`active`/`paused`/`ended`) | 턴 끝. `turn_id`는 `turn` 이벤트와 같다. 전체 답변과 세션 상태 |
| `error` | `code`, `message` | 스트림 도중 오류. 코드는 7절 공통 오류와 같다. 이 뒤에는 이벤트가 오지 않는다 |
| `transcript` | `text` | 음성 턴에서만 `turn` 바로 앞에 오는 첫 이벤트. 인식한 글(사용자 메시지로 저장된 글)이다 |

**도구 이름(`name`)**: `send_email`(대화를 설정한 이메일 주소로 보내기, FR-21), `save_note`, `search_notes`, `search_conversations`(지난 대화 전체의 주고받은 말 찾기, S3-28. 음성 대화에서 말없이 시작하면 `web_search`처럼 안내 음성 `notice`가 붙는다), `summarize_session`, `pause_session`, `end_session`, `set_nickname`, `set_model`(대화 모델 바꾸기, S3-31), `web_search`(내장 웹 검색 또는 검색 API 도구 `search_USA`(해외·영어권)·`search_naver`(국내 뉴스). 서버가 이들을 같은 이름·같은 `web_search` 요약으로 보내므로 클라이언트는 구분하지 않는다), `web_fetch`.

**결과 요약(`summary`)**: `end`에서만 오며 `kind`로 종류를 구분한다(OpenAPI `WebSearchSummary`·`WebFetchSummary`·`ToolResultSummary`). 결과 형식을 알 수 없으면 `null`이다. 모르는 `kind`(서버가 나중에 더한 종류)는 `null`처럼 다루고 이벤트를 버리지 않는다(생성한 판별 타입이 역직렬화에 실패하지 않게 한다). 화면의 출처 표시는 서버가 준 호스트 이름을 그대로 쓴다(클라이언트는 URL을 해석하지 않는다).

| `kind` | 필드 | 의미 |
|---|---|---|
| `web_search` | `query`, `links: [{title, url}]`(최대 10개), `sources: [호스트]` | 검색어와 결과 링크. `sources`는 링크의 호스트 이름(`www.` 뗌, 중복 없이 링크 순서로 최대 3개)이다. 비어 있으면 화면은 "검색 완료" |
| `web_fetch` | `code`, `bytes`, `url`, `host` | 읽은 페이지의 HTTP 상태·크기·주소와 출처 호스트. `code`가 400 이상이면 읽지 못한 것으로 본다 |
| `result` | `result` | 앱 도구(`save_note` 등)가 돌려준 값(보통 한 줄 문자열) |

**세션 API**: 대화 화면이 "시작 전"·"끝남" 상태가 되면 `POST /api/sessions/prepare` `{mode}` → 204를 보낸다. 서버가 다음 대화의 CLI를 미리 띄워 인사말 대기를 약 1.4초 줄인다. 대화 탭이 보일 때만 보내고, 화면이 열려 있는 동안 4분마다 다시 보낸다. 결과를 기다리지 않고 실패해도 무시한다. 같은 조건이면 여러 번 불러도 하나만 준비된다. 준비된 지 5분이 지나면 다음 요청 때 새 시각으로 다시 띄우고, 요청이 끊겨 쓰지 않으면 닫힌다. 준비 뒤 프롬프트(호칭·페르소나 등)나 날짜·오전/오후가 바뀌면 시작할 때 새로 띄운다. `POST /api/sessions` `{mode: "text"|"voice"}` → 201 `{session, greeting: {turn_id, text, audio}, persona: {id, name}}`. `greeting.audio`는 인사말 MP3(base64)로 음성 세션에서만 오고, 합성에 실패하면 `null`이어도 세션은 시작된다. 화면의 캐릭터 이름은 `persona.name`을 쓰고 코드에 넣지 않는다(NFR-08). `POST /api/sessions/{id}/turns` `{text}`(1~4000자) → 위 SSE. **음성 턴**: `POST /api/sessions/{id}/turns/audio`, 본문은 말 한 번의 오디오 바이트 그대로(multipart 아님), `Content-Type`은 녹음 형식(웹 `audio/webm`. 3절) → 위 SSE(`transcript` → `turn` → …). 서버는 SSE를 열기 전에 인식하므로 오디오·인식 오류와 말 없음은 JSON 오류다: `audio_invalid`(400, 너무 크면 413), `no_speech`(422, 인식 결과에 말이 없음), `stt_failed`·`stt_timeout`·`voice_unavailable`. 이 오류들은 사용자 메시지를 만들지 않는다(상태 머신에는 `turn_error {turnId: null}`). 인식 뒤 스트림을 열 때 다른 턴이 진행 중이거나 세션이 끝났으면 `transcript` 없이 `error`(`turn_in_progress`·`session_ended`)가 첫 이벤트로 온다(인식한 글은 저장되지 않는다). 텍스트 세션에서도 음성 턴을 보낼 수 있고 그때 문장 `audio`는 `null`이다. `POST /api/sessions/{id}/end` → `{session, closing, closing_audio, saved: {idea, todo, memo}, journal_status}`(여러 번 불러도 같다. `closing_audio`는 마무리 멘트 MP3(base64)로 음성 세션에서만, 실패하면 `null`). 서버는 세션을 끝내고 일지 정리(추출)를 띄운 뒤 최대 45초 기다려, 이 대화에서 저장한 노트 개수로 만든 마무리 멘트(`closing`, 캐릭터 말풍선으로 보인다)를 준다. `journal_status`가 `pending`이면 정리가 아직 끝나지 않은 것이다(개수가 나중에 늘 수 있다). 기다리는 동안 클라이언트는 정리 중 안내를 보인다. 끝내기 도구로 턴이 끝나 대화가 끝났을 때(`done`의 `session_status: ended`, 또는 `turn` 뒤 `session_ended` 오류)도 클라이언트는 이어서 이 API를 불러 마무리 멘트를 받는다. 쉬기(`paused`) 상태에서 턴을 보내면 다시 `active`가 된다. 마지막 발화 뒤 30분 동안 말이 없으면(쉬는 중 포함) 서버가 세션을 끝내고 일지를 정리한다(클라이언트 타이머의 안전망). 그 뒤 턴 요청은 `session_ended`가 된다. 서버는 사용자 메시지를 받자마자, 답변은 `sentence`를 보내기 전에 문장마다 저장한다. 그래서 턴 도중 연결이 끊기거나 오류가 나거나 서버가 죽어도 사용자 메시지와 클라이언트가 받은 문장은 모두 기록되고(보내려던 문장이 하나 더 남을 수 있다), 그 답변은 끊긴 답변(`interrupted`)으로 남는다. 첫 문장 전에 끊기면 사용자 메시지만 남는다. 쉬기·끝내기 도구가 불린 뒤 턴이 오류나 연결 끊김으로 끝나도 그 요청은 반영된다. 턴 요청이 `session_ended`·`session_not_found`로 실패하면(시작 전 JSON 오류든 SSE `error` 이벤트든) 클라이언트는 대화를 끝난 상태로 바꾼다. 끝내기 요청 뒤 턴이 오류로 끝나거나, 턴 도중 다른 곳(끝내기 API·무발화 감시)이 세션을 끝내면 서버는 `error` 이벤트를 `session_ended`("대화를 마쳤어요.")로 보낸다. 무발화로 끝난 세션의 `ended_at`은 마지막 발화 시각이다. `turn` 이벤트 전에 온 `error`는 서버가 사용자 메시지를 받지 못한 것이므로 클라이언트는 그 메시지를 목록에서 빼고 입력창으로 되돌린다. **다시 열기(S3-26)**: `POST /api/sessions/{id}/reopen` `{mode}` → 200 `{session, greeting: {turn_id, text, audio}, persona, turns: [턴]}`. 끝난 대화를 같은 세션으로 다시 열어 이어서 대화한다(일지 상세의 "글로 이어서"·"음성으로 이어서"). 끝나지 않은 대화(대화 화면을 닫았거나 다른 기기에서 남은 대화, S3-37)도 같은 요청으로 이어받는다: 서버는 지금 CLI를 닫고 끝난 대화처럼 새로 띄운다(실패하면 원래 진행 중 상태로 남는다). `mode`는 이번에 쓸 방식이며 처음과 달라도 된다. 서버는 저장된 전문을 새 프롬프트에 넣어 캐릭터를 다시 띄우고(일지 정리가 끝났고 전문이 길면 앞부분은 그 정리(제목·요약·확인할 것·노트)로 대신하고 최근 원문 약 4천 자만 넣어 턴마다 읽히는 양을 줄인다, S3-27), 직전 이야기를 짚는 재개 인사말(`greeting`, 음성이면 `audio`)을 전문 끝에 새 턴으로 남긴다. `turns`는 그 인사말까지 포함한 전체 전문(일지 상세의 `turns`와 같은 형식)이라 클라이언트는 이것으로 이전 말풍선을 채운다. 그 뒤 턴·끝내기·쉬기·무발화 종료는 새 대화와 같다. 다시 연 동안 일지는 진행 중(`status: active`, `journal_status: null`)으로 보이고, 돌던 일지 정리는 멈춘다. 다시 끝내면 일지를 새로 정리한다: 요약·태그·주제·확인할 것은 전문 전체로 새로 쓰고, 노트는 지우지 않으며(별표·완료·고친 내용 유지) 새 노트만 더하고, 고친 제목은 유지된다. 일지 날짜(`date`, `started_at`)는 처음 시작한 날 그대로다. 끝내기 응답의 `saved`는 다시 연 뒤 생긴 노트만 센다. 답변을 만드는 중이면 409 `turn_in_progress`, 없으면 404 `session_not_found`, 재개 인사말을 받지 못하면 시작 실패와 같은 오류이고 대화는 원래 상태로 남는다. 다른 대화가 진행 중일 때 다시 열면 서버는 막지 않으므로 클라이언트가 막는다(진행 중인 대화를 끝낸 뒤 이어서 할 수 있다고 안내). 일지 상세에서 이 화면이 지금 진행 중인 대화는 다시 열지 않고 대화 화면으로 돌아가며, 열려 있지 않은 진행 중 대화에는 이어서 버튼과 "대화 끝내기"(끝내기 API, 끝내야 지울 수 있다)를 보인다. 재개 인사말 턴은 첫 인사말처럼 끼어들어도 잘리지 않는다.

**끼어들기 API**: `POST /api/sessions/{id}/turns/{turn_id}/cancel` `{last_played}` → 204. `last_played`는 끝까지 들려준 마지막 문장 번호(`sentence.index`)이고 하나도 못 들려줬으면 -1이다. 서버는 그 턴이 진행 중이면 CLI를 인터럽트하고(남은 합성은 버린다) 턴이 끝나기를 최대 10초 기다린 뒤, 답변 기록을 `last_played`번 문장까지로 자르고 `interrupted`로 표시한다. 끝난 턴(다 받은 뒤 재생 중 끊기)도 같게 자른다. 다 들었으면(마지막 문장 번호 이상) 바꾸지 않는다. 여러 번 불러도 같다. 인사말(seq 0)은 문장 번호 없이 재생되므로 자르지 않는다. 자른 경우 다음 턴에 CLI에만 "직전 답변을 어디까지 들었는지" 안내를 붙인다(기록에는 남지 않는다). 없는 세션은 404 `session_not_found`, 이 대화의 캐릭터 답변이 아니면 404 `turn_not_found`다. 첫 문장 전에 연결이 끊겨 답변 기록이 아직 없는 턴도 `turn_not_found`일 수 있으며 클라이언트는 이 결과를 무시한다. 클라이언트는 cancel과 함께 턴 스트림도 끊는다(계속 읽으면 `done.text`는 자르기 전 전체 답변이다). 자르기와 다음 턴 안내는 턴 락 안에서 하므로 그 짧은 동안 새 턴은 `turn_in_progress`가 될 수 있다. 진행 중인 턴이 10초 안에 멈추지 않으면 자르지 않는다.

**기록만 남기기(S3-12)**: `POST /api/sessions/{id}/turns/audio/record`, 본문은 음성 턴과 같은 오디오 바이트 → 201 `{text}`. 인식한 말을 사용자 턴으로만 저장하고 캐릭터는 대답하지 않는다. 대답할 수 없는 보관한 말(서버가 대화를 끝냄, 새로 고쳐 대화가 사라짐)의 유실을 막는 데 쓴다. 끝난 대화도 받으며 그때는 일지를 다시 정리한다(새 말에서 나온 노트만 더해진다). 진행 중인 턴이 있으면 409 `turn_in_progress`, 말이 없으면 422 `no_speech`, 없는 세션은 404 `session_not_found`.

**지연 측정(S3-07, NFR-01)**: 서버는 음성 턴마다 요청 처리를 시작한 때를 기준으로 단계 시간(ms)을 남긴다: `upload_ms`(세션 확인과 본문 다 받기까지), `stt_ms`(형식 변환과 인식), `first_token_ms`(CLI 첫 글자), `first_sentence_ms`(첫 문장을 소리와 함께 보냄), `done_ms`(턴 끝), `audio_bytes`. 클라이언트는 말이 실제로 끝난 때(VAD가 끝을 알아챈 때에서 무음 대기 `end_of_speech_silence_ms`를 뺀 시각)부터 요청을 시작한 때까지(`speech_to_request_ms`), 요청 시작부터 그 턴의 첫 소리가 재생되기 시작한 때까지(`request_to_playback_ms`, 검색 안내 음성 포함)를 재서 `POST /api/sessions/{id}/turns/{turn_id}/latency` `{speech_to_request_ms, request_to_playback_ms, first_sound_notice}`(0~600000, `first_sound_notice`는 첫 소리가 검색 안내 음성이었는지) → 204로 한 번 보낸다(기다리지 않고 실패는 무시, 끊은 턴·소리 없이 끝난 턴은 보내지 않음, 마무리 멘트 소리는 재지 않음, 다시 보내면 덮어씀, 측정 행이 없으면 404 `turn_not_found`). `GET /api/latency?limit=100`(1~500) → `{turns: [... , first_sound_notice, total_ms], summary: {count, total_ms: {median, p90}, total_ms_reply: {median, p90}, stages: {단계: 중앙값}}}`(최근 음성 턴부터). `total_ms`는 두 보고값의 합(말 끝 → 캐릭터 첫 소리)이고, `total_ms_reply`는 첫 소리가 답변 문장인 턴만의 값이다(검색 턴은 안내 음성이 답변 지연을 가린다).

**일지 API**: `GET /api/journal?from=YYYY-MM-DD&to=YYYY-MM-DD` → 일지 목록(최신순). 날짜는 서버 시간대의 현지 날짜이고 둘 다 포함하며, 생략하면 최근 30일이다(한 번에 366일까지, 2000-01-01~9998-12-31 밖이거나 범위가 틀리면 422 `invalid_range`). 사용자가 한마디도 하지 않은 대화는 빠진다. 항목은 `{id, date, started_at, ended_at, status, title, summary: [줄], tags, topics, journal_status, counts: {idea, todo, memo}}`이고, 클라이언트는 `date`로 날짜별로 묶는다(시간대 계산을 하지 않는다). `topics`는 이 대화에서 다룬 아이디어 주제 이름 목록(0~3개)이다. 서버가 같은 아이디어에는 같은 이름을 붙이므로 클라이언트는 이름이 같은 대화끼리 아이디어별로 묶는다(한 대화가 여러 묶음에 나올 수 있고, 빈 목록이면 "기타"). 정리 전이거나 아이디어가 없는 대화는 빈 목록이다. `journal_status`는 `pending`(정리 중)·`done`·`failed`(정리 실패)·`null`(정리 기록 없음: 아직 끝나지 않은 대화, 또는 일지 정리가 생기기 전에 끝난 대화)이다. `GET /api/journal/{id}` → `{session: 위 항목, summary_cites, citations, checks, persona_name, notes: [{id, kind, content, starred, done, created_at, cites}], turns: [{id, seq, role, text, interrupted, created_at}]}`(없으면 404 `session_not_found`. 목록에서 빠지는 대화도 ID로는 조회된다). `turns`는 전문이고 `interrupted`는 끝까지 말하지 못한 답변이다. 일지 인용(S3-23): 검색으로 알게 된 요약 줄·메모에는 근거 출처 번호가 붙는다. `summary_cites[i]`는 `session.summary[i]`의 번호(같은 길이, 없으면 빈 목록), 노트의 `cites`는 그 메모의 번호, `citations`는 `[{n, title, url}]` 인용 목록이다. 클라이언트는 문장 끝에 `[1][2]`를, 맨 아래 "인용:" 아래에 `[n] 제목 URL`(제목은 링크, http(s)만)을 그린다. 번호는 서버가 대화 중 캐릭터가 본 검색 결과에 맞춰 검증하고 1부터 다시 매긴 것이며, 검색하지 않은 대화·예전 일지는 빈 목록이다. 일지 표시(S3-24): `checks`(확인할 것 목록)가 null이 아니면 새 형식이다. `session.summary` 첫 줄은 결론(굵게), 나머지 줄은 "알게 된 것", `checks`는 "확인할 것"으로 그리고, 태그는 인용 뒤 맨 아래에 둔다. `checks`가 null이면 예전 형식(요약 줄 목록)이며, 끝난 대화면 다시 정리해 새 형식으로 바꿀 수 있다(다시 정리해도 노트는 새로 넣지 않는다). 전문의 캐릭터 화자 이름은 `persona_name`(현재 프로필의 페르소나 이름)을 쓴다(코드에 두지 않는다). `POST /api/journal/{id}/retry` → 202 일지 항목: 정리에 실패했거나(`failed`) 정리 기록이 없는(`null`) 끝난 대화, 또는 예전 형식으로 정리된(`done`인데 `checks`가 null) 대화를 다시 정리한다. 정리 중·완료면 아무것도 하지 않고 그대로 준다(끝나지 않은 대화는 409 `session_not_ended`). 클라이언트는 `journal_status`가 `pending`인 동안 목록·상세를 3초마다(최대 약 2분) 다시 불러와 정리가 끝난 것을 보여 준다. `PATCH /api/journal/{id}` `{title}` → 바뀐 일지 항목: 대화 제목을 고친다(줄바꿈·연속 공백은 한 칸으로 줄인 뒤 1~200자, 없으면 404 `session_not_found`). 고친 제목은 일지를 다시 정리해도 바뀌지 않는다. `DELETE /api/journal/{id}` → 204: 대화와 노트·전문·지연 기록·보관한 녹음을 모두 지운다. 진행 중(`active`)인 대화는 409 `session_active`(끝낸 뒤 지운다), 답변을 만드는 중이면 409 `turn_in_progress`, 쉬는 중(`paused`)이면 CLI를 정리하고 지운다. 정리 중이던 일지 정리는 멈춘다. 여러 개를 한 번에 지울 때(S3-25)는 일괄 API 없이 고른 항목마다 이 요청을 차례로(동시에 보내지 않고) 부르고, 404는 이미 지워진 것으로 보며, 실패한 항목만 선택된 채 남긴다. `PATCH /api/notes/{id}` `{starred?, done?, content?}` → 바뀐 노트. 아이디어의 `done`은 다 했거나 접은 아이디어를 닫는 데 쓴다(다음 대화의 기억에서 빠진다). 보낸 필드만 바꾸며 `content`는 앞뒤 공백을 빼고 1~500자이며 여러 줄도 된다(없으면 404 `note_not_found`). `GET /api/notes/latest-idea` → `{id, content, starred, session_id}` 또는 `null`(S3-39): 대화 시작 화면의 "지난 아이디어 이어 가기" 카드. 완료하지 않은 아이디어 하나를 기억 블록과 같은 순서(별표 먼저, 최신순)로 고른다. 클라이언트는 대화 전 시작 화면이 보일 때마다 다시 불러오고(끝난 대화 화면에는 두지 않는다), `null`이거나 못 불러오면 카드를 숨기며, 누르면 `session_id`의 일지 상세를 연다(거기서 이어서 하기).

**프로필 API**: `GET /api/profile` → `{nickname, email, mail_ready, interests, persona_id, voice, speaking_rate, keep_audio, chat_model, default_chat_model, client}`(처음 조회하면 기본값으로 만든다). `client`는 5절의 클라이언트 설정값이고 읽기 전용이다(`PUT`에 보내면 422). `PUT /api/profile`은 보낸 필드만 바꾼다. `nickname`은 앞뒤 공백을 빼고 1~20자 한 줄이고, `null`이면 기본 호칭으로 돌아간다. `email`은 대화를 보낼 본인 주소(앞뒤 공백을 빼고 이메일 모양 254자 이내, 틀리면 422)이고 `null`이면 설정 안 함이다. `mail_ready`는 서버에 메일 보내기(SMTP) 설정이 있는지(읽기 전용)다. `interests`는 최대 10개, 각 1~30자이며 중복은 제거한다. `voice`는 `GET /api/voices`의 `voices` 안의 이름만 받고(틀리면 422) `speaking_rate`는 0.75~1.5다. 둘 다 `null`이면 캐릭터(페르소나 YAML) 기본값을 쓴다. 바꾼 보이스·말 속도는 다음 답변(인사말·문장·마무리 멘트)부터, 호칭·관심사는 다음 대화의 프롬프트부터 쓴다. 말 속도를 정하면 서버가 음성 말투 지시에도 빠르기를 붙인다(모델이 `speed`를 덜 따르기 때문). `GET /api/voices` → `{voices, default_voice, default_rate, min_rate, max_rate}`, `GET /api/voices/{voice}/sample?rate=`는 고정 문장의 미리 듣기 MP3(보이스·속도별로 한 번만 합성, 합성할 수 없으면 503 `voice_unavailable`). 없는 `persona_id`는 404 `persona_not_found`다. `keep_audio`(기본 `false`)를 켜면 이후 음성 턴의 녹음(인식에 넘긴 파일: 인식이 바로 받는 형식 webm·wav·mp3·m4a는 올린 그대로, 그 밖은 서버가 바꾼 webm/opus)을 서버가 사용자 턴에 붙여 보관하고 30일(`AUDIO_RETENTION_DAYS`)이 지나면 지운다. 끄면 이후 녹음은 저장하지 않고, 이미 저장한 녹음은 같은 기간 뒤 지운다. 녹음은 본인만 읽을 수 있는 권한으로 저장한다. 저장에 실패해도 턴은 그대로 진행한다(경로를 남기지 못하면 파일도 지운다). 웹 설정 화면은 S3-18에서 만들었다. 진행 중인 세션의 프롬프트는 시작 때 고정돼(서버 `conversation_session.system_prompt`) CLI를 다시 띄우거나 서버를 재시작해도 그대로다. 예외로 대화 중 사용자가 호칭을 바꿔 달라고 하면 캐릭터가 `set_nickname` 도구로 같은 `nickname`을 바꾸고 그 대화에서도 바로 새 호칭을 쓴다(이번 사용자 발화에 나온 호칭만 받는다). **대화 모델(S3-31)**: `chat_model`은 `haiku`·`sonnet`·`opus` 중 하나이고(그 밖은 422) `null`이면 서버 기본값(`default_chat_model`, 서버 설정 `LLM_CHAT_MODEL`)을 쓴다. 진행 중인 대화에도 다음 답변부터 쓴다(서버가 답변 사이에 같은 대화 맥락으로 CLI를 새 모델로 다시 띄우므로 바꾼 직후 첫 답변은 조금 늦을 수 있다). 대화 중 사용자가 모델을 바꿔 달라고 하면("빠른 모델로" 등) 캐릭터가 `set_model` 도구로 같은 `chat_model`을 바꾼다(이번 사용자 발화에 "모델"이나 모델 이름이 있을 때만 받는다). 일지 정리 모델은 따로이며 바뀌지 않는다.

**순서**: 한 턴은 `turn`으로 시작해(음성 턴은 그 앞에 `transcript`) `sentence`·`tool`이 섞여 오다가 `done` 또는 `error` 하나로 끝난다. 모든 필드는 항상 실려 온다(스키마상 required). 시작 전 오류(세션 없음, 진행 중인 턴 등)는 SSE가 아니라 7절의 JSON 오류 응답으로 온다.

## 3. 오디오 형식

- 업로드: 말 한 번을 하나의 오디오로 보낸다. 권장은 16kHz 모노 Opus(웹 `audio/webm;codecs=opus`). 웹은 VAD가 준 16kHz 발화 오디오를 WebCodecs `AudioEncoder`로 24kbps Opus로 인코딩해 webm에 담고(mediabunny, `web/src/platform/encodeAudio.ts`), 브라우저가 Opus 인코딩을 못 하면 16bit PCM WAV(`audio/wav`, 약 10배 큼)로 보낸다. 서버는 webm·wav·mp3·m4a(mp4)는 그대로 인식에 넘기고, 그 밖의 형식(ogg 등)은 16kHz 모노 webm/opus로 바꾼다. 최대 10MB, 변환은 앞 120초까지.
- 응답: 문장별 MP3(base64, `sentence.audio`), 인사말·마무리 멘트도 MP3(base64)다.

## 4. 세션 상태 머신

음성 대화는 아래 상태를 오가는 하나의 루프다(설계서 4.1). 상태 머신은 이벤트를 받아 다음 상태와 **명령**을 돌려주는 순수 함수이고(웹 `web/src/core/sessionMachine.ts`), 마이크·재생·서버 호출·타이머는 화면·플랫폼 계층이 명령을 받아 실행한다. 전이 표 `shared/fixtures/transitions.json`(S3-09, version 1, 사례 33개)을 웹 테스트(Vitest)가 읽는다. 각 사례는 대기에서 시작해 단계마다 이벤트를 넣고 상태 이름·명령 목록(순서 포함)·지정한 context 값을 확인한다.

- **상태**(코드 이름): 대기 `idle`, 듣기 `listening`, 처리 중 `processing`, 말하기 `speaking`, 쉬기 `paused`, 오프라인 보관 `offline`, 정리 `closing`.
- **이벤트**: 버튼 `tap`·`long_press`·`pause`(일시 중단), 시작 `session_started`(인사말 재생 시작)·`start_failed`, 발화 감지 `speech_start`·`speech_end`, 턴 스트림 `turn`·`sentence`·`turn_done`·`turn_error`·`note_saved`, 재생 `sentence_played`·`playback_idle`, 오프라인 `send_failed`·`offline_notice_done`·`online`·`queue_sent`·`queue_send_failed`, 그 밖 `idle_timeout`·`session_closed`·`end_failed`.
- **명령**: `startSession`, `sendTurn`, `cancelTurn`(턴 ID와 마지막으로 다 들려준 문장 번호), `endSession`, `micOn`·`micOff`, `setVadMode`(재생 중 `playback`으로 임계값 상향), `stopPlayback`, `queueUtterance`, `speakOfflineNotice`, `sendQueued`, `playSound`(`listen`·`saved`·`offline`), `notifyError`, `startIdleTimer`·`clearIdleTimer`.
- **규칙 요약**
  - 한 번 누르기: 대기에서는 시작, 말하기·처리 중에는 끼어들기(재생을 멈추고 취소 뒤 듣기. 처리 중에도 검색 안내 음성이 나오고 있을 수 있다), 쉬기에서는 다시 듣기.
  - 길게 누르기: 대기 외 어디서나 종료(정리 중이면 끝내기 응답을 기다리지 않고 대기로).
  - 일시 중단(`pause`, 화면의 "일시 중단" 버튼): 듣기에서만 받아 쉬기로 간다. 마이크를 끄고(`micOff`) 무발화 타이머를 다시 시작하며, 말하던 중이면 그 말은 버린다. 서버 호출은 없다(서버 세션은 그대로 진행 중이고 무발화 감시가 같은 30분 기준으로 정리한다). 다시 듣기는 쉬기의 `tap`이다. 다른 상태에서는 무시한다.
  - 답변 문장을 다 들려주고 턴이 끝나면 `done`의 `session_status`에 따라 듣기·쉬기·정리로 간다.
  - 듣기·쉬기에서 30분(`idle_timeout_minutes`) 동안 말이 없으면 정리로 간다. 서버 안전망과 같은 기준이다.
  - 오프라인 큐(S3-12): 새 말을 보내다 서버에 닿지 않으면(`send_failed`) 큐에 넣고 오프라인 안내 뒤 듣는다(`connected=false`). 연결되면(`online`) 큐의 말을 가장 오래된 것부터 보통 턴으로 보내(`sendQueued`) 캐릭터가 차례로 대답한다. 턴을 다 들려주고 끝났을 때·오프라인 안내가 끝났을 때·쉬기에서 다시 들을 때·오류 뒤에도 연결돼 있고 큐가 있으면 듣기 대신 큐부터 보낸다(끼어들기는 사용자가 말하려는 것이므로 바로 듣는다). 큐가 남아 있는 동안 한 새 말은 큐 뒤에 넣어 순서를 지킨다. 처리 중(답변을 기다리는 중, 보관한 말을 보내는 중 `sendingQueued` 모두)에 들어온 발화(`speech_end`)도 버리지 않고 큐 뒤에 넣어(`queueUtterance`) 턴이 끝나면 연결돼 있는 한 차례로 보낸다(잠깐 쉬었다 이어 말한 뒷말을 잃지 않게). 끼어든 뒤 큐가 남아 있으면 다음 턴이 끝날 때(또는 다음 말) 이어서 보낸다. 큐의 말을 서버가 받으면 `queue_sent {remaining}`, 보내다 서버에 닿지 않으면 `queue_send_failed`(안내 없이 듣기, 말은 큐에 그대로)다. 상태에는 `connected`(서버에 닿는가)가 있다.
  - 이어 말하기(S3-33): 상태에는 `userSpeaking`(마이크가 켜진 상태에서 `speech_start` 뒤 `speech_end` 전, 쉬기·정리에서 false)이 있다. 처리 중에 말을 시작해 아직 끝나지 않았는데 첫 답변 문장(`sentence`)이 오면 끼어들기로 처리한다(재생을 멈추고 들려준 문장 없이 취소한 뒤 듣기). 반쪽 말에 답하지 않고 이어 하는 말을 다음 턴으로 보낸다. `speech_start`는 발화마다 한 번이라 이렇게 하지 않으면 말하기에서도 끼어들기가 되지 않는다. 말하기 중에 끝난 말(`speech_end`)도 버리지 않고 큐 뒤에 넣는다.
  - 표에 없는 조합과 모르는 이벤트는 무시한다.
- **플랫폼이 지킬 것**
  - 인사말은 SSE가 아니라 시작 응답으로 온다. 재생을 시작하며 `session_started {turnId}`(인사말 턴 ID)를 보내고, 재생할 소리가 없으면 바로 `playback_idle`을 보낸다.
  - `sentence`·`turn_done`에는 턴 ID를 싣는다. 머신은 지금 턴과 다른 ID의 이벤트(취소한 턴의 늦은 이벤트)를 무시한다. `turn_error`는 턴 시작 전 오류면 `turnId: null`이다.
  - `sentence` 이벤트는 그 문장 소리를 재생 대기열에 넣은 뒤에 머신에 보낸다. `playback_idle`은 보내는 순간 대기열이 비어 있을 때만 보낸다(`done`보다 먼저 와도 된다).
  - 모든 요청(`startSession`·`sendTurn`·`endSession`)은 성공 이벤트나 실패 이벤트(`start_failed`·`turn_error`·`send_failed`·`end_failed`) 중 하나로 반드시 끝낸다. 시간 초과도 실패로 보낸다.
  - 큐 순번은 말이 끝난 때 정하므로, 보내던 말이 실패해 나중에 큐에 들어가도 그사이 넣은 뒷말보다 앞에 선다. 화면은 끊겼으면 보관한 말 수를, 연결돼 있으면 "이어서 한 말 N개"(답변 중이면 "답변 뒤에", 아니면 "다음 차례에" 보냄)를 보인다.
  - 이어 재생(`AudioOutput`, 웹 `web/src/platform/audioOutput.ts`)은 넣은 순서대로 하나씩 재생하고(디코드는 넣는 즉시 병렬), 답변 문장이 끝날 때마다 `sentence_played {index}`, 대기열이 비면 `playback_idle`을 보낸다. 인사말·검색 안내(`tool.notice`)·마무리 멘트는 문장 번호 없이 넣는다(`sentence_played` 없음). 소리가 없는 문장(`audio: null`)과 디코드·재생에 실패한 소리는 길이 0으로 보고 순서대로 넘어간다. `stopPlayback`은 즉시 멈추고 대기열을 비우며 이벤트를 보내지 않는다. 브라우저 자동 재생 제한 때문에 시작 버튼을 누를 때 오디오를 연다(`unlock`). 소리가 나지 않는 상황(자동 재생 제한, 오디오 중단)에서도 대기열은 멈추지 않는다(다시 켜기를 0.5초만 기다리고, 끝 알림이 오지 않으면 소리 길이 + 2초 뒤 넘어간다). 소리 없는 문장은 넣자마자 `sentence_played`가 나갈 수 있으므로, 플랫폼은 대기열에 넣은 직후 같은 동기 흐름에서 머신에 `sentence`를 보낸다(사이에 `await`을 두지 않는다).
  - 마이크 입력(`AudioInput`, 웹 `web/src/platform/audioInput.ts`)은 `micOn`→`start`, `micOff`→`stop`(트랙을 멈춰 마이크 표시가 꺼진다), `setVadMode`→`setMode`로 받는다. `speech_start`는 말소리가 `min_speech_ms` 동안 이어진 뒤에 보낸다(재생 중 짧은 소음 한 번으로 끼어들기가 되지 않게). 그보다 짧은 소리는 이벤트 없이 버린다. `stop` 뒤에는 이벤트를 보내지 않는다. 마이크 권한 거부(`mic_denied`)·장치 없음(`mic_unavailable`)·감지 모델 로드 실패(`vad_failed`)의 처리는 아래 명령 실행 항목에 있다.
  - 명령 실행(웹 `web/src/screens/voiceController.ts`): `startSession`은 `POST /api/sessions {mode: "voice"}` 뒤 인사말 소리를 대기열에 넣고 `session_started`를 보낸다. `sendTurn`은 음성 턴을 올리고 SSE를 머신 이벤트로 바꾼다(`transcript`는 사용자 말풍선, `sentence`는 소리를 넣은 뒤 `sentence`, `tool.notice`는 번호 없이 대기열에(소리가 있으면 마이크를 재생 중 임계값으로 바꿔 안내 음성을 이어 말하기로 잡지 않는다), `save_note` 성공은 `note_saved`). `cancelTurn`은 받는 중인 턴 요청 연결을 끊고(늦은 이벤트를 버린다) 끼어들기 API에 `lastPlayed`를 보낸다(기다리지 않고 실패는 무시: 연결이 끊기면 서버가 보낸 문장까지는 끊긴 답변으로 남긴다). 말풍선도 들려준 문장까지만 남긴다(대화 리듀서 `interrupt`). 인사말은 자르지 않는다. 끝내기 응답 뒤 마무리 소리(`closing_audio`)를 넣고 `session_closed`를 보낸다. 마이크를 쓸 수 없으면(`mic_denied` 등) `long_press`로 대화를 마치고(일지 정리) 정리가 끝난 뒤 이유를 보인다(대기·정리 중에 늦게 온 마이크 오류는 무시). 턴 도중 세션이 서버에서 끝났을 때(`session_ended`)의 문구도 정리가 끝난 뒤 보인다. 정리 중에는 "그만 기다리기"(= `long_press`)로 끝내기 응답을 기다리지 않고 나올 수 있다. 대화 중에는 Screen Wake Lock으로 화면을 켜 두고, Media Session의 재생/일시정지(이어폰 버튼)를 `tap`으로 받는다(재생을 Web Audio로만 해서 브라우저가 미디어 세션을 켜지 않을 수 있다. 폰(안드로이드 Chrome 브라우저)에서 음성 대화는 확인했고(S3-14), 이어폰 버튼 동작은 실제 산책 때 확인한다). 음성 모듈(vad-web·onnxruntime·mediabunny)은 첫 화면 로딩에서 빼고 화면이 열린 뒤 따로 불러오며, 다 불러오기 전에는 "음성으로 대화"를 막는다(오디오는 버튼을 누른 동작 안에서 열어야 한다). 불러오지 못하면 글로 대화하도록 안내한다. 시작 화면은 "음성으로 대화"·"글로 대화"를 고르고, 고른 방식을 기억해 `prepare`도 그 방식으로 보낸다(서버 준비분이 방식마다 다르다).
  - 음성 대화 중 글 입력(S3-21): 글은 말 한 번처럼 `speech_end`로 머신에 넣고, `sendTurn`에서 `POST /api/sessions/{id}/turns {text}`로 보낸다(서버가 음성 대화면 답변 음성도 만든다). 듣기에서만 받는다. 말하기면 `tap`(끼어들기), 쉬기면 `tap`(다시 듣기)을 먼저 보내고 듣기가 되면 보낸다. 끼어든 직후에는 `cancelTurn` 요청이 끝난 뒤 보내고, 그래도 `turn_in_progress`(서버가 이전 답변을 정리 중)면 0.5초 뒤 최대 3번 다시 보낸다. 처리 중·오프라인·정리 중이거나 큐에 말이 남아 있으면 받지 않는다(화면은 입력을 남기고 보내기만 잠근다). 인식 결과 이벤트가 없으므로 내 말풍선은 보낼 때 바로 그린다. 턴 시작 전에 실패해도 큐(녹음 전용)에 넣지 않는다. 대화가 이어지면 말풍선을 빼고 글을 입력창에 돌려주고(`turn_error`로 듣기로), 대화가 끝났으면(끝내기로 끊음·서버에서 끝남) 말풍선만 빼고 글은 버린다. 지연 측정은 하지 않는다.
  - 오프라인 큐(`LocalQueue`, 웹 `web/src/platform/localQueue.ts`)는 녹음을 대화 ID와 함께 IndexedDB에 보관한다(새로 고쳐도 남는다, IndexedDB를 못 쓰면 메모리로 대신해 새로 고치면 사라진다). 서버에 닿지 않은 실패는 턴 시작(`turn`) 전의 `network_error`·`stream_closed`이고, 그 밖의 오류는 `turn_error`다. `queueUtterance`는 녹음을 큐에 넣고, `sendQueued`는 이 대화의 가장 오래된 말을 보내 `turn`을 받으면 큐에서 지운 뒤 `queue_sent`를 보낸다. 턴이 시작되기(인식 결과가 오기) 전에 30초가 지나면 서버에 닿지 않은 것으로 본다. 큐의 말이 말소리가 없으면(`no_speech` 등) 버리고, 서버 일시 오류면 남겨 두고 `queue_send_failed`로 나중에 다시 보낸다(5번 실패하면 대답을 포기하고 기록만 남겨 뒤의 말을 막지 않는다). 끝내기로 보내던 말이 끊기면 보관해 기록만 남긴다. 서버가 말을 저장한 직후 `turn` 전에 끊기면 다시 보내 한 번 더 기록될 수 있다(최소 한 번 전달). 서버가 대화를 끝냈으면(`session_ended`) 그 말은 대답 없이 기록만 남긴다(`POST …/turns/audio/record`, 아래 2절). 대화가 끝나 대기로 돌아가면(끊긴 채 끝냄 포함) 이 대화에 남은 말과 이전 대화(새로 고치기 전)의 남은 말도 기록만 남긴다(연결이 없으면 다음 연결 때). `speakOfflineNotice`는 기기 TTS(`speechSynthesis`, ko-KR)로 `client.offline_notice`를 읽고 끝나면 `offline_notice_done`을 보낸다(없거나 6초를 넘으면 바로). 연결 복구는 브라우저 `online` 이벤트와, 끊긴 동안 30초마다 `GET /api/health`로 서버에 닿는지 확인하는 것으로 알아챈다. 보관한 녹음은 30일이 지나면 보내지 않고 지우고, 기록만 남기기에 5번 실패한 말도 지운다(기기에 녹음을 끝없이 두지 않게. 유실 0건(NFR-04)의 예외로 둔다). 대답을 포기한 말은 "기록만" 표시로 보통 전송에서 빠진다. 저장소(IndexedDB)에 넣지 못하면 그 말은 메모리에 두고, 읽기·지우기는 두 곳을 모두 본다. 화면에는 보관한 말 수를 보인다.

## 5. 클라이언트 설정값

클라이언트는 `GET /api/profile`의 `client`를 받아 쓴다. 받기 전(또는 받지 못했을 때)에는 같은 형식의 `shared/client-defaults.json`을 대체값으로 쓴다. 서버는 시작할 때 이 파일을 읽어 검증하며(서버 `app/client_config.py`), 틀리면 서버가 시작하지 않는다. 다만 `session.idle_timeout_minutes`는 서버의 무발화 종료 기준(`IDLE_TIMEOUT_S`)으로 덮어써 서버 안전망과 늘 같다(0 이하면 서버가 시작하지 않는다). 서버만 따로 배포할 때는 `shared/`를 함께 두거나 `CLIENT_DEFAULTS_PATH`로 파일 위치를 준다.

| 필드 | 기본값 | 의미 |
|---|---|---|
| `vad.speech_threshold` | 0.5 | Silero VAD 음성 확률이 이 값 이상이면 말 시작으로 본다(평상시) |
| `vad.silence_threshold` | 0.25 | 이 값 아래면 무음으로 본다. `speech_threshold`보다 작다 |
| `vad.playback_speech_threshold` | 0.8 | 캐릭터 음성 재생 중(`setVadMode playback`)의 말 시작 기준. 제니 목소리를 사용자 발화로 잘못 듣지 않게 올린다. 평상시 값 이상 |
| `vad.playback_silence_threshold` | 0.65 | 재생 중 무음 기준. 평상시 값 이상, 재생 중 말 시작 기준보다 작다 |
| `vad.end_of_speech_silence_ms` | 1800 | 무음이 이만큼 이어지면 발화 끝(`speech_end`) |
| `vad.min_speech_ms` | 300 | 이보다 짧은 소리는 발화로 보지 않고 버린다 |
| `session.idle_timeout_minutes` | 30 | 듣기·쉬기에서 이 시간 동안 말이 없으면 정리로 간다(4절). 소수일 수 있다 |
| `audio.upload` | `{codec: "opus", sample_rate_hz: 16000, channels: 1}` | 발화 업로드 형식(3절) |
| `audio.response` | `{codec: "mp3"}` | 답변 문장 오디오 형식(3절) |
| `offline_notice` | "네트워크 연결이 불안하여 메모만 해둘게요." | 오프라인 보관 때 기기 TTS로 읽는 안내 문구 |

VAD 수치는 시작값이며 실제 산책 측정에서 조정한다. 웹은 `@ricky0123/vad-web`(Silero `v5` 모델)에 `speech/silence_threshold` → `positive/negativeSpeechThreshold`, `end_of_speech_silence_ms` → `redemptionMs`, `min_speech_ms` → `minSpeechMs`로 넘기고, 재생 중(`setVadMode playback`)에는 `playback_*` 값으로 바꾼다. 감지 전 소리 300ms를 발화 앞에 붙인다(웹 상수 `PRE_SPEECH_PAD_MS`). 모델·worklet·onnxruntime wasm은 CDN이 아니라 앱이 `/vad/<vad-web 버전>-<onnxruntime 버전>/`에서 서빙한다(약 16MB, wasm이 대부분. 파일 이름에 해시가 없어 버전 폴더로 캐시를 나눈다, `web/vadAssets.ts`).

## 6. 알림음·안내 문구

`shared/sounds/`의 효과음과 `shared/client-defaults.json`의 안내 문구를 사용한다. 효과음은 `listen.mp3`(듣기 시작, 올라가는 두 음 0.24초), `saved.mp3`(노트 저장, 맑은 두 음 0.29초), `offline.mp3`(오프라인 전환, 내려가는 두 음 0.36초)로 ffmpeg 사인파로 만들었다(저작권 없음). 상태 머신의 `playSound {name}`이 이 파일 이름과 같다. 안드로이드는 같은 파일을 앱 리소스로 복사한다.

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
| 404 | `turn_not_found` | 끼어들기 대상이 이 대화의 캐릭터 답변이 아님(`POST /api/sessions/{id}/turns/{turn_id}/cancel`) |
| 500 | `persona_invalid` | 서버의 페르소나 YAML 오류(프로필 요청에서 올 수 있다. 세션 시작에서는 일반 문구로 바뀐다) |
| 401·403·409·429 등 | `unauthorized`·`forbidden`·`conflict`·`too_many_requests`, 그 밖은 HTTP 상태 이름 | 일반 HTTP 오류(`server/app/errors.py`) |
| 404 | `persona_not_found` | 없는 페르소나(`PUT /api/profile`) |
| 404 | `note_not_found` | 없는 노트(`PATCH /api/notes/{id}`) |
| 422 | `invalid_range` | 일지 목록의 날짜 범위가 틀림(`GET /api/journal`) |
| 409 | `session_not_ended` | 끝나지 않은 대화를 다시 정리하려 함(`POST /api/journal/{id}/retry`) |
| 409 | `session_active` | 진행 중인 대화를 지우려 함(`DELETE /api/journal/{id}`) |
| 502 | `llm_error` | 인사말·답변을 만들지 못함(SSE에서는 `error` 이벤트) |
| 502 | `llm_process_exited` | Claude CLI 프로세스가 끝남. 다음 요청에서 맥락을 이어 다시 띄운다 |
| 504 | `llm_timeout` | 답변 시간 초과 |
| 422 | `no_speech` | 음성 턴에서 인식 결과에 말이 없음(조용함·잡음). 사용자 메시지는 만들지 않는다 |
| 400·413 | `audio_invalid` | 업로드 오디오가 비었거나, 너무 크거나(413), 읽을 수 없음(음성 턴) |
| 503 | `voice_unavailable` | 음성 서비스를 쓸 수 없음(서버 키 없음·인증 실패·크레딧 소진·ffmpeg 없음). 다시 시도해도 풀리지 않는다 |
| 502 | `stt_failed`·`tts_failed` | 음성 인식·합성 실패(일시 오류 포함) |
| 504 | `stt_timeout`·`tts_timeout` | 음성 인식·합성 시간 초과 |

기능별 코드(예: `session_not_found`)는 해당 API를 만들 때 이 표에 추가한다.

**클라이언트 측 코드**(서버가 보내지 않고 클라이언트가 만든다, 웹 `src/api/http.ts`·`src/api/conversation.ts`): `network_error`(서버에 연결할 수 없음, 또는 JSON 본문 없는 502·503·504: 개발 프록시·터널이 서버 중단 때 주는 응답), `http_error`(오류 응답이 공통 형식이 아님), `stream_closed`(턴 스트림이 `done`·`error` 없이 끊김), `bad_event`(SSE `data`가 JSON이 아니거나, JSON이어도 객체가 아니거나 `type`이 문자열이 아님). 안드로이드도 같은 코드를 쓴다.

**요청 ID**: 클라이언트는 `X-Request-ID` 헤더(영문·숫자·`._-`, 64자 이내)를 보낼 수 있고, 없거나 형식이 맞지 않으면 서버가 새로 만든다. 서버는 모든 응답 헤더에 `X-Request-ID`를 넣는다.
