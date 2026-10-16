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
| `turn` | `turn_id` | 스트림의 첫 이벤트. 이번 답변(assistant 턴)의 ID. 끼어들기 `POST /api/sessions/{id}/turns/{turn_id}/cancel`에 쓴다(아래 끼어들기 API) |
| `sentence` | `index`, `text`, `audio` | 답변 한 문장. `index`는 턴 안에서 0부터. `audio`는 그 문장의 MP3(base64)로, 음성 세션에서만 오고 텍스트 세션이나 합성 실패면 `null`이다(클라이언트는 글자를 보이거나 기기 TTS로 대신한다) |
| `tool` | `phase`(`start`/`call`/`end`), `tool_use_id`, `name`, `input`, `summary`, `is_error`, `notice` | 도구 사용. `start`에는 이름만 온다(검색 중 표시용). `input`은 `call`에서만, `summary`·`is_error`는 `end`에서만 의미가 있고 나머지 단계에서는 `null`/`false`. `notice`(`{text, audio}`)는 음성 세션에서 캐릭터가 아무 말 없이 `web_search`·`web_fetch`를 시작할 때만 `start`에 실리는 안내 음성이다(턴마다 한 번). 답변 문장이 아니라 `index`·`done.text`에 들어가지 않는다. 클라이언트는 문장처럼 재생 대기열에 넣는다 |
| `done` | `turn_id`, `text`, `interrupted`, `session_status`(`active`/`paused`/`ended`) | 턴 끝. `turn_id`는 `turn` 이벤트와 같다. 전체 답변과 세션 상태 |
| `error` | `code`, `message` | 스트림 도중 오류. 코드는 7절 공통 오류와 같다. 이 뒤에는 이벤트가 오지 않는다 |
| `transcript` | `text` | 음성 턴에서만 `turn` 바로 앞에 오는 첫 이벤트. 인식한 글(사용자 메시지로 저장된 글)이다 |

**도구 이름(`name`)**: `save_note`, `search_notes`, `summarize_session`, `pause_session`, `end_session`, `web_search`, `web_fetch`. 결과 요약(`summary`)은 `web_search`면 `{query, links: [{title, url}]}`, `web_fetch`면 `{code, bytes}`, 앱 도구면 `{result}`다. 결과 형식을 알 수 없으면 `{}`가 온다.

