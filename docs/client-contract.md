# 클라이언트 규약 (초안)

웹 앱과 안드로이드 앱이 함께 지키는 규약이다. 설계서 4.8을 기준으로 하며, 3단계([구현 계획서](implementation-plan.md) S3-15)에서 확정한다. 확정 전까지는 각 절이 비어 있을 수 있다.

## 1. API

- 모든 서버 API는 `/api` 아래에 둔다(예: `/api/health`, `/api/sessions`).
- 타입은 FastAPI OpenAPI 스키마에서 생성한다: 웹은 openapi-typescript(`npm run gen:api` → `web/src/api/schema.d.ts`, 서버 `python -m app.openapi`), 안드로이드는 openapi-generator.
- 턴 SSE는 POST 응답이라 `EventSource` 대신 스트림을 직접 읽는다. 파서는 `web/src/core/sse.ts`(줄 끝은 `\r\n`·`\r`·`\n`만, 빈 줄로 끝나지 않은 마지막 메시지는 버림).

## 2. SSE 이벤트

턴 요청(텍스트 `POST /api/sessions/{id}/turns`, 음성 `POST /api/sessions/{id}/turns/audio`)의 응답은 `text/event-stream`이다. 메시지마다 `event: <type>` 줄과 `data: <한 줄 JSON>` 줄, 빈 줄로 이뤄지고 JSON에도 `type`이 들어 있다. 스키마는 OpenAPI components(`StreamEvent`, 서버 `app/api/events.py`)가 기준이다. 1단계 초안이며 3단계(S3-15)에서 확정한다.

| type | 필드 | 의미 |
|---|---|---|
| `turn` | `turn_id` | 스트림의 첫 이벤트. 이번 답변(assistant 턴)의 ID. 끼어들기 `POST /api/sessions/{id}/turns/{turn_id}/cancel`(3단계)에 쓴다 |
| `sentence` | `index`, `text`, `audio` | 답변 한 문장. `index`는 턴 안에서 0부터. `audio`는 그 문장의 MP3(base64)로, 음성 세션에서만 오고 텍스트 세션이나 합성 실패면 `null`이다(클라이언트는 글자를 보이거나 기기 TTS로 대신한다) |
| `tool` | `phase`(`start`/`call`/`end`), `tool_use_id`, `name`, `input`, `summary`, `is_error`, `notice` | 도구 사용. `start`에는 이름만 온다(검색 중 표시용). `input`은 `call`에서만, `summary`·`is_error`는 `end`에서만 의미가 있고 나머지 단계에서는 `null`/`false`. `notice`(`{text, audio}`)는 음성 세션에서 캐릭터가 아무 말 없이 `web_search`·`web_fetch`를 시작할 때만 `start`에 실리는 안내 음성이다(턴마다 한 번). 답변 문장이 아니라 `index`·`done.text`에 들어가지 않는다. 클라이언트는 문장처럼 재생 대기열에 넣는다 |
| `done` | `turn_id`, `text`, `interrupted`, `session_status`(`active`/`paused`/`ended`) | 턴 끝. `turn_id`는 `turn` 이벤트와 같다. 전체 답변과 세션 상태 |
| `error` | `code`, `message` | 스트림 도중 오류. 코드는 7절 공통 오류와 같다. 이 뒤에는 이벤트가 오지 않는다 |
| `transcript` | `text` | 음성 턴에서만 `turn` 바로 앞에 오는 첫 이벤트. 인식한 글(사용자 메시지로 저장된 글)이다 |

**도구 이름(`name`)**: `save_note`, `search_notes`, `summarize_session`, `pause_session`, `end_session`, `web_search`, `web_fetch`. 결과 요약(`summary`)은 `web_search`면 `{query, links: [{title, url}]}`, `web_fetch`면 `{code, bytes}`, 앱 도구면 `{result}`다. 결과 형식을 알 수 없으면 `{}`가 온다.

**세션 API**: 대화 화면이 "시작 전"·"끝남" 상태가 되면 `POST /api/sessions/prepare` `{mode}` → 204를 보낸다. 서버가 다음 대화의 CLI를 미리 띄워 인사말 대기를 약 1.4초 줄인다. 대화 탭이 보일 때만 보내고, 화면이 열려 있는 동안 4분마다 다시 보낸다. 결과를 기다리지 않고 실패해도 무시한다. 같은 조건이면 여러 번 불러도 하나만 준비된다. 준비된 지 5분이 지나면 다음 요청 때 새 시각으로 다시 띄우고, 요청이 끊겨 쓰지 않으면 닫힌다. 준비 뒤 프롬프트(호칭·페르소나 등)나 날짜·오전/오후가 바뀌면 시작할 때 새로 띄운다. `POST /api/sessions` `{mode: "text"|"voice"}` → 201 `{session, greeting: {turn_id, text, audio}, persona: {id, name}}`. `greeting.audio`는 인사말 MP3(base64)로 음성 세션에서만 오고, 합성에 실패하면 `null`이어도 세션은 시작된다. 화면의 캐릭터 이름은 `persona.name`을 쓰고 코드에 넣지 않는다(NFR-08). `POST /api/sessions/{id}/turns` `{text}`(1~4000자) → 위 SSE. **음성 턴**: `POST /api/sessions/{id}/turns/audio`, 본문은 말 한 번의 오디오 바이트 그대로(multipart 아님), `Content-Type`은 녹음 형식(웹 `audio/webm`, 안드로이드 `audio/ogg`. 3절) → 위 SSE(`transcript` → `turn` → …). 서버는 SSE를 열기 전에 인식하므로 오디오·인식 오류와 말 없음은 JSON 오류다: `audio_invalid`(400, 너무 크면 413), `no_speech`(422, 인식 결과에 말이 없음), `stt_failed`·`stt_timeout`·`voice_unavailable`. 이 오류들은 사용자 메시지를 만들지 않는다(상태 머신에는 `turn_error {turnId: null}`). 인식 뒤 스트림을 열 때 다른 턴이 진행 중이거나 세션이 끝났으면 `transcript` 없이 `error`(`turn_in_progress`·`session_ended`)가 첫 이벤트로 온다(인식한 글은 저장되지 않는다). 텍스트 세션에서도 음성 턴을 보낼 수 있고 그때 문장 `audio`는 `null`이다. `POST /api/sessions/{id}/end` → `{session, closing, closing_audio, saved: {idea, todo, memo}, journal_status}`(여러 번 불러도 같다. `closing_audio`는 마무리 멘트 MP3(base64)로 음성 세션에서만, 실패하면 `null`). 서버는 세션을 끝내고 일지 정리(추출)를 띄운 뒤 최대 45초 기다려, 이 대화에서 저장한 노트 개수로 만든 마무리 멘트(`closing`, 캐릭터 말풍선으로 보인다)를 준다. `journal_status`가 `pending`이면 정리가 아직 끝나지 않은 것이다(개수가 나중에 늘 수 있다). 기다리는 동안 클라이언트는 정리 중 안내를 보인다. 끝내기 도구로 턴이 끝나 대화가 끝났을 때(`done`의 `session_status: ended`, 또는 `turn` 뒤 `session_ended` 오류)도 클라이언트는 이어서 이 API를 불러 마무리 멘트를 받는다. 쉬기(`paused`) 상태에서 턴을 보내면 다시 `active`가 된다. 마지막 발화 뒤 30분 동안 말이 없으면(쉬는 중 포함) 서버가 세션을 끝내고 일지를 정리한다(클라이언트 타이머의 안전망). 그 뒤 턴 요청은 `session_ended`가 된다. 서버는 사용자 메시지를 받자마자, 답변은 `sentence`를 보내기 전에 문장마다 저장한다. 그래서 턴 도중 연결이 끊기거나 오류가 나거나 서버가 죽어도 사용자 메시지와 클라이언트가 받은 문장은 모두 기록되고(보내려던 문장이 하나 더 남을 수 있다), 그 답변은 끊긴 답변(`interrupted`)으로 남는다. 첫 문장 전에 끊기면 사용자 메시지만 남는다. 쉬기·끝내기 도구가 불린 뒤 턴이 오류나 연결 끊김으로 끝나도 그 요청은 반영된다. 턴 요청이 `session_ended`·`session_not_found`로 실패하면(시작 전 JSON 오류든 SSE `error` 이벤트든) 클라이언트는 대화를 끝난 상태로 바꾼다. 끝내기 요청 뒤 턴이 오류로 끝나거나, 턴 도중 다른 곳(끝내기 API·무발화 감시)이 세션을 끝내면 서버는 `error` 이벤트를 `session_ended`("대화를 마쳤어요.")로 보낸다. 무발화로 끝난 세션의 `ended_at`은 마지막 발화 시각이다. `turn` 이벤트 전에 온 `error`는 서버가 사용자 메시지를 받지 못한 것이므로 클라이언트는 그 메시지를 목록에서 빼고 입력창으로 되돌린다.