**세션 API**: 대화 화면이 "시작 전"·"끝남" 상태가 되면 `POST /api/sessions/prepare` `{mode}` → 204를 보낸다. 서버가 다음 대화의 CLI를 미리 띄워 인사말 대기를 약 1.4초 줄인다. 대화 탭이 보일 때만 보내고, 화면이 열려 있는 동안 4분마다 다시 보낸다. 결과를 기다리지 않고 실패해도 무시한다. 같은 조건이면 여러 번 불러도 하나만 준비된다. 준비된 지 5분이 지나면 다음 요청 때 새 시각으로 다시 띄우고, 요청이 끊겨 쓰지 않으면 닫힌다. 준비 뒤 프롬프트(호칭·페르소나 등)나 날짜·오전/오후가 바뀌면 시작할 때 새로 띄운다. `POST /api/sessions` `{mode: "text"|"voice"}` → 201 `{session, greeting: {turn_id, text, audio}, persona: {id, name}}`. `greeting.audio`는 인사말 MP3(base64)로 음성 세션에서만 오고, 합성에 실패하면 `null`이어도 세션은 시작된다. 화면의 캐릭터 이름은 `persona.name`을 쓰고 코드에 넣지 않는다(NFR-08). `POST /api/sessions/{id}/turns` `{text}`(1~4000자) → 위 SSE. **음성 턴**: `POST /api/sessions/{id}/turns/audio`, 본문은 말 한 번의 오디오 바이트 그대로(multipart 아님), `Content-Type`은 녹음 형식(웹 `audio/webm`, 안드로이드 `audio/ogg`. 3절) → 위 SSE(`transcript` → `turn` → …). 서버는 SSE를 열기 전에 인식하므로 오디오·인식 오류와 말 없음은 JSON 오류다: `audio_invalid`(400, 너무 크면 413), `no_speech`(422, 인식 결과에 말이 없음), `stt_failed`·`stt_timeout`·`voice_unavailable`. 이 오류들은 사용자 메시지를 만들지 않는다(상태 머신에는 `turn_error {turnId: null}`). 인식 뒤 스트림을 열 때 다른 턴이 진행 중이거나 세션이 끝났으면 `transcript` 없이 `error`(`turn_in_progress`·`session_ended`)가 첫 이벤트로 온다(인식한 글은 저장되지 않는다). 텍스트 세션에서도 음성 턴을 보낼 수 있고 그때 문장 `audio`는 `null`이다. `POST /api/sessions/{id}/end` → `{session, closing, closing_audio, saved: {idea, todo, memo}, journal_status}`(여러 번 불러도 같다. `closing_audio`는 마무리 멘트 MP3(base64)로 음성 세션에서만, 실패하면 `null`). 서버는 세션을 끝내고 일지 정리(추출)를 띄운 뒤 최대 45초 기다려, 이 대화에서 저장한 노트 개수로 만든 마무리 멘트(`closing`, 캐릭터 말풍선으로 보인다)를 준다. `journal_status`가 `pending`이면 정리가 아직 끝나지 않은 것이다(개수가 나중에 늘 수 있다). 기다리는 동안 클라이언트는 정리 중 안내를 보인다. 끝내기 도구로 턴이 끝나 대화가 끝났을 때(`done`의 `session_status: ended`, 또는 `turn` 뒤 `session_ended` 오류)도 클라이언트는 이어서 이 API를 불러 마무리 멘트를 받는다. 쉬기(`paused`) 상태에서 턴을 보내면 다시 `active`가 된다. 마지막 발화 뒤 30분 동안 말이 없으면(쉬는 중 포함) 서버가 세션을 끝내고 일지를 정리한다(클라이언트 타이머의 안전망). 그 뒤 턴 요청은 `session_ended`가 된다. 서버는 사용자 메시지를 받자마자, 답변은 `sentence`를 보내기 전에 문장마다 저장한다. 그래서 턴 도중 연결이 끊기거나 오류가 나거나 서버가 죽어도 사용자 메시지와 클라이언트가 받은 문장은 모두 기록되고(보내려던 문장이 하나 더 남을 수 있다), 그 답변은 끊긴 답변(`interrupted`)으로 남는다. 첫 문장 전에 끊기면 사용자 메시지만 남는다. 쉬기·끝내기 도구가 불린 뒤 턴이 오류나 연결 끊김으로 끝나도 그 요청은 반영된다. 턴 요청이 `session_ended`·`session_not_found`로 실패하면(시작 전 JSON 오류든 SSE `error` 이벤트든) 클라이언트는 대화를 끝난 상태로 바꾼다. 끝내기 요청 뒤 턴이 오류로 끝나거나, 턴 도중 다른 곳(끝내기 API·무발화 감시)이 세션을 끝내면 서버는 `error` 이벤트를 `session_ended`("대화를 마쳤어요.")로 보낸다. 무발화로 끝난 세션의 `ended_at`은 마지막 발화 시각이다. `turn` 이벤트 전에 온 `error`는 서버가 사용자 메시지를 받지 못한 것이므로 클라이언트는 그 메시지를 목록에서 빼고 입력창으로 되돌린다.

**끼어들기 API**: `POST /api/sessions/{id}/turns/{turn_id}/cancel` `{last_played}` → 204. `last_played`는 끝까지 들려준 마지막 문장 번호(`sentence.index`)이고 하나도 못 들려줬으면 -1이다. 서버는 그 턴이 진행 중이면 CLI를 인터럽트하고(남은 합성은 버린다) 턴이 끝나기를 최대 10초 기다린 뒤, 답변 기록을 `last_played`번 문장까지로 자르고 `interrupted`로 표시한다. 끝난 턴(다 받은 뒤 재생 중 끊기)도 같게 자른다. 다 들었으면(마지막 문장 번호 이상) 바꾸지 않는다. 여러 번 불러도 같다. 인사말(seq 0)은 문장 번호 없이 재생되므로 자르지 않는다. 자른 경우 다음 턴에 CLI에만 "직전 답변을 어디까지 들었는지" 안내를 붙인다(기록에는 남지 않는다). 없는 세션은 404 `session_not_found`, 이 대화의 캐릭터 답변이 아니면 404 `turn_not_found`다. 첫 문장 전에 연결이 끊겨 답변 기록이 아직 없는 턴도 `turn_not_found`일 수 있으며 클라이언트는 이 결과를 무시한다. 클라이언트는 cancel과 함께 턴 스트림도 끊는다(계속 읽으면 `done.text`는 자르기 전 전체 답변이다). 자르기와 다음 턴 안내는 턴 락 안에서 하므로 그 짧은 동안 새 턴은 `turn_in_progress`가 될 수 있다. 진행 중인 턴이 10초 안에 멈추지 않으면 자르지 않는다.