**일지 API**: `GET /api/journal?from=YYYY-MM-DD&to=YYYY-MM-DD` → 일지 목록(최신순). 날짜는 서버 시간대의 현지 날짜이고 둘 다 포함하며, 생략하면 최근 30일이다(한 번에 366일까지, 2000-01-01~9998-12-31 밖이거나 범위가 틀리면 422 `invalid_range`). 사용자가 한마디도 하지 않은 대화는 빠진다. 항목은 `{id, date, started_at, ended_at, status, title, summary: [줄], tags, journal_status, counts: {idea, todo, memo}}`이고, 클라이언트는 `date`로 날짜별로 묶는다(시간대 계산을 하지 않는다). `journal_status`는 `pending`(정리 중)·`done`·`failed`(정리 실패)·`null`(정리 기록 없음: 아직 끝나지 않은 대화, 또는 일지 정리가 생기기 전에 끝난 대화)이다. `GET /api/journal/{id}` → `{session: 위 항목, persona_name, notes: [{id, kind, content, starred, done, created_at}], turns: [{id, seq, role, text, interrupted, created_at}]}`(없으면 404 `session_not_found`. 목록에서 빠지는 대화도 ID로는 조회된다). `turns`는 전문이고 `interrupted`는 끝까지 말하지 못한 답변이다. 전문의 캐릭터 화자 이름은 `persona_name`(현재 프로필의 페르소나 이름)을 쓴다(코드에 두지 않는다). `POST /api/journal/{id}/retry` → 202 일지 항목: 정리에 실패했거나(`failed`) 정리 기록이 없는(`null`) 끝난 대화를 다시 정리한다. 정리 중·완료면 아무것도 하지 않고 그대로 준다(끝나지 않은 대화는 409 `session_not_ended`). 클라이언트는 `journal_status`가 `pending`인 동안 목록·상세를 3초마다(최대 약 2분) 다시 불러와 정리가 끝난 것을 보여 준다. `PATCH /api/notes/{id}` `{starred?, done?, content?}` → 바뀐 노트. 아이디어의 `done`은 다 했거나 접은 아이디어를 닫는 데 쓴다(다음 대화의 기억에서 빠진다). 보낸 필드만 바꾸며 `content`는 앞뒤 공백을 빼고 1~500자이며 여러 줄도 된다(없으면 404 `note_not_found`).

**프로필 API**: `GET /api/profile` → `{nickname, interests, persona_id, voice, keep_audio, client}`(처음 조회하면 기본값으로 만든다). `client`는 5절의 클라이언트 설정값이고 읽기 전용이다(`PUT`에 보내면 422). `PUT /api/profile`은 보낸 필드만 바꾼다. `nickname`은 앞뒤 공백을 빼고 1~20자 한 줄이고, `null`이면 기본 호칭으로 돌아간다. `interests`는 최대 10개, 각 1~30자이며 중복은 제거한다. 없는 `persona_id`는 404 `persona_not_found`다. 프로필을 바꾸면 다음 세션부터 반영된다. 진행 중인 세션의 프롬프트는 시작 때 고정돼(서버 `conversation_session.system_prompt`) CLI를 다시 띄우거나 서버를 재시작해도 그대로다.

**순서**: 한 턴은 `turn`으로 시작해(음성 턴은 그 앞에 `transcript`) `sentence`·`tool`이 섞여 오다가 `done` 또는 `error` 하나로 끝난다. 모든 필드는 항상 실려 온다(스키마상 required). `summary`의 도구별 타입은 3단계 확정 때 스키마로 고정한다. 시작 전 오류(세션 없음, 진행 중인 턴 등)는 SSE가 아니라 7절의 JSON 오류 응답으로 온다.

## 3. 오디오 형식

- 업로드: 말 한 번을 하나의 오디오로 보낸다. 권장은 16kHz 모노 Opus(웹 MediaRecorder `audio/webm;codecs=opus`, 안드로이드 `audio/ogg`). 서버는 webm·wav·mp3·m4a(mp4)는 그대로 인식에 넘기고, 그 밖의 형식(ogg 등)은 16kHz 모노 webm/opus로 바꾼다. 최대 10MB, 변환은 앞 120초까지.
- 응답: 문장별 MP3(base64, `sentence.audio`), 인사말·마무리 멘트도 MP3(base64)다.