**기록만 남기기(S3-12)**: `POST /api/sessions/{id}/turns/audio/record`, 본문은 음성 턴과 같은 오디오 바이트 → 201 `{text}`. 인식한 말을 사용자 턴으로만 저장하고 캐릭터는 대답하지 않는다. 대답할 수 없는 보관한 말(서버가 대화를 끝냄, 새로 고쳐 대화가 사라짐)의 유실을 막는 데 쓴다. 끝난 대화도 받으며 그때는 일지를 다시 정리한다(새 말에서 나온 노트만 더해진다). 진행 중인 턴이 있으면 409 `turn_in_progress`, 말이 없으면 422 `no_speech`, 없는 세션은 404 `session_not_found`.

**지연 측정(S3-07, NFR-01)**: 서버는 음성 턴마다 요청 처리를 시작한 때를 기준으로 단계 시간(ms)을 남긴다: `upload_ms`(세션 확인과 본문 다 받기까지), `stt_ms`(형식 변환과 인식), `first_token_ms`(CLI 첫 글자), `first_sentence_ms`(첫 문장을 소리와 함께 보냄), `done_ms`(턴 끝), `audio_bytes`. 클라이언트는 말이 실제로 끝난 때(VAD가 끝을 알아챈 때에서 무음 대기 `end_of_speech_silence_ms`를 뺀 시각)부터 요청을 시작한 때까지(`speech_to_request_ms`), 요청 시작부터 그 턴의 첫 소리가 재생되기 시작한 때까지(`request_to_playback_ms`, 검색 안내 음성 포함)를 재서 `POST /api/sessions/{id}/turns/{turn_id}/latency` `{speech_to_request_ms, request_to_playback_ms, first_sound_notice}`(0~600000, `first_sound_notice`는 첫 소리가 검색 안내 음성이었는지) → 204로 한 번 보낸다(기다리지 않고 실패는 무시, 끊은 턴·소리 없이 끝난 턴은 보내지 않음, 마무리 멘트 소리는 재지 않음, 다시 보내면 덮어씀, 측정 행이 없으면 404 `turn_not_found`). `GET /api/latency?limit=100`(1~500) → `{turns: [... , first_sound_notice, total_ms], summary: {count, total_ms: {median, p90}, total_ms_reply: {median, p90}, stages: {단계: 중앙값}}}`(최근 음성 턴부터). `total_ms`는 두 보고값의 합(말 끝 → 캐릭터 첫 소리)이고, `total_ms_reply`는 첫 소리가 답변 문장인 턴만의 값이다(검색 턴은 안내 음성이 답변 지연을 가린다).

**일지 API**: `GET /api/journal?from=YYYY-MM-DD&to=YYYY-MM-DD` → 일지 목록(최신순). 날짜는 서버 시간대의 현지 날짜이고 둘 다 포함하며, 생략하면 최근 30일이다(한 번에 366일까지, 2000-01-01~9998-12-31 밖이거나 범위가 틀리면 422 `invalid_range`). 사용자가 한마디도 하지 않은 대화는 빠진다. 항목은 `{id, date, started_at, ended_at, status, title, summary: [줄], tags, journal_status, counts: {idea, todo, memo}}`이고, 클라이언트는 `date`로 날짜별로 묶는다(시간대 계산을 하지 않는다). `journal_status`는 `pending`(정리 중)·`done`·`failed`(정리 실패)·`null`(정리 기록 없음: 아직 끝나지 않은 대화, 또는 일지 정리가 생기기 전에 끝난 대화)이다. `GET /api/journal/{id}` → `{session: 위 항목, persona_name, notes: [{id, kind, content, starred, done, created_at}], turns: [{id, seq, role, text, interrupted, created_at}]}`(없으면 404 `session_not_found`. 목록에서 빠지는 대화도 ID로는 조회된다). `turns`는 전문이고 `interrupted`는 끝까지 말하지 못한 답변이다. 전문의 캐릭터 화자 이름은 `persona_name`(현재 프로필의 페르소나 이름)을 쓴다(코드에 두지 않는다). `POST /api/journal/{id}/retry` → 202 일지 항목: 정리에 실패했거나(`failed`) 정리 기록이 없는(`null`) 끝난 대화를 다시 정리한다. 정리 중·완료면 아무것도 하지 않고 그대로 준다(끝나지 않은 대화는 409 `session_not_ended`). 클라이언트는 `journal_status`가 `pending`인 동안 목록·상세를 3초마다(최대 약 2분) 다시 불러와 정리가 끝난 것을 보여 준다. `PATCH /api/notes/{id}` `{starred?, done?, content?}` → 바뀐 노트. 아이디어의 `done`은 다 했거나 접은 아이디어를 닫는 데 쓴다(다음 대화의 기억에서 빠진다). 보낸 필드만 바꾸며 `content`는 앞뒤 공백을 빼고 1~500자이며 여러 줄도 된다(없으면 404 `note_not_found`).

**프로필 API**: `GET /api/profile` → `{nickname, interests, persona_id, voice, keep_audio, client}`(처음 조회하면 기본값으로 만든다). `client`는 5절의 클라이언트 설정값이고 읽기 전용이다(`PUT`에 보내면 422). `PUT /api/profile`은 보낸 필드만 바꾼다. `nickname`은 앞뒤 공백을 빼고 1~20자 한 줄이고, `null`이면 기본 호칭으로 돌아간다. `interests`는 최대 10개, 각 1~30자이며 중복은 제거한다. 없는 `persona_id`는 404 `persona_not_found`다. `keep_audio`(기본 `false`)를 켜면 이후 음성 턴의 녹음(인식에 넘긴 파일: 인식이 바로 받는 형식 webm·wav·mp3·m4a는 올린 그대로, 그 밖은 서버가 바꾼 webm/opus)을 서버가 사용자 턴에 붙여 보관하고 30일(`AUDIO_RETENTION_DAYS`)이 지나면 지운다. 끄면 이후 녹음은 저장하지 않고, 이미 저장한 녹음은 같은 기간 뒤 지운다. 녹음은 본인만 읽을 수 있는 권한으로 저장한다. 저장에 실패해도 턴은 그대로 진행한다(경로를 남기지 못하면 파일도 지운다). 설정 화면은 5단계(S5-01)에서 만든다. 프로필을 바꾸면 다음 세션부터 반영된다. 진행 중인 세션의 프롬프트는 시작 때 고정돼(서버 `conversation_session.system_prompt`) CLI를 다시 띄우거나 서버를 재시작해도 그대로다.

**순서**: 한 턴은 `turn`으로 시작해(음성 턴은 그 앞에 `transcript`) `sentence`·`tool`이 섞여 오다가 `done` 또는 `error` 하나로 끝난다. 모든 필드는 항상 실려 온다(스키마상 required). `summary`의 도구별 타입은 3단계 확정 때 스키마로 고정한다. 시작 전 오류(세션 없음, 진행 중인 턴 등)는 SSE가 아니라 7절의 JSON 오류 응답으로 온다.

## 3. 오디오 형식

- 업로드: 말 한 번을 하나의 오디오로 보낸다. 권장은 16kHz 모노 Opus(웹 `audio/webm;codecs=opus`, 안드로이드 `audio/ogg`). 웹은 VAD가 준 16kHz 발화 오디오를 WebCodecs `AudioEncoder`로 24kbps Opus로 인코딩해 webm에 담고(mediabunny, `web/src/platform/encodeAudio.ts`), 브라우저가 Opus 인코딩을 못 하면 16bit PCM WAV(`audio/wav`, 약 10배 큼)로 보낸다. 서버는 webm·wav·mp3·m4a(mp4)는 그대로 인식에 넘기고, 그 밖의 형식(ogg 등)은 16kHz 모노 webm/opus로 바꾼다. 최대 10MB, 변환은 앞 120초까지.
- 응답: 문장별 MP3(base64, `sentence.audio`), 인사말·마무리 멘트도 MP3(base64)다.

## 4. 세션 상태 머신