## 4. 세션 상태 머신

음성 대화는 아래 상태를 오가는 하나의 루프다(설계서 4.1). 상태 머신은 이벤트를 받아 다음 상태와 **명령**을 돌려주는 순수 함수이고(웹 `web/src/core/sessionMachine.ts`), 마이크·재생·서버 호출·타이머는 화면·플랫폼 계층이 명령을 받아 실행한다. 전이 표 `shared/fixtures/transitions.json`(S3-09)을 웹과 안드로이드 테스트가 함께 읽는다. 3단계 S3-15에서 확정한다.

- **상태**(코드 이름): 대기 `idle`, 듣기 `listening`, 처리 중 `processing`, 말하기 `speaking`, 쉬기 `paused`, 오프라인 보관 `offline`, 정리 `closing`.
- **이벤트**: 버튼 `tap`·`long_press`, 시작 `session_started`(인사말 재생 시작)·`start_failed`, 발화 감지 `speech_start`·`speech_end`, 턴 스트림 `turn`·`sentence`·`turn_done`·`turn_error`·`note_saved`, 재생 `sentence_played`·`playback_idle`, 오프라인 `send_failed`·`offline_notice_done`·`online`·`queue_flushed`, 그 밖 `idle_timeout`·`session_closed`·`end_failed`.
- **명령**: `startSession`, `sendTurn`, `cancelTurn`(턴 ID와 마지막으로 다 들려준 문장 번호), `endSession`, `micOn`·`micOff`, `setVadMode`(재생 중 `playback`으로 임계값 상향), `stopPlayback`, `queueUtterance`, `speakOfflineNotice`, `flushQueue`, `playSound`(`listen`·`saved`·`offline`), `notifyError`, `startIdleTimer`·`clearIdleTimer`.
- **규칙 요약**
  - 한 번 누르기: 대기에서는 시작, 말하기·처리 중에는 끼어들기(취소 뒤 듣기), 쉬기에서는 다시 듣기.
  - 길게 누르기: 대기 외 어디서나 종료(정리 중이면 끝내기 응답을 기다리지 않고 대기로).
  - 답변 문장을 다 들려주고 턴이 끝나면 `done`의 `session_status`에 따라 듣기·쉬기·정리로 간다.
  - 듣기·쉬기에서 30분(`idle_timeout_minutes`) 동안 말이 없으면 정리로 간다. 서버 안전망과 같은 기준이다.
  - 큐에 발화가 남아 있으면 새 발화도 큐 뒤에 넣어 순서를 지킨다.
  - 표에 없는 조합과 모르는 이벤트는 무시한다.
- **플랫폼이 지킬 것**
  - 인사말은 SSE가 아니라 시작 응답으로 온다. 재생을 시작하며 `session_started {turnId}`(인사말 턴 ID)를 보내고, 재생할 소리가 없으면 바로 `playback_idle`을 보낸다.
  - `sentence`·`turn_done`에는 턴 ID를 싣는다. 머신은 지금 턴과 다른 ID의 이벤트(취소한 턴의 늦은 이벤트)를 무시한다. `turn_error`는 턴 시작 전 오류면 `turnId: null`이다.
  - `sentence` 이벤트는 그 문장 소리를 재생 대기열에 넣은 뒤에 머신에 보낸다. `playback_idle`은 보내는 순간 대기열이 비어 있을 때만 보낸다(`done`보다 먼저 와도 된다).
  - 모든 요청(`startSession`·`sendTurn`·`endSession`)은 성공 이벤트나 실패 이벤트(`start_failed`·`turn_error`·`send_failed`·`end_failed`) 중 하나로 반드시 끝낸다. 시간 초과도 실패로 보낸다.
  - 처리 중에 들어온 발화(`speech_end`)는 버린다.
  - 큐 비우기가 끝나면 남은 발화 수를 `queue_flushed {remaining}`로 알린다. 큐 항목이 어느 세션에 속하는지와 끝내기 전에 큐를 비울지는 S3-12(LocalQueue)에서 정한다.

## 5. 클라이언트 설정값

클라이언트는 `GET /api/profile`의 `client`를 받아 쓴다. 받기 전(또는 받지 못했을 때)에는 같은 형식의 `shared/client-defaults.json`을 대체값으로 쓴다. 서버는 시작할 때 이 파일을 읽어 검증하며(서버 `app/client_config.py`), 틀리면 서버가 시작하지 않는다. 다만 `session.idle_timeout_minutes`는 서버의 무발화 종료 기준(`IDLE_TIMEOUT_S`)으로 덮어써 서버 안전망과 늘 같다(0 이하면 서버가 시작하지 않는다). 서버만 따로 배포할 때는 `shared/`를 함께 두거나 `CLIENT_DEFAULTS_PATH`로 파일 위치를 준다.

| 필드 | 기본값 | 의미 |
|---|---|---|
| `vad.speech_threshold` | 0.5 | Silero VAD 음성 확률이 이 값 이상이면 말 시작으로 본다(평상시) |
| `vad.silence_threshold` | 0.35 | 이 값 아래면 무음으로 본다. `speech_threshold`보다 작다 |
| `vad.playback_speech_threshold` | 0.8 | 캐릭터 음성 재생 중(`setVadMode playback`)의 말 시작 기준. 제니 목소리를 사용자 발화로 잘못 듣지 않게 올린다. 평상시 값 이상 |
| `vad.playback_silence_threshold` | 0.65 | 재생 중 무음 기준. 평상시 값 이상, 재생 중 말 시작 기준보다 작다 |
| `vad.end_of_speech_silence_ms` | 1200 | 무음이 이만큼 이어지면 발화 끝(`speech_end`) |
| `vad.min_speech_ms` | 300 | 이보다 짧은 소리는 발화로 보지 않고 버린다 |
| `session.idle_timeout_minutes` | 30 | 듣기·쉬기에서 이 시간 동안 말이 없으면 정리로 간다(4절). 소수일 수 있다 |
| `audio.upload` | `{codec: "opus", sample_rate_hz: 16000, channels: 1}` | 발화 업로드 형식(3절) |
| `audio.response` | `{codec: "mp3"}` | 답변 문장 오디오 형식(3절) |
| `offline_notice` | "지금은 산이 깊어서 메모만 해둘게요!" | 오프라인 보관 때 기기 TTS로 읽는 안내 문구 |

VAD 수치는 시작값이며 S3-10과 실제 산책 측정에서 조정한다.

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
| 404 | `note_not_found` | 없는 노트(`PATCH /api/notes/{id}`) |
| 422 | `invalid_range` | 일지 목록의 날짜 범위가 틀림(`GET /api/journal`) |
| 409 | `session_not_ended` | 끝나지 않은 대화를 다시 정리하려 함(`POST /api/journal/{id}/retry`) |
| 502 | `llm_error` | 인사말·답변을 만들지 못함(SSE에서는 `error` 이벤트) |
| 502 | `llm_process_exited` | Claude CLI 프로세스가 끝남. 다음 요청에서 맥락을 이어 다시 띄운다 |
| 504 | `llm_timeout` | 답변 시간 초과 |
| 422 | `no_speech` | 음성 턴에서 인식 결과에 말이 없음(조용함·잡음). 사용자 메시지는 만들지 않는다 |
| 400·413 | `audio_invalid` | 업로드 오디오가 비었거나, 너무 크거나(413), 읽을 수 없음(음성 턴) |
| 503 | `voice_unavailable` | 음성 서비스를 쓸 수 없음(서버 키 없음·인증 실패·크레딧 소진·ffmpeg 없음). 다시 시도해도 풀리지 않는다 |
| 502 | `stt_failed`·`tts_failed` | 음성 인식·합성 실패(일시 오류 포함) |
| 504 | `stt_timeout`·`tts_timeout` | 음성 인식·합성 시간 초과 |

기능별 코드(예: `session_not_found`)는 해당 API를 만들 때 이 표에 추가한다.

**클라이언트 측 코드**(서버가 보내지 않고 클라이언트가 만든다, 웹 `src/api/conversation.ts`): `network_error`(서버에 연결할 수 없음, 또는 JSON 본문 없는 502·503·504: 개발 프록시·터널이 서버 중단 때 주는 응답), `http_error`(오류 응답이 공통 형식이 아님), `stream_closed`(턴 스트림이 `done`·`error` 없이 끊김), `bad_event`(SSE `data`가 JSON이 아님). 안드로이드도 같은 코드를 쓴다.

**요청 ID**: 클라이언트는 `X-Request-ID` 헤더(영문·숫자·`._-`, 64자 이내)를 보낼 수 있고, 없거나 형식이 맞지 않으면 서버가 새로 만든다. 서버는 모든 응답 헤더에 `X-Request-ID`를 넣는다.