음성 대화는 아래 상태를 오가는 하나의 루프다(설계서 4.1). 상태 머신은 이벤트를 받아 다음 상태와 **명령**을 돌려주는 순수 함수이고(웹 `web/src/core/sessionMachine.ts`), 마이크·재생·서버 호출·타이머는 화면·플랫폼 계층이 명령을 받아 실행한다. 전이 표 `shared/fixtures/transitions.json`(S3-09)을 웹과 안드로이드 테스트가 함께 읽는다. 3단계 S3-15에서 확정한다.

- **상태**(코드 이름): 대기 `idle`, 듣기 `listening`, 처리 중 `processing`, 말하기 `speaking`, 쉬기 `paused`, 오프라인 보관 `offline`, 정리 `closing`.
- **이벤트**: 버튼 `tap`·`long_press`, 시작 `session_started`(인사말 재생 시작)·`start_failed`, 발화 감지 `speech_start`·`speech_end`, 턴 스트림 `turn`·`sentence`·`turn_done`·`turn_error`·`note_saved`, 재생 `sentence_played`·`playback_idle`, 오프라인 `send_failed`·`offline_notice_done`·`online`·`queue_sent`·`queue_send_failed`, 그 밖 `idle_timeout`·`session_closed`·`end_failed`.
- **명령**: `startSession`, `sendTurn`, `cancelTurn`(턴 ID와 마지막으로 다 들려준 문장 번호), `endSession`, `micOn`·`micOff`, `setVadMode`(재생 중 `playback`으로 임계값 상향), `stopPlayback`, `queueUtterance`, `speakOfflineNotice`, `sendQueued`, `playSound`(`listen`·`saved`·`offline`), `notifyError`, `startIdleTimer`·`clearIdleTimer`.
- **규칙 요약**
  - 한 번 누르기: 대기에서는 시작, 말하기·처리 중에는 끼어들기(재생을 멈추고 취소 뒤 듣기. 처리 중에도 검색 안내 음성이 나오고 있을 수 있다), 쉬기에서는 다시 듣기.
  - 길게 누르기: 대기 외 어디서나 종료(정리 중이면 끝내기 응답을 기다리지 않고 대기로).
  - 답변 문장을 다 들려주고 턴이 끝나면 `done`의 `session_status`에 따라 듣기·쉬기·정리로 간다.
  - 듣기·쉬기에서 30분(`idle_timeout_minutes`) 동안 말이 없으면 정리로 간다. 서버 안전망과 같은 기준이다.
  - 오프라인 큐(S3-12): 새 말을 보내다 서버에 닿지 않으면(`send_failed`) 큐에 넣고 오프라인 안내 뒤 듣는다(`connected=false`). 연결되면(`online`) 큐의 말을 가장 오래된 것부터 보통 턴으로 보내(`sendQueued`) 캐릭터가 차례로 대답한다. 턴을 다 들려주고 끝났을 때·오프라인 안내가 끝났을 때·쉬기에서 다시 들을 때·오류 뒤에도 연결돼 있고 큐가 있으면 듣기 대신 큐부터 보낸다(끼어들기는 사용자가 말하려는 것이므로 바로 듣는다). 큐가 남아 있는 동안 한 새 말은 큐 뒤에 넣어 순서를 지킨다. 보관한 말을 보내는 처리 중(`sendingQueued`)에 한 말도 버리지 않고 큐 뒤에 넣는다(사용자가 막 말을 마친 처리 중에 들어온 말은 지금처럼 버린다). 끼어든 뒤 큐가 남아 있으면 다음 턴이 끝날 때(또는 다음 말) 이어서 보낸다. 큐의 말을 서버가 받으면 `queue_sent {remaining}`, 보내다 서버에 닿지 않으면 `queue_send_failed`(안내 없이 듣기, 말은 큐에 그대로)다. 상태에는 `connected`(서버에 닿는가)가 있다.
  - 표에 없는 조합과 모르는 이벤트는 무시한다.
- **플랫폼이 지킬 것**
  - 인사말은 SSE가 아니라 시작 응답으로 온다. 재생을 시작하며 `session_started {turnId}`(인사말 턴 ID)를 보내고, 재생할 소리가 없으면 바로 `playback_idle`을 보낸다.
  - `sentence`·`turn_done`에는 턴 ID를 싣는다. 머신은 지금 턴과 다른 ID의 이벤트(취소한 턴의 늦은 이벤트)를 무시한다. `turn_error`는 턴 시작 전 오류면 `turnId: null`이다.
  - `sentence` 이벤트는 그 문장 소리를 재생 대기열에 넣은 뒤에 머신에 보낸다. `playback_idle`은 보내는 순간 대기열이 비어 있을 때만 보낸다(`done`보다 먼저 와도 된다).
  - 모든 요청(`startSession`·`sendTurn`·`endSession`)은 성공 이벤트나 실패 이벤트(`start_failed`·`turn_error`·`send_failed`·`end_failed`) 중 하나로 반드시 끝낸다. 시간 초과도 실패로 보낸다.
  - 처리 중에 들어온 발화(`speech_end`)는 버린다.
  - 이어 재생(`AudioOutput`, 웹 `web/src/platform/audioOutput.ts`)은 넣은 순서대로 하나씩 재생하고(디코드는 넣는 즉시 병렬), 답변 문장이 끝날 때마다 `sentence_played {index}`, 대기열이 비면 `playback_idle`을 보낸다. 인사말·검색 안내(`tool.notice`)·마무리 멘트는 문장 번호 없이 넣는다(`sentence_played` 없음). 소리가 없는 문장(`audio: null`)과 디코드·재생에 실패한 소리는 길이 0으로 보고 순서대로 넘어간다. `stopPlayback`은 즉시 멈추고 대기열을 비우며 이벤트를 보내지 않는다. 브라우저 자동 재생 제한 때문에 시작 버튼을 누를 때 오디오를 연다(`unlock`). 소리가 나지 않는 상황(자동 재생 제한, 오디오 중단)에서도 대기열은 멈추지 않는다(다시 켜기를 0.5초만 기다리고, 끝 알림이 오지 않으면 소리 길이 + 2초 뒤 넘어간다). 소리 없는 문장은 넣자마자 `sentence_played`가 나갈 수 있으므로, 플랫폼은 대기열에 넣은 직후 같은 동기 흐름에서 머신에 `sentence`를 보낸다(사이에 `await`을 두지 않는다).
  - 마이크 입력(`AudioInput`, 웹 `web/src/platform/audioInput.ts`)은 `micOn`→`start`, `micOff`→`stop`(트랙을 멈춰 마이크 표시가 꺼진다), `setVadMode`→`setMode`로 받는다. `speech_start`는 말소리가 `min_speech_ms` 동안 이어진 뒤에 보낸다(재생 중 짧은 소음 한 번으로 끼어들기가 되지 않게). 그보다 짧은 소리는 이벤트 없이 버린다. `stop` 뒤에는 이벤트를 보내지 않는다. 마이크 권한 거부(`mic_denied`)·장치 없음(`mic_unavailable`)·감지 모델 로드 실패(`vad_failed`)의 처리는 아래 명령 실행 항목에 있다.
  - 명령 실행(웹 `web/src/screens/voiceController.ts`): `startSession`은 `POST /api/sessions {mode: "voice"}` 뒤 인사말 소리를 대기열에 넣고 `session_started`를 보낸다. `sendTurn`은 음성 턴을 올리고 SSE를 머신 이벤트로 바꾼다(`transcript`는 사용자 말풍선, `sentence`는 소리를 넣은 뒤 `sentence`, `tool.notice`는 번호 없이 대기열에, `save_note` 성공은 `note_saved`). `cancelTurn`은 받는 중인 턴 요청 연결을 끊고(늦은 이벤트를 버린다) 끼어들기 API에 `lastPlayed`를 보낸다(기다리지 않고 실패는 무시: 연결이 끊기면 서버가 보낸 문장까지는 끊긴 답변으로 남긴다). 말풍선도 들려준 문장까지만 남긴다(대화 리듀서 `interrupt`). 인사말은 자르지 않는다. 끝내기 응답 뒤 마무리 소리(`closing_audio`)를 넣고 `session_closed`를 보낸다. 마이크를 쓸 수 없으면(`mic_denied` 등) `long_press`로 대화를 마치고(일지 정리) 정리가 끝난 뒤 이유를 보인다(대기·정리 중에 늦게 온 마이크 오류는 무시). 턴 도중 세션이 서버에서 끝났을 때(`session_ended`)의 문구도 정리가 끝난 뒤 보인다. 정리 중에는 "그만 기다리기"(= `long_press`)로 끝내기 응답을 기다리지 않고 나올 수 있다. 오프라인 보관(S3-12) 전까지는 네트워크 오류도 `turn_error`로 보내 알리고 다시 듣는다(그 발화는 잃는다). 대화 중에는 Screen Wake Lock으로 화면을 켜 두고, Media Session의 재생/일시정지(이어폰 버튼)를 `tap`으로 받는다(재생을 Web Audio로만 해서 브라우저가 미디어 세션을 켜지 않을 수 있다. 실기기 확인은 S3-14). 음성 모듈(vad-web·onnxruntime·mediabunny)은 첫 화면 로딩에서 빼고 화면이 열린 뒤 따로 불러오며, 다 불러오기 전에는 "음성으로 대화"를 막는다(오디오는 버튼을 누른 동작 안에서 열어야 한다). 불러오지 못하면 글로 대화하도록 안내한다. 시작 화면은 "음성으로 대화"·"글로 대화"를 고르고, 고른 방식을 기억해 `prepare`도 그 방식으로 보낸다(서버 준비분이 방식마다 다르다).
  - 오프라인 큐(`LocalQueue`, 웹 `web/src/platform/localQueue.ts`)는 녹음을 대화 ID와 함께 IndexedDB에 보관한다(새로 고쳐도 남는다, IndexedDB를 못 쓰면 메모리로 대신해 새로 고치면 사라진다). 서버에 닿지 않은 실패는 턴 시작(`turn`) 전의 `network_error`·`stream_closed`이고, 그 밖의 오류는 지금처럼 `turn_error`다. `queueUtterance`는 녹음을 큐에 넣고, `sendQueued`는 이 대화의 가장 오래된 말을 보내 `turn`을 받으면 큐에서 지운 뒤 `queue_sent`를 보낸다. 턴이 시작되기(인식 결과가 오기) 전에 30초가 지나면 서버에 닿지 않은 것으로 본다. 큐의 말이 말소리가 없으면(`no_speech` 등) 버리고, 서버 일시 오류면 남겨 두고 `queue_send_failed`로 나중에 다시 보낸다(5번 실패하면 대답을 포기하고 기록만 남겨 뒤의 말을 막지 않는다). 끝내기로 보내던 말이 끊기면 보관해 기록만 남긴다. 서버가 말을 저장한 직후 `turn` 전에 끊기면 다시 보내 한 번 더 기록될 수 있다(최소 한 번 전달). 서버가 대화를 끝냈으면(`session_ended`) 그 말은 대답 없이 기록만 남긴다(`POST …/turns/audio/record`, 아래 2절). 대화가 끝나 대기로 돌아가면(끊긴 채 끝냄 포함) 이 대화에 남은 말과 이전 대화(새로 고치기 전)의 남은 말도 기록만 남긴다(연결이 없으면 다음 연결 때). `speakOfflineNotice`는 기기 TTS(`speechSynthesis`, ko-KR)로 `client.offline_notice`를 읽고 끝나면 `offline_notice_done`을 보낸다(없거나 6초를 넘으면 바로). 연결 복구는 브라우저 `online` 이벤트와, 끊긴 동안 30초마다 `GET /api/health`로 서버에 닿는지 확인하는 것으로 알아챈다. 보관한 녹음은 30일이 지나면 보내지 않고 지우고, 기록만 남기기에 5번 실패한 말도 지운다(기기에 녹음을 끝없이 두지 않게. 유실 0건(NFR-04)의 예외로 둔다). 대답을 포기한 말은 "기록만" 표시로 보통 전송에서 빠진다. 저장소(IndexedDB)에 넣지 못하면 그 말은 메모리에 두고, 읽기·지우기는 두 곳을 모두 본다. 화면에는 보관한 말 수를 보인다.

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

VAD 수치는 시작값이며 실제 산책 측정에서 조정한다. 웹은 `@ricky0123/vad-web`(Silero `v5` 모델)에 `speech/silence_threshold` → `positive/negativeSpeechThreshold`, `end_of_speech_silence_ms` → `redemptionMs`, `min_speech_ms` → `minSpeechMs`로 넘기고, 재생 중(`setVadMode playback`)에는 `playback_*` 값으로 바꾼다. 감지 전 소리 300ms를 발화 앞에 붙인다(웹 상수 `PRE_SPEECH_PAD_MS`). 모델·worklet·onnxruntime wasm은 CDN이 아니라 앱이 `/vad/`에서 서빙한다(약 16MB, wasm이 대부분).

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
