# TrailTalk V2 요구사항·설계 (spec)

> 상태: 초안(8차 독립 리뷰 반영). [intent.md](intent.md)를 입력으로 만들었다. V1 설계서·규약을 대체하지 않고 **V1에 더하거나 바꾸는 부분만** 적는다. 적지 않은 것은 V1 그대로다. 구현 순서와 작업은 plan.md에 쓴다.
> 번호는 `V2-FR-xx`, `V2-NFR-xx`이고 V1 번호는 "V1 NFR-xx"로 쓴다. **[가정]**은 측정 전 추정이며 M0·M1의 측정으로 확정한다. **[코드 확인]**은 설계가 코드의 어떤 동작에 달려 있어 해당 작업 시작 때 확인할 부분이다.

## 1. 개요와 범위

V2는 V1의 구조(웹 PWA + FastAPI + Claude CLI + OpenAI 음성)를 유지하고 두 가지를 개선한다.

1. **답변 시간 단축** — 말이 끝난 뒤 제니의 첫 소리까지.
2. **자연스러운 끼어들기** — 제니가 답하는 도중에 말하면 즉시 멈추고, 끼어든 말을 놓치지 않고, 끊긴 뒤 못 들은 핵심을 먼저 다시 말한다.

| 구분 | 포함 | 제외(후순위) |
|---|---|---|
| 지연 | 무음 대기, 큐 뒷말 즉시 전송, 서버 턴 경로, 첫 문장 분할, 맞장구, 스트리밍 TTS 판단 | 모델 교체·CLI 자체 개선 |
| 끼어들기 | 감지, 정지, 알림음 겹침, 끼어든 말 인식, 정리 대기, 들은 만큼 기록, 이어짐, 엣지케이스 | 스피커 재생 지원(결정), 사용자 말 도중 제니의 추임새(백채널) |
| 측정 | 지연·끼어들기 평가 스크립트, 현장 이벤트 기록 | 일지 품질, 백그라운드 복구, 브리핑, 선제 발화, MCP, 멀티 사용자 |
| 보안 | 인증·Origin 검사(최소, 마지막 마일스톤) | |

**전제(결정 2026-10-19)**: 이어폰(유선·블루투스) 전제, 스피커 재생 미지원. 맞장구 허용. 끼어든 뒤 제니는 못 들은 핵심을 먼저 다시 말한다.

**용어**

- **실제 말 끝**: 사용자가 말을 멈춘 시각. VAD가 끝을 알아챈 시각 − 무음 대기(V1 S3-07 정의). **무음 대기도 지연에 들어간다.** 클라이언트가 아는 시각은 VAD 판정 시각(= 실제 말 끝 + 무음 대기)이고, 이를 **끝 판정**이라 부른다.
- **첫 반응**: 실제 말 끝 뒤 사용자가 처음 듣는 제니의 소리(맞장구 포함). **첫 답변**: 답변 본문 첫 문장의 음성.
- **끼어들기**: 제니의 소리가 나는 중(`speaking`)에 사용자가 말을 시작하는 것. 답변 처리 중(`processing`)에 말을 이어 하는 것은 **이어 말하기**로 구분한다(4.7절 표).
- **말 시작(raw)**: 사용자가 실제로 발성을 시작한 시각. VAD가 처음 의심하는 **probe**, 확정하는 **confirm**과 구분한다. **정지 지연**은 실제 발성 시작 → 소리가 멈출 때까지다.
- **들은 문장**: 끝까지 재생된 문장(`last_played`)과 재생 중 끊긴 문장의 들은 부분.

## 2. 요구사항

### 2.1 답변 시간 단축

| ID | 요구사항 | 우선순위 | 마일스톤 |
|---|---|---|---|
| V2-FR-01 | 지연 구간(무음 대기, 업로드, 인식, 취소 정리 대기, CLI 첫 글자, 첫 문장 합성, 첫 소리, 맞장구)을 턴마다 기록하고, 평가 스크립트로 기준선을 잰다 | P1 | M0 |
| V2-FR-02 | 발화 끝 판정 무음(현재 1800ms)을 줄이는 방안(고정 단축, 동적 방식)을 비교해 고른다. 말 중간 쉼에서 끊기는 S3-33 문제를 되살리지 않는다 | P1 | M1 |
| V2-FR-03 | **큐 뒷말 즉시 전송**: 처리 중 이어 말한 말이 V1 큐에 보관돼 있고 첫 답변 문장이 도착하면, 첫 문장을 재생하지 않고 앞 턴을 취소(`reason: continued`)한 뒤 뒷말을 바로 보낸다. 서버는 "이어서 말함" 안내를 붙인다(3.3절) | P1 | M1 |
| V2-FR-04 | 서버 턴 경로의 불필요한 대기를 없앤다. 합성이 끝난 문장을 다음 CLI 이벤트와 무관하게 내보낸다(`head_ready`) | P1 | M1 |
| V2-FR-05 | 첫 문장을 쉼표·절 단위로 일찍 끊어 합성하되, 서버가 실제로 내보낸 문장 목록을 턴에 저장해 끼어들기의 문장 번호가 어긋나지 않게 한다 | P1 | M1 |
| V2-FR-06 | **맞장구**: 요청을 보낸 뒤 첫 문장이 `ack_delay_ms` 안에 오지 않으면 제니의 짧은 소리를 재생한다. 사용자가 다시 말하면 즉시 멈춘다. 설정에서 끌 수 있다(5장) | P1 | M1 |
| V2-FR-07 | 스트리밍 TTS의 이득을 측정하고, 0.5초 이상 줄일 때만 도입한다(3.5절) | P2 | M1 |
| V2-FR-08 | 발화 오디오를 말하는 도중 조금씩 올리는 방안을 측정한다. 줄일 수 있는 것은 전송 시간(수백 ms 이하)뿐이고 STT는 완성 파일이 필요하다. 이득이 작으면 폐기 | P3 | M1 |
| V2-FR-09 | **뒷말만 보내 이어 붙이기**(조건부): 서버가 앞 사용자 턴 텍스트에 뒷말을 이어 붙여 앞 CLI 진행분을 살린다. M0·M1 측정에서 이득이 확인될 때만 채택(X11, 3.3절) | P3 | M1b |

### 2.2 자연스러운 끼어들기

| ID | 요구사항 | 우선순위 | 마일스톤 |
|---|---|---|---|
| V2-FR-11 | **두 단계 감지**: probe에서 즉시 볼륨을 낮추고(ducking), confirm에서 페이드아웃으로 멈춘다. confirm이 시간 안에 안 오면 볼륨을 되돌린다(4.2절) | P1 | M2 |
| V2-FR-12 | 재생 중 감지 기준을 이어폰 전제로 다시 정해 반응을 빠르게 하되, 제니 목소리·알림음·맞장구·바람에 오작동하지 않게 한다 | P1 | M2 |
| V2-FR-13 | 끼어든 순간 "듣기 시작" 알림음을 내지 않는다. 알림음·검색 안내·맞장구 재생 중에도 자기 소리를 사용자 말로 오인하지 않는다 | P1 | M2 |
| V2-FR-14 | 끼어든 말의 첫 음절이 잘리지 않는다. 끼어든 직후 VAD 임계값은 즉시 평상시로 돌리고, 끼어든 발화의 무음 대기는 별도 값을 쓴다 | P1 | M2 |
| V2-FR-15 | 서버는 취소가 진행 중인 세션의 새 턴을 `TurnBusy`로 거절하지 않고 상한 시간까지 기다린다. M2부터 일반 끼어들기의 음성 새 턴은 클라이언트가 취소 완료를 기다리지 않는다(글 턴과 큐 뒷말 즉시 전송 경로는 기다림, M1에서는 모두 기다림). 이때 `turn_in_progress`를 받으면 재시도하거나 큐에 보관한다. 취소는 연결을 먼저 닫지 않고 취소 API를 먼저 보낸다(M1). 이득은 M0 `cancel_wait_ms`·`cli_restarted` 측정으로 확인한다 | P1 | M2 |
| V2-FR-16 | **들은 만큼 기록**: 문장 도중 끊긴 경우 보수적으로 가늠한 들은 부분까지만 기록하고 나머지를 "못 들은 부분"으로 구분한다(4.5절) | P1 | M2 |
| V2-FR-17 | **끊긴 뒤 이어짐**: 제니는 먼저 못 들은 핵심을 한 문장 안팎으로 다시 말한 뒤 끼어든 말에 답한다. 이미 들려준 내용과 이미 실행된 도구 결과를 되풀이하지 않는다(4.6절) | P1 | M2 |
| V2-FR-18 | 끼어들기를 이벤트로 기록하고(감지·정지 시각, 재생 비율, 결과, 이후 첫 소리까지) 평가 스크립트로 정지 지연·오탐·누락·인식·맥락을 잰다 | P1 | M0·M2 |
| V2-FR-19 | 스피커 사용은 지원하지 않는다. 설정 화면에 "이어폰을 쓰세요" 안내만 둔다 | P3 | M2 |
| V2-FR-20 | **엣지케이스 규칙**: 인사말 중, 연속, 도구 실행 중, 쉬기·끝내기 요청이 걸린 턴, 네트워크 끊김·오프라인 안내 중, 글 입력 중의 끼어들기를 정의된 대로 처리한다(4.7절) | P1 | M2 |

### 2.3 보안(최소, 마지막)

| ID | 요구사항 | 우선순위 | 마일스톤 |
|---|---|---|---|
| V2-FR-21 | 모든 `/api`는 인증 후에만 응답한다(`/api/health` 제외). 단일 사용자 토큰 **[가정]** | P2 | M3 |
| V2-FR-22 | 상태를 바꾸는 요청(턴 SSE 포함)은 `Origin`이 허용 목록이고 `Content-Type`이 `application/json` 또는 오디오 형식일 때만 받는다 | P2 | M3 |
| V2-FR-23 | 웹 로그인 화면, 로그인 시도 제한, 기존 테스트·E2E·가짜 서버에 인증 주입 | P2 | M3 |

### 2.4 비기능

정지·감지 수치는 **소프트웨어 경로 기준**이다(6장). 블루투스 출력 지연(150~300ms)은 실기에서 따로 재고 기록한다.

| ID | 항목 | 기준 |
|---|---|---|
| V2-NFR-01 | 첫 답변 지연 | 중앙값 3초 이내 **[가정: 3.4절 예산상 어렵다. X1에서 재결정]**. 기준선은 M0에서 현재 코드로 다시 잰다(6.6초는 무음 대기 1.2초 시절 값). 30턴 이상 |
| V2-NFR-02 | 첫 반응 지연 | 맞장구 포함, 실제 말 끝 → 첫 소리 중앙값 1.5초 이내 **[가정]** |
| V2-NFR-03 | 체감 정지 | 실제 발성 시작 → 볼륨 절반 이하: 중앙값 0.3초 이내 **[가정, M0 기준선 후 확정]** (VAD 탐지 지연 포함) |
| V2-NFR-04 | 완전 정지 | 실제 발성 시작 → 소리 정지: 중앙값 0.5초 이내, p90 0.8초 이내 **[가정]** |
| V2-NFR-05 | 오탐(이어폰) | 제니가 말하는 10분 동안 사용자 발화 없이 끼어들기 0회(실험실). 현장 10분당 1회 이하(근사, 6장) |
| V2-NFR-06 | 누락 | 사용자가 끼어들었는데 1초 안에 안 멈춘 비율 5% 이하 |
| V2-NFR-07 | 끼어든 말 인식 | 끼어든 발화 첫 3어절 정확도가 재생 없이 보낸 같은 발화의 90% 이상 |
| V2-NFR-08 | 끼어든 뒤 응답 지연 | 끼어든 말의 실제 말 끝 → 첫 소리 중앙값이 같은 조건의 일반 턴 + 0.5초 이내 |
| V2-NFR-09 | 기록 일관성 | (a) 문장 단위: 서버 기록이 실제 들은 문장과 일치하는 비율 100%. (b) 문장 도중 끊김: 들은 부분 경계 오차 ±1어절 이내 90% 이상이고, 오차는 "못 들은 쪽"으로만 난다(들은 것으로 잘못 기록 0건) |
| V2-NFR-10 | 맥락 정합 | 끼어들기 시나리오 20개 중 18개 이상에서 (a) 못 들은 핵심을 먼저 말하고 (b) 이미 한 말을 되풀이하지 않고 (c) 답변을 추임새로 시작하지 않는다 |
| V2-NFR-11 | 톤 | 프롬프트·규칙을 바꾸면 톤 평가 20개 중 18개 이상(V1 NFR-07 유지) |
| V2-NFR-12 | 회귀 | 이어 말하기(S3-33), 쉬기·끝내기 음성 명령, 오프라인 큐, V1 pytest·Vitest·E2E가 마일스톤마다 통과. 건수는 M0에서 다시 센다 |

## 3. 답변 시간 설계

### 3.1 기준선

V1의 중앙값 6.6초(무음 대기·전송 1.25 + 인식 1.1~1.5 + CLI 첫 글자 1.3 + 첫 문장 완성·합성 2.7)는 무음 대기 1.2초 시절의 책상 측정이다. S3-33이 `end_of_speech_silence_ms`를 1200→1800으로 올려 현재는 더 길 수 있다 **[가정]**. M0에서 같은 발화 파일·조건으로 다시 잰 값이 기준선이다.

### 3.2 지연 기록

`turn_latency`(upload_ms, stt_ms, first_token_ms, first_sentence_ms, done_ms, speech_to_request_ms, request_to_playback_ms 등)와 `GET /api/latency`가 이미 있다. 일부(`speech_to_request_ms`, `request_to_playback_ms`)는 클라이언트가 보고한 값이라, **말 끝 → 첫 소리 전체는 브라우저를 구동해야 재현된다**.

- 추가 컬럼: `cancel_wait_ms`(이전 턴 정리를 기다린 시간), `ack_ms`(맞장구가 재생되기 시작한 시각, 요청을 보낸 시각 대비 ms, 클라이언트 보고), `merged`(큐 뒷말 즉시 전송으로 보낸 턴인지), `cli_restarted`(취소 때 CLI가 재기동됐는지), `queued_at_first_sentence`(첫 `sentence` 시점에 뒷말이 큐에 있었는지), `second_utterance_phase`(뒷말이 앞 턴의 `turn` 이벤트 전/후 어느 쪽에서 끝났는지), `cancelled_turn_id`(취소한 턴 id). 컬럼 전체는 7장 데이터 표를 따른다.
- **기존 지표 유지**: `request_to_playback_ms`와 `total_ms`는 맞장구를 제외하고 첫 답변 문장 기준으로 유지해 V1 기준선과 비교할 수 있게 한다. 첫 반응은 `ack_ms`로 따로 본다. `merged` 턴의 `speech_to_request_ms`는 뒷말 끝이 아니라 큐에서 꺼내 보낸 시각 기준이 될 수 있어 `merged`로 구분해 중앙값을 따로 센다.
- **연결 키**: `cancel_wait_ms`는 취소 요청에서 재지만 지연 행은 다음 턴 것이므로, 취소한 턴의 id를 다음 턴 행에 기록해 연결한다(M0에서는 서버 로그·별도 계측으로 먼저 잰다). `GET /api/latency` 요약은 `stages`(단계별 중앙값)에 `cancel_wait_ms`, `ack_ms`를 더한다.
- 클라이언트 보고 요청 `POST /api/sessions/{id}/turns/{turn_id}/latency`의 스키마(`LatencyReport`, 모르는 필드는 거부)에 선택 필드 `ack_ms`, `merged`, `queued_at_first_sentence`, `second_utterance_phase`를 더한다(7장 API 표).
- 평가 스크립트 `server/tests/latency_eval/`: (1) 서버 단계(인식, CLI 첫 글자, 합성)는 같은 발화 파일을 직접 호출해 잰다. (2) 말 끝 → 첫 소리 전체는 Playwright로 구동해 `GET /api/latency` 요약을 쓴다. 검색 턴은 따로 센다(`total_ms_reply`). 결과는 `docs/eval/latency-<날짜>.md`.

### 3.3 무음 대기와 발화 병합 (V2-FR-02, 03, 09)

- **무음 단축**: 1800 → 800~1000 고정값과, 문장이 끝난 듯한 단서(직전 소리 크기 감소, 발화 길이)가 있으면 짧게·말 중간이면 길게 하는 동적 방식을 시험한다 **[가정]**. 1800은 긴 발화가 끊겨 뒷말이 사라지는 S3-33 문제를 고치려 올린 값이므로, 이어 말하기 E2E 3회 연속 통과와 현장 데이터로만 확정한다.
- **무엇이 문제인가**: 무음을 줄이면 말이 쪼개지는 일이 늘어난다. 현재는 첫 답변 문장이 오기 전에 두 번째 말이 끝나면(`processing` 중 `speech_end`) 뒷말이 V1 큐에 보관되고, 앞 답변이 그대로 재생된 뒤 뒷말이 별도 턴이 된다. 병합은 말이 끝난 뒤 첫 소리를 빠르게 하는 장치가 아니라, 무음 단축의 부작용(쪼개진 말에 반쪽 답이 재생됨)을 줄이는 **품질 장치**다.
- **채택안 (M1): 큐 뒷말 즉시 전송** — 서버 변경이 작은 쪽을 먼저 쓴다.
  0. **용어**: 이 문서에서 "병합"은 채택안(큐 뒷말 즉시 전송)을 뜻하고, `merged`·`merge_min_speech_ms`도 채택안용이다. 조건부 안(M1b)은 "이어 붙이기"로 부른다.
  1. **조건**: 상태가 `processing`이고 `sendingQueued`가 아니며(오프라인 잔여와 구분) 마지막으로 보낸 턴이 글 턴이 아니고(`typedTurn`이 아님. 글 입력도 `speech_end`로 머신에 들어와 상태에 글/음성 구분이 없으므로 `typedTurn` 플래그를 `sendTurn`/`NEW_TURN` 전이에서 세운다) 뒷말이 V1 큐에 **정확히 하나**(`queued == 1`) 보관돼 있으며, 첫 `sentence` 이벤트가 도착했을 때, 그리고 그 뒷말의 실제 음성 길이(`queuedSpeechMs`)가 `merge_min_speech_ms`(기본 600 **[가정]**) 이상일 때. 큐에 항목이 둘 이상이면 가장 오래된 항목만 보내는 큐 순서(`oldest`) 때문에 앞의 잡음 항목이 먼저 나가고 안내가 엉뚱한 턴에 붙을 수 있으므로 병합하지 않고 V1 큐 동작을 유지한다. 병합 직후 `sendingQueued` 턴을 처리하는 중에 또 뒷말이 오는 연쇄 병합도 하지 않는다.
  2. **동작**: V1은 이 시점에 사용자가 말하는 중(`userSpeaking`)이면 첫 문장을 재생하지 않고 취소한 뒤 듣는다(S3-33). 이 분기보다 **뒤에** "조건을 만족하면 첫 문장을 재생하지 않고 `stopPlayback`(첫 문장 오디오는 머신 이벤트 전에 이미 출력 큐에 들어가 있다)과 `ackPlaying`·검색 안내 해제(`NEW_TURN`에 `ackPlaying: false` 포함)를 낸 뒤 `setVadMode normal`(맞장구·검색 안내가 올린 재생 모드를 풀어 병합이 노리는 구간에서 이어 말하기 감도가 떨어지지 않게 한다. 병합 전이는 `processing`→`processing`이라 `enterListening`의 해제가 없다), `cancelTurn`(들은 문장 없음, `reason: continued`)을 보내고, **취소 응답을 기다린 뒤**(V1의 `await cancelling`을 유지) 큐의 뒷말을 보통 턴으로 보낸다"를 더한다. 명령 순서는 `stopPlayback`, `setVadMode normal`, `cancelTurn`, `clearIdleTimer`, `sendQueued`이며, V1의 `sendQueued(state, [stopPlayback, ...cancelCurrent(state)])` 헬퍼로 표현한다. "취소 응답 후 전송"은 머신 이벤트가 아니라 명령 순서와 컨트롤러의 `cancelling`(`cancelTurn` 실행에서 동기적으로 세워지고 이어지는 `runTurn`이 `await`)으로 보장한다. 턴 요청에는 새 필드가 없다(취소 API에만 `reason`을 더한다). 서버 기록 수정은 없다. 사용자 턴은 앞말·뒷말 둘이 남는다(일지 추출은 사용자 턴 텍스트를 이어 읽으므로 지장이 없다). 취소 응답 대기는 뒷말이 이미 보관돼 있어 추가 지연이 작다. 병합 후 상태는 `processing` + `turnId = null` + `sendingQueued = true`이며, 이 구간(약 1.2초 이상)의 `tap`은 V1처럼 무시된다(`turnId`가 없어 취소할 대상이 없다).
  - **큐 항목의 음성 길이**: 머신은 `queued: number`만 가지고 `QueuedUtterance`에는 음성 길이가 없다(녹음 길이는 `durationMs: 0`으로 버려진다). 머신 상태에 `queuedSpeechMs`(가장 오래된 항목의 음성 길이)를 더하고, `queueUtterance` 명령과 `queue_sent` 이벤트가 이를 싣거나 갱신한다. `QueuedUtterance`에는 선택 필드 `speechMs?`를 더한다(IndexedDB는 선택 필드라 마이그레이션이 필요 없다). **갱신 규칙**: 큐 0→1은 `speech_end.speechMs`, 1→2는 유지, `queue_sent`로 줄 때 새 가장 오래된 항목의 값이 필요하므로 `queue_sent`가 `nextSpeechMs`를 싣거나 컨트롤러가 `id → speechMs` 메모리 맵을 둔다(`dequeue`는 현재 `queued - 1`만 계산하고 큐를 읽지 않는다). `queue_sent{remaining: 0}`이면 0으로 지운다. 이전에 IndexedDB에 저장된 항목은 `speechMs`가 없으므로 값이 없으면 병합하지 않는다. 병합 직후 상태는 `processing`, `turnId = null`, `sendingQueued = true`, `queued = 1`, `queuedSpeechMs`는 그대로다.
  3. **서버 안내**: 취소 API에 선택 필드 `reason`(`barge_in`·`continued`)을 더한다. 취소 요청 스키마(`TurnCancel`, `extra="forbid"`)에 `reason: Literal['barge_in', 'continued'] | None`을 더하고 생략은 `barge_in`과 같다(구 클라이언트는 현행 `INTERRUPTED_*` 동작). 서버는 `reason`을 `cancel_turn` → `_trim_reply`(호출 3곳)로 전달하고, `_trim_reply`에서 `reason == continued`이면 `CONTINUED_UTTERANCE`를, 아니면 `_heard_note(heard, unheard)`를 고른다(그래서 `_heard_note` 시그니처는 `reason`과 무관하다). `continued`이면 `INTERRUPTED_NOTHING`("하나도 듣지 못했다")과 4.6절의 "못 들은 핵심 다시 말하기" 대신 `persona/rules.py`의 새 상수 `CONTINUED_UTTERANCE`(`INTERRUPTED_HEARD`·`INTERRUPTED_NOTHING` 옆, `prompt.py`는 건드리지 않음)를 다음 턴 프롬프트에 붙인다: "사용자가 방금 한 말에 이어서 말했다. 앞말과 이어 말한 것을 합친 전체에 한 번만 답하라. 메일·저장 같은 도구는 앞 턴에서 이미 실행됐을 수 있으니 다시 실행하기 전에 확인하라." 톤 평가·스냅샷(`UPDATE_SNAPSHOTS`) 대상이다. 앞 턴에서 이미 실행된 도구 호출은 4.6절처럼 요약해 전달한다. **안내가 빠지는 경로(알려진 한계)**: 서버 재시작 뒤(`runtime` 없음), 락 대기 10초 초과(턴이 아직 실행 중이면 자르지도 안내하지도 않고 반환, 실행 중이 아니면 `_trim_reply(..., None)`), 최신 답변이 아닌 경우, 답변 행이 없어 `TurnNotFound`인 경우. 취소 요청을 재시도·보관할 때 `reason`도 함께 보관한다(4.7절).
  4. **병합하지 않는 경우**: 상태가 `speaking`(첫 문장 재생이 이미 시작), `sendingQueued`, `queued != 1`, 글 입력 턴(`typedTurn`), 뒷말이 `merge_min_speech_ms` 미만(잡음 보호), `queuedSpeechMs`가 없는 옛 큐 항목. 이때는 V1 큐 동작을 유지한다. 근거: `processing`·`speaking`·`offline`의 `speech_end`가 모두 같은 `queued`를 올리지만, `processing && !sendingQueued && queued == 1`이면 오프라인 잔여가 섞일 수 없다(`offline` 상태는 이미 걸러진다).
  5. **비용과 한계**: 뒷말의 응답 시작이 앞 턴의 첫 `sentence` 도착 시점으로 밀린다(최악 약 2초). 뒷말이 인식 단계에서 `no_speech`로 판명되면 앞 답변은 이미 취소된 뒤이므로 앞말이 답 없이 남는다(V1의 `userSpeaking` 취소 경로와 같은 한계, `merge_min_speech_ms`로 줄임). 검색 안내(`tool.notice`) 중이면 서버가 이미 웹 검색을 시작했을 수 있어 취소가 검색을 버린다(구독 사용량 비용).
  6. **취소 순서(CLI kill 회피)**: V1 컨트롤러는 취소 때 `turnAbort.abort()`로 SSE 연결을 먼저 닫고 `cancel` API를 보낸다. 서버는 연결 끊김을 anyio 취소로 받고, `claude_cli`의 `_abort_turn`은 `CancelledError`에서 CLI 프로세스를 **kill**한다(`--resume`으로 다시 띄운다). 처리 중(CLI가 생성 중)에 취소하면 매번 CLI 재기동 비용(인사말 대기 기준 약 1.4초 이상)이 든다. 정상 인터럽트(`cancel` API 경로)는 `result`까지 읽어 프로세스를 살린다. 그래서 취소는 `cancel` API를 **먼저** 보내고, 응답(204) 또는 짧은 상한(`cancel_abort_wait_ms`, 기본 1500 **[가정]**) 뒤에 연결을 닫는다. 재생 정지는 `cancel` 응답을 기다리지 않는다. 이 변경은 일반 끼어들기에도 적용되며 [코드 확인] 대상이다.
     - **연결을 열어 둔 동안의 늦은 이벤트**: V1은 이 때문에 취소와 함께 스트림도 끊는다(클라이언트 규약: 계속 읽으면 `done.text`는 자르기 전 전체 답변이다). 컨트롤러의 이벤트 핸들러는 `abort.signal.aborted`일 때만 이벤트를 버리므로, 연결을 유지하는 동안 늦은 `sentence`는 출력 큐에 들어가 재생되고, 말풍선이 되살아나며, `done.text`가 말풍선을 전체 답변으로 되돌리고, `tool.notice`가 재생 모드를 다시 올릴 수 있다. 그래서 **턴별 `cancelled` 플래그**를 둔다. `runTurn` 클로저의 지역 변수로는 `cancelTurn` 명령 실행부에서 닿지 않으므로, 단일 `turnAbort` 대신 `activeTurn = { abort, cancelled, turnId }` 핸들로 바꾼다. 명령 실행부는 `command.turnId`가 핸들의 `turnId`와 같을 때만 취소한다(새 `runTurn`이 이미 핸들을 덮어쓴 경우 다른 턴을 잘못 취소하지 않으려는 것). `cancelTurn` 실행 시점에 `cancelled`를 세우고, **이벤트 핸들러 맨 앞과 `catch` 블록 맨 앞** 모두에서 `aborted || cancelled`이면 반환한다(`catch`의 `measuring = null`이 새 턴의 지연 측정을 지우는 것과 `closingReason` 설정을 막기 위해서다). 지연 close는 취소 시점에 잡아 둔 **이전** `AbortController`를 대상으로 하고, V1이 하던 `turnAbort = null`은 하지 않는다. 취소로 따로 빠진 컨트롤러는 `Set`에 보관해 `dispose`와 `endConversation`에서 함께 abort하고 타이머를 해제한다. 취소 API가 즉시 실패하면 `cancel_abort_wait_ms`를 기다리지 않고 바로 닫으며, 재시도는 연결을 붙잡지 않는다. 취소된 턴의 `tool.note_saved` 이벤트는 버려져 `saved` 효과음이 나지 않는 것은 V1과 같은 한계다. 클라이언트 규약의 개정 항목은 7장에 나열한다.
     - **타이머와 취소 응답 대기의 관계**: 응답이 `cancel_abort_wait_ms` 안에 오지 않으면 연결을 닫아 서버가 CLI를 kill한다(`cli_restarted = true`). 한편 다음 턴은 취소 응답(서버 대기 최대 10초)을 계속 기다린다. 정상 인터럽트 중 도구(웹 검색)가 실행 중이어 유예 시간(`_ABORT_GRACE_S`)을 넘겨 `_terminate`로 닫히는 경로도 `cli_restarted`로 센다.
- **조건부 안 (M1b, V2-FR-09): 뒷말만 보내 이어 붙이기** — 서버가 앞 사용자 턴 텍스트에 뒷말을 이어 붙여 앞 CLI 진행분을 살리는 방식. 이득은 뒷말의 응답이 첫 `sentence`를 기다리지 않는 것뿐이고 복잡도가 크다(서버 매핑·제자리 수정·락 대기 우회·클라이언트 말풍선 교체). 아래를 모두 만족하는 근거가 M0·M1 측정에서 나올 때만 채택한다(X11).
  - 측정: (a) 첫 `sentence` 시점에 `queued > 0`인 비율, (b) 뒷말이 앞 턴의 `turn` 이벤트 전/후 어느 쪽에서 끝나는지, (c) 채택안의 뒷말 응답 지연.
  - 적중 구간 추정: `turn` 이벤트는 요청 후 약 1.1~1.5초, 첫 `sentence`는 예산상 요청 후 약 2.7~3.8초이므로 `turn`~첫 `sentence` 창은 약 1.4~2.5초다. 이 창 안에서 뒷말이 시작하고 무음 대기까지 끝나야 해서, 대부분의 이어 말하기는 `turn` 전에 끝나 더 복잡한 보관 경로를 탄다.
  - 채택 시 상세화할 요구(리뷰에서 확인된 설계 제약): 앞 턴은 연결을 닫아 kill하지 않고 서버가 정상 인터럽트한다(뒷말 인식으로 말이 있음을 확인한 뒤). 병합 CLI 입력은 앞말+뒷말 전체. 어시스턴트 id→사용자 턴 id 매핑은 `assistant_id` 생성 직후 `TurnEvent` 전에 기록(연쇄 병합 포함). 앞 사용자 턴은 지우지 않고 `text`만 갱신(`note.turn_id`·메일 가드·음성 파일 보호, 뒷말 음성은 보관하지 않음). 락을 잡은 뒤 조건 재검사. 병합 턴의 `_run_turn`은 사용자 턴 생성을 건너뛰고 `runtime.current_user_turn_id`를 앞 사용자 턴 id로 설정. STT 힌트로 앞말을 줄 때 결과가 힌트와 같으면 `no_speech`로 취급. `transcript` 이벤트는 병합된 전체 텍스트를 싣고 클라이언트는 앞 사용자 말풍선을 교체하며 앞 어시스턴트 빈 말풍선을 제거. 병합 표시는 IndexedDB가 아니라 컨트롤러 메모리에 둔다.
- **`speech_end`의 음성 길이**: 병합·맞장구 조건(`merge_min_speech_ms`, `ack_min_speech_ms`)은 실제 음성 길이가 필요한데, 현재 녹음 길이(`RecordedAudio.durationMs`)는 앞 패딩과 뒤 무음을 포함한 전체 샘플 길이이고 `speech_end` 이벤트는 `utteranceId`만 싣는다. `AudioInput`이 음성 프레임 수로 `speechMs`를 계산해 `speech_end`에 싣고, 전이 표 픽스처의 `speech_end` 사례 형식도 바꾼다.
- 전이 표(`transitions.json`)에 사례를 더한다: `processing` 중 뒷말 보관 → 첫 `sentence`에서 취소·전송, 뒷말이 짧아 병합 안 함, `queued > 1`이라 병합 안 함, `speaking` 진입 뒤 뒷말(병합 안 함), 오프라인 큐가 있는 경우, 병합 직후 `tap`(무시됨).

### 3.4 예산

| 구간 | V1 측정(S3-33 전) | V2 예산 **[가정]** | 수단 |
|---|---|---|---|
| 무음 대기·전송 | 1.25 | 1.0~1.2 (무음 0.8~1.0 + 전송 0.2) | 3.3절, 업로드 선전송(FR-08) |
| 음성 인식 | 1.1~1.5 | 1.0~1.3 | 업로드 크기·형식 재측정(큰 개선 기대 안 함) |
| CLI 첫 글자 | 1.3 | 0.9~1.3 | 변경 없음. 첫 토큰 시간은 줄지 않았다(handoff 4장) |
| 첫 문장 완성·합성 | 2.7 | 0.8~1.2 | 3.5절 |
| **합계** | **약 6.4~6.8** | **약 3.7~5.0** | |

합계가 3초를 넘는다. 그래서 맞장구(5장)로 **첫 반응**을 실제 말 끝 + 1.5초 안에 주고, 첫 답변 기준은 X1에서 재결정한다. 측정이 기대와 다르면 멈추고 사실대로 보고한 뒤 방향을 묻는다.

### 3.5 서버 턴 경로 (V2-FR-04, 05, 07, 15)

- **합성 완료 문장 즉시 전송**: `conversation._run_turn`에서 합성이 끝난 문장이 다음 CLI 이벤트가 와야 나가는 구조(`head_ready`는 이벤트 루프 안에서만 확인)를 고친다.
- **일반 끼어들기의 취소와 새 턴**: V1은 음성 턴에서 STT를 SSE 시작 전에 끝내고, 그 뒤 `stream_turn`이 턴 락을 확인한다. 락이 잡혀 있으면 기다리지 않고 즉시 `TurnBusy`를 돌려준다(자르기와 `heard_note` 설정이 락 안에서 끝나야 바로 뒤 턴이 안내를 놓치지 않기 때문). `cancel_turn`은 이미 "락 밖에서 인터럽트를 보내고 턴 종료를 최대 `_CANCEL_WAIT_S`(10초) 기다린 뒤, 락 안에서 답변을 자르고 `heard_note`를 설정"하는 구조이며 분리 작업은 필요 없다.
  - **취소 진행 표시**: `cancel_turn`은 시작할 때 세션에 "취소 진행 중" 표시와 완료 이벤트(`asyncio.Event`, `finally`에서 set)를 둔다. 취소가 재시도로 두 번 겹쳐 들어와도 서로 덮어쓰지 않도록 카운터로 관리하고, 세션 조회가 404로 실패해도 `finally`에서 표시를 지운다. 새 턴이 `TurnBusy`로 거절되는 대신 표시가 있으면 이 이벤트를 상한까지 기다린 뒤 락을 잡는다. `asyncio.Lock`은 선입선출이라 먼저 기다리던 `cancel_turn`이 보통 먼저 락을 얻지만, 이벤트는 "취소가 진행 중"과 "그냥 다른 턴이 진행 중"(`TurnBusy`)을 가르는 데 필요하다. 표시가 없고 락이 잡혀 있으면 V1처럼 `TurnBusy`다.
  - **CLI를 여는 중**: `active_turn[1]`이 아직 없는 구간(`open_llm` 중)에는 `interrupt()`를 보낼 수 없다(V1도 같다). `_run_turn`이 `open_llm` 직후 "취소 요청 플래그"를 확인해 바로 인터럽트하게 한다.
  - 이득은 일반 끼어들기에서 취소(끼어든 직후)와 새 턴(말이 끝난 뒤, 수 초 후) 사이에 간격이 있어 작을 수 있으므로 M0 `cancel_wait_ms`로 먼저 잰다 **[가정]**.
- **취소 순서와 CLI 재기동**: V1과 달리 클라이언트는 연결을 먼저 닫지 않고 `cancel` API를 먼저 보낸다(3.3절 6번). 연결 끊김은 CLI 프로세스를 kill하고 `--resume`으로 재기동하게 한다.
- **새 턴의 사전 검사 위치**: `check_turn_allowed`는 동기 함수로 `create_turn`·`create_audio_turn`이 STT 전에 부르며, 락이 잡혀 있으면 여기서 이미 `TurnBusy`(JSON 409)를 던진다. "취소 진행 중이면 `TurnBusy`를 던지지 않음"은 이 두 곳과 `stream_turn`의 `locked()` 검사 모두에 적용하고, 실제 기다림은 `stream_turn`에서 한다. 음성 턴은 STT 중에 취소가 끝나는 경우가 많아 STT 앞 검사만 완화해도 이득이 크다.
- **첫 문장 조기 분할**: `voice/sentences.py`에 첫 조각만 쉼표·절 단위로 짧게 끊는 옵션(최소 글자 수, 쉼 위치 규칙). 톤 평가에 포함한다.
  - **문장 번호 확정**: 서버는 메모리(`runtime.reply_sentences`)에 내보낸 문장을 기억하지만, 서버 재시작 뒤에는 저장된 답변을 다시 나눠 번호를 맞추는 폴백이 있다(알려진 한계). 조기 분할을 쓰면 폴백 재분할이 맞지 않으므로 실제 내보낸 문장 목록을 영구 저장한다(`turn.spoken_sentences`, JSON, 기존 행은 NULL → 재분할 폴백, 마이그레이션).
  - 취소 시 합성 큐를 비우고 남은 합성은 버린다.
- **스트리밍 TTS 비용**: 현재 `sentence` 이벤트는 문장 전체 MP3를 base64로 싣고, `AudioOutput`은 문장 전체를 `decodeAudioData`로 디코드한다. 스트리밍은 청크 이벤트(`audio.chunk`)와 점진 재생기가 필요한 큰 변경이다(규약의 "모르는 이벤트 무시" 덕에 호환은 된다). 취소 시 서버 합성 요청도 끊어야 한다. M1에서는 **측정으로 이득만 확인**하고 0.5초 미만이면 제외한다.
- **구독 사용량**: 병합과 취소가 늘면 취소된 CLI 턴도 한도를 소모한다. `GET /api/usage`로 M1·M2 평가 때 사용량을 기록한다.

## 4. 끼어들기 설계

### 4.1 V1 현황과 한계 (코드 확인)

| 항목 | 현재 동작 | 한계 |
|---|---|---|
| 감지 | 재생 중 VAD는 `playback` 모드(`playback_speech_threshold` 0.8, `silence` 0.65). vad-web은 `onSpeechRealStart`만 쓰며, 확정은 **누적** 음성 프레임이 `min_speech_ms`(300) 분량에 이르면 난다 | 작은 목소리·짧은 "응"을 놓친다. 누적이라 흩어진 잡음 프레임도 쌓인다. 정지 지연은 측정한 적 없다 |
| 정지 | `AudioOutput.stop()`이 `source.stop()`으로 즉시 끊음 | 페이드·ducking 없음 |
| 끊긴 뒤 상태 | `speaking → listening`, 마이크는 켜져 있고 `setVadMode normal` | `enterListening`이 `playSound('listen')`을 내보내 알림음이 사용자 말 위에 겹침. 재생 모드의 negative 임계값(0.65)이 끼어든 발화의 말끝을 빨리 끊을 수 있음(S3-33 원인) |
| 끼어든 발화 끝 판정 | 평상시와 같은 무음(1800ms) | 끼어든 직후 응답이 느림 |
| 다음 턴 전송 | `await cancelling` 뒤 전송. 서버는 락이 잡혀 있으면 `TurnBusy`로 즉시 거절하고, `cancel_turn`은 턴 종료를 최대 10초 기다림 | 정리 시간이 응답 지연에 섞일 수 있으나 `turn_latency`에 구간 없음 |
| 취소 요청 실패 | 컨트롤러가 실패를 무시(`.catch(() => {})`) | 끊김 중 끼어들면 `last_played`가 서버에 전달되지 않음 |
| 기록 | 문장 단위로 `last_played`까지 남기고 `interrupted`, 다음 턴에 `heard_note` 한 개(최신 답변일 때만 갱신) | 문장 도중 끊으면 그 문장을 못 들은 것으로 처리 → 같은 말 되풀이 가능. 부분 재생은 기록하지 않음. 연속 끼어들기 시 앞의 못 들은 부분이 사라짐 |
| 처리 중 이어 말하기(S3-33) | 처리 중 `speech_end`는 큐 뒤에 넣음. 첫 문장이 올 때 사용자가 말하는 중이면 취소하고 뒷말을 듣는다 | 첫 문장 전에 말을 마치면 별도 턴(3.3절의 큐 뒷말 즉시 전송으로 완화) |
| 검색 안내 음성 | `tool.notice` 재생 중 VAD를 `playback`으로 올림 | 그동안 이어 말하기 감도 저하 |
| 에코 | 브라우저 기본 에코 제거(`echoCancellation: true`)에만 의존 | 이어폰 조건별 검증 없음 |
| 인사말 | `greeting` 턴은 자르지 않고 `heard_note`도 붙지 않음 | 인사말이 끊겼다는 사실을 제니가 모름 |
| 도구 부작용 | `send_email`·`save_note` 등은 CLI 인터럽트 전에 이미 실행됐을 수 있고, 쉬기·끝내기 요청은 턴이 끊겨도 반영(`pop_requested_status`) | 끼어든 뒤 중복 실행·상태 불일치 가능 |

### 4.2 감지와 정지 (V2-FR-11, 12, 14)

이어폰 전제라 제니 목소리가 마이크로 되돌아오는 양이 스피커보다 훨씬 작다. 재생 중 기준을 낮출 수 있다. vad-web 0.0.31은 `onFrameProcessed(probs, frame)`로 프레임(약 32ms)마다 음성 확률을 주고 `setOptions`로 임계값·`minSpeechMs`·`redemptionMs`를 런타임에 바꿀 수 있다(`setOptions`는 진행 중 발화 상태를 초기화하지 않는다). 아래는 이를 이용해 **재생 중(`playback` 모드)에서만** probe/confirm을 직접 판정하는 방식이다. 평상시(`normal`) 모드는 V1의 `onSpeechRealStart` 그대로다.

1. **probe**: 프레임 확률 ≥ `probe_threshold`가 연속 `probe_frames`(기본 2~3 **[가정]**)이면 새 이벤트 `speech_probe`를 머신에 올린다. 한 프레임만으로는 ducking하지 않는다. `probe_threshold`는 재생 모드의 vad-web `positiveSpeechThreshold`(= `playback_speech_threshold`)와 **같은 값**(기본 0.6 **[가정]**)으로 맞춘다. 값이 다르면 vad-web의 발화 버퍼 시작(raw start)과 probe 시각이 어긋난다. 머신은 `speaking`에서 `duckPlayback`을 내고 `AudioOutput`이 볼륨을 `duck_gain`(기본 0.2 **[가정]**)으로 낮춘다.
2. **confirm**: V1의 누적 프레임 확정 대신, 최근 `confirm_window_ms`(기본 200 **[가정]**) 안에서 음성 프레임 비율이 `confirm_ratio`(기본 0.6 **[가정]**) 이상이면 `speech_start`(확정)를 낸다. 비율의 분모는 윈도우가 다 차지 않았을 때 지금까지의 프레임 수다(최단 약 120ms에서 확정 가능). 흩어진 잡음 프레임이 쌓여 확정되는 것을 막는다.
3. **되돌림은 타이머로**: vad-web의 `onVADMisfire`는 redemption(재생 중 1800ms) 뒤에야 발생해 ducking이 약 1.8초 풀리지 않으므로 되돌림에 쓰지 않는다. probe 뒤 `probe_timeout_ms`(기본 400 **[가정]**) 안에 confirm이 없으면 `speech_misfire`로 `unduckPlayback`한다.
4. **정지**: confirm 도착 시 `fadeOutPlayback`(`fade_ms` 기본 80 **[가정]**)으로 멈추고 `cancelTurn`을 보낸다. 하드 컷 `stopPlayback`은 종료·오류용으로 남긴다. 페이드 중에는 `source`가 살아 있으므로 `generation`을 즉시 올려 `sentence_played`·`playback_idle`을 내보내지 않는다. 재생 비율은 **페이드·정지 전에** 컨트롤러가 `output.playedRatio()`로 읽어 `cancelTurn` 명령에 싣는다(현재 명령 순서에서는 stop 뒤에는 읽을 수 없다).
5. **재생 중 임계값**: `playback_speech_threshold` 0.8 → 0.6 안팎, `playback_silence_threshold` 0.65 → **0.4 안팎** **[가정]**. 서버 검증(`client_config.py`)은 `playback_silence_threshold < playback_speech_threshold`와 각 값이 평상시 값 이상일 것을 요구하므로, 0.6/0.4는 기존 검증을 통과한다(0.4 ≥ 0.25, 0.6 ≥ 0.5). speech만 0.6으로 내리면 silence(0.65)와 순서가 어긋나 설정 로드가 실패하므로 두 값을 함께 바꾼다. 필요한 서버 변경은 신규 키 추가(`VadConfig`가 `extra="forbid"`)뿐이다. 값은 M0 기준선과 M2의 되먹임 실험(6장)으로 정한다.
6. **첫 음절 보존**: 감지 전 소리를 붙이는 `PRE_SPEECH_PAD_MS`(300ms)는 raw 시작 **이전**만 덧붙인다. 발화 버퍼는 raw 시작 프레임부터 담으므로 확정 지연 때문에 앞이 잘리지는 않는다. 앞이 잘리는 실제 원인은 부드러운 첫 음절이 높은 임계값(0.8)을 못 넘어 raw 시작 자체가 늦어지는 것이다. 임계값을 낮춘 뒤 평가 wav의 시작 오프셋으로 첫 음절 포함 여부를 검증한다.
7. **`AudioInput` 재생 모드 규칙** (vad-web 동작을 근거로 한다)
   - 재생 모드에서는 `onSpeechRealStart`를 쓰지 않는다. 이 콜백은 누적 프레임 수가 `minSpeechFrames`와 **같아지는 순간 한 번**만 불리므로 발화 도중 `minSpeechMs`를 바꾸면 영영 불리지 않는다. 앱의 confirm이 그 역할을 한다.
   - `minSpeechMs`는 재생 모드에서 `playback_min_speech_ms`(낮은 값)로 두어, 앱 confirm은 통과했는데 vad-web의 누적 300ms에 못 미치는 짧은 발화("응", 약 150ms)가 `onVADMisfire`로 버려지는 일을 막는다.
   - 낮은 `minSpeechMs`의 부작용: probe 수준의 짧은 잡음도 vad-web이 `SpeechEnd`로 낸다. 그래서 **앱 confirm이 선 발화의 `SpeechEnd`만 `speech_end`로 내보내고**, confirm 없는 `SpeechEnd`와 `VADMisfire`는 조용히 버린다. 그렇지 않으면 잡음이 헛 STT 호출과 오프라인 큐 오염을 만든다.
   - **이미 진행 중이던 발화는 폐기하지 않는다**: vad-web은 첫 프레임에서 발화를 시작하고 `onSpeechRealStart`는 누적 프레임이 최소값과 같아지는 순간 한 번만 불린다. 사용자가 평상시 모드에서 말을 막 시작한 직후 재생 모드로 바뀌면(맞장구·검색 안내·`send_failed`) 최소값이 낮아져 그 콜백이 영영 불리지 않고, confirm도 없어 `SpeechEnd`가 폐기된다. 그래서 `AudioInput`은 `onSpeechStart`(raw 시작)를 모드와 무관하게 받아 "평상시 모드에서 시작된 발화" 플래그를 두고, 이 플래그가 있으면 `SpeechEnd`를 폐기하지 않고 내보낸다. 맞장구는 `userSpeaking`이면 재생하지 않고 `setVadMode`도 내지 않는다(V1 검색 안내와 같은 가드).
   - **앞쪽 잡음 잘라내기**: 재생 모드에서 단발 프레임이 `speaking`을 켜면, negative 임계값(0.4)이 낮아 제니 목소리 누설이 무음으로 세어지지 않아 `speaking`이 재생 내내 이어지고 `audioBuffer`가 쌓일 수 있다. 끼어든 발화의 `SpeechEnd` 오디오가 수 초 앞의 누설·잡음을 담으면 V2-NFR-07(첫 3어절 정확도)에 불리하다. 앱이 `onFrameProcessed`로 프레임을 세어 probe 시작 프레임 − `PRE_SPEECH_PAD_MS` 위치부터 오디오를 잘라 쓴다(끝에서 거꾸로 센다).
   - confirm 뒤에 `onVADMisfire`가 오면 `speech_misfire_after_confirm`으로 받아 "발화 없음"으로 보고 듣기를 이어 간다(제니는 이미 취소됐으므로 재개하지 않는다).
   - confirm 즉시 positive·negative 임계값을 평상시(0.5, 0.25)로 돌린다(제니 소리가 이미 멈췄다). 발화가 끝날 때까지 기다리면 재생 모드의 negative 임계값이 말끝을 빨리 끊는 S3-33 문제가 되살아난다. 단 `minSpeechMs`는 발화가 끝날 때까지 낮은 값을 유지한 뒤 복원한다. 그래서 `setMode`는 `confirmed` 플래그를 둔 3상태(재생 / 끼어든 발화 중 / 평상시)를 가진다. 이는 `setMode`를 임계값뿐 아니라 `minSpeechMs`·`redemptionMs`도 바꾸도록 `setOptions` 경로로 확장하는 일이다 **[코드 확인]**.
   - `onSpeechEnd`의 `speechEndedAt`(= 지금 − `endOfSpeechSilenceMs`)는 **실제 적용된** 무음 대기(끼어든 발화는 `barge_in_end_silence_ms`)로 계산해야 V2-NFR-08이 맞는다.
8. **끼어든 발화의 무음 대기**: 평상시와 분리한 `vad.barge_in_end_silence_ms`(3.3절 결정값 이하 **[가정]**). 끼어드는 말은 보통 짧다.

설정 추가: `client-defaults.json`의 `vad`에 `probe_threshold`, `probe_frames`, `probe_timeout_ms`, `confirm_window_ms`, `confirm_ratio`, `playback_min_speech_ms`, `barge_in_end_silence_ms`, `duck_gain`, `fade_ms`; 기존 `playback_speech_threshold`·`playback_silence_threshold` 값 변경. 서버 검증(`client_config.py`)을 함께 고친다.

### 4.3 알림음과 자기 소리 (V2-FR-13)

- `enterListening`은 끼어들기·이어 말하기로 들어올 때 `listen` 알림음을 내지 않는다. 일반 듣기 진입(턴 종료, 쉬기 복귀)은 그대로 낸다.
- 짧은 알림음(0.5초 이하) 재생 구간에는 confirm 조건을 한 단계 강화한다(`confirm_ratio` 상향) **[가정]**. 검색 안내 음성은 V1처럼 `playback` 모드로 두되 4.2절의 낮춘 값을 쓴다.
- 스피커 사용은 지원하지 않는다. 출력 장치 종류를 알 수 있는 브라우저에서만 설정 화면에 안내한다(V2-FR-19).

### 4.4 정리 대기 (V2-FR-15)

- **일반 끼어들기**: 확정 즉시 `cancelTurn`(취소 API)을 보내 CLI와 합성을 멈춘다. 재생 정지는 취소 응답을 기다리지 않는다. 실패하면 재시도 2회 뒤 기기에 보관했다가 연결되면 다시 보낸다(4.7절). 새 턴 요청에는 취소 정보를 싣지 않는다(취소 API가 `last_played`·`played_ratio`·`reason`을 받는다).
- **`await cancelling` 정책**: V1의 모든 `runTurn`은 새 턴을 보내기 전에 진행 중인 취소를 기다린다. 서버가 취소 진행 중인 세션의 새 턴을 기다려 주는 변경은 M2이므로 **M1에서는 모든 종류의 턴이 취소 완료를 기다린다.** M2부터는 음성 `new` 턴만 기다리지 않고, 글 턴은 계속 기다린다(`client-contract.md`의 "취소 API를 부른 뒤 글을 보낸다"와 일치). 그때 음성 `new` 턴이 `turn_in_progress`를 받으면(서버 대기 한계 10초 초과, 도구 실행 중, 취소 재시도·지연) 끼어든 발화가 사라지지 않도록 짧게 재시도하거나(글 턴의 `TEXT_BUSY_RETRIES`와 같은 방식) 오프라인 큐에 보관한다. V1의 `failedBeforeTurn`은 글 턴만 재시도한다.
- **큐 뒷말 즉시 전송 경로**는 M1부터 취소 응답을 기다린 뒤 새 턴을 보낸다. 뒷말이 이미 보관돼 있어 추가 지연이 작고, 취소와 새 턴이 같은 순간에 나가는 경합이 없다. 서버의 "취소 진행 중" 표시를 `cancel_turn`의 첫 `await` 앞에서 동기적으로 세우는 것은 일반 끼어들기에서 취소 재시도·지연이 새 턴과 겹칠 때를 줄이는 최선 노력일 뿐이다(FastAPI가 라우트 호출 전에 하는 의존성 해결·본문 파싱 구간은 표시보다 앞서 있다). 최종 방어선은 클라이언트의 재시도·보관이다.
- **병합**: 3.3절(큐 뒷말 즉시 전송).
- **취소 순서**: 연결을 먼저 닫지 않고 `cancel` API를 먼저 보낸다(CLI kill 회피, 3.3절 6번).
- `cancel_wait_ms`와 `cli_restarted`를 M0에서 먼저 재고, 일반 끼어들기에서 취소 대기가 0에 가까우면 이 요구사항의 범위는 CLI 재기동 회피와 네트워크 불량 경로로 줄인다(결정 X12, plan.md 결정 게이트).

### 4.5 들은 만큼 기록 (V2-FR-16)

- 취소 API에 선택 필드 `played_ratio`(재생 중이던 문장 `last_played + 1`의 재생 비율 0~1, 모르면 생략)를 더한다. 이전 클라이언트와 호환된다.
- **보수적 계산**: TTS 길이는 글자 수에 비례하지 않는다(쉼표·마침표 휴지, 숫자·영문, 말 속도, 문장 앞뒤 무음). 오차가 "더 들은 것으로" 나면 못 들은 핵심을 다시 말하지 않게 되므로 못 들은 쪽으로 기운다.
  - 클라이언트: `ratio = (재생 경과 − outputLatency − fade_ms) / 문장 길이`로 줄인다.
  - 서버: `ratio`에 비례한 글자 위치에서 **어절 경계로 내림**하고, 가능하면 직전 쉼표·절 경계로 한 번 더 내린다. 모호하면(문장 길이를 모르는 등) 해당 문장 전체를 못 들은 것으로 본다.
- 서버는 `last_played`번 문장까지와 위에서 가늠한 부분을 "들은 부분"으로 `reply`에 남기고, 나머지를 `turn.interrupted_unheard`로 저장한다(마이그레이션).
- 인사말은 자르지 않는다. 인사말 중 끼어든 경우는 4.7절.
- 클라이언트의 말풍선도 같은 기준으로 자른다(대화 리듀서 `interrupt`).

### 4.6 끊긴 뒤 이어짐 (V2-FR-17)

결정: 못 들은 핵심을 먼저 다시 말한 뒤 끼어든 말에 답한다.

- 서버가 다음 턴 프롬프트에 (1) 들은 부분, (2) 못 들은 부분, (3) 취소된 턴에서 이미 실행된 도구 호출 요약을 준다. `persona/rules.py`(앱 동작 규칙, 캐릭터와 무관)의 `heard_note`를 확장한다. V1의 `_heard_note(heard)`는 들은 문장만 받고 나머지 문장(`sentences[keep:]`)을 버리므로 시그니처를 `(heard, unheard)`로 바꾼다. 이 규칙은 `reason == barge_in`일 때의 안내이며, 일반 끼어들기에서 `last_played = -1`이면 V1의 `INTERRUPTED_NOTHING`("하나도 듣지 못했다 … 필요하면 짧게 다시 말한다")을 **대체**한다(더 강하게 "못 들은 핵심을 먼저 다시 말한다"). `reason == continued`이면 3.3절의 `CONTINUED_UTTERANCE`를 쓴다. 스냅샷(`UPDATE_SNAPSHOTS`) 대상이다.
- 규칙 문구(초안): "사용자가 네 말 도중에 끼어들었다. 사용자가 듣지 못한 부분 중 핵심만 먼저 한 문장 안팎으로 짧게 다시 말한 다음, 사용자의 말에 답하라. 이미 들려준 내용은 되풀이하지 마라. 이미 실행된 도구(메일, 메모 저장 등)는 다시 실행하지 말고 결과만 말하라. 다시 말할 때 추임새('음', '네')로 시작하지 마라." 말투는 페르소나 YAML이 입힌다. 프롬프트를 바꾸면 `UPDATE_SNAPSHOTS=1`로 스냅샷을 갱신하고 차이를 검토한다.
- 예외 **[가정, X8]**: 끼어든 말이 "응", "알겠어" 같은 짧은 호응뿐이면 다시 말하지 않고 바로 이어서 말한다.
- 길이 상한: 다시 말하기는 1문장 안팎.
- 평가: `persona_eval`을 확장한 끼어들기 시나리오 20개(문장 중간 끊김, 문장 끝 끊김, 호응, 새 질문, 연속 끼어들기, 도구 호출 뒤 끼어들기)로 V2-NFR-10을 잰다.

### 4.7 엣지케이스와 상태별 규칙 (V2-FR-20)

**상태별 처리**

| 현재 상태 | 사용자 말 시작 | 소리 처리 | 서버 | 비고 |
|---|---|---|---|---|
| `speaking`(답변 재생) | probe: duck, confirm: 페이드 정지 | 4.2절 | `cancelTurn`(취소 API, `last_played`·`played_ratio`) | 일반 끼어들기 |
| `speaking`(맞장구 뒤 첫 문장 재생) | 같음 | 같음 | `last_played` 기준 | 맞장구는 문장 번호에 포함하지 않음 |
| `processing`(첫 `sentence` 이벤트 전) | 말하는 동안 `userSpeaking` 갱신 | 맞장구 재생 중이면 즉시 정지 | 취소 안 함, 말이 끝나면 V1 큐에 보관하고 첫 `sentence` 도착 때 취소·전송(3.3절) | 이어 말하기. `speaking`으로 넘어간 뒤의 `speech_end`는 병합하지 않고 V1 큐 동작 |
| `processing`, 검색 안내(`tool.notice`) 재생 중 | probe/confirm은 `speaking`과 같게 | 안내 음성 정지 | 취소 안 함, V1 큐에 보관하고 첫 `sentence` 도착 때 취소·전송(3.3절) | 검색 안내 중에도 이어 말하기 감도는 4.2절 값을 쓴다. 서버가 이미 웹 검색을 시작했을 수 있어 취소가 검색을 버리게 된다(구독 사용량 비용이 큼) |
| `speaking`, 인사말(`greeting`) 재생 중(`session_started`에서 바로 `speaking`) | 일반 끼어들기 | 정지 | `cancelTurn`이 인사말 id로 나가도 서버는 자르지 않음(인사말은 `seq 0`). `heard_note` 없음 | 규칙: 제니는 인사말을 되풀이하지 않고 바로 사용자 말에 답한다 |

**엣지케이스**

- **연속 끼어들기**: 다시 말하기 중 또 끼어들면 재설명을 반복하지 않는다. 서버는 못 들은 부분을 턴마다 덮어쓰지 않고 누적하되(상한 약 3문장 분량) 새 답변이 시작되면 이전 못 들은 부분은 한 번만 언급한다. V1의 `runtime.heard_note`는 단일 문자열이고 최신 답변일 때만 갱신되므로 목록 필드로 바꿔야 한다. 이 값은 메모리에만 있어 서버가 재시작되면 사라진다(알려진 한계, DB의 `turn.interrupted_unheard`로 복원할 수 있으면 복원).
- **도구 실행 중/뒤 끼어들기**: 4.6절 규칙. 취소된 턴의 도구 호출 요약을 안내에 넣는다.
- **쉬기·끝내기 요청이 걸린 턴**: 서버는 턴이 정상 종료되는 즉시 `pop_requested_status`로 요청을 꺼내 반영한다(끝내기면 정리·일지 추출이 바로 시작). 이는 서버가 `done`을 보내기 전, 클라이언트가 문장을 재생하는 중에 일어나므로 "끝낼게요" 재생 중 끼어들 때 서버 세션은 이미 `ended`일 수 있다.
  - `paused`: 다음 사용자 턴이 세션을 다시 `active`로 되돌리므로 자연히 철회된다.
  - `ended`: **철회를 지원하지 않는다.** 끼어들어도 종료는 유지하고, 클라이언트는 서버 상태를 따라 정리로 가며, 필요하면 V1의 대화 다시 열기(`reopen_session`)로 이어 간다. 끝내기 반영을 재생 종료 확인까지 미루는 안은 변경이 커서 이번 범위에서 제외한다 **[가정, X10]**.
  - 클라이언트 상태(`listening`)와 서버 세션 상태가 어긋나지 않는지 서버 테스트와 전이 표 사례로 확인한다.
- **네트워크 끊김 중 끼어들기**: 취소 요청이 실패하면 기기에 `cancel`(턴 id, `last_played`, `played_ratio`, `reason`)을 보관했다가 연결되면 취소 API로 다시 보낸다(서버는 이미 연결이 끊겨 CLI를 멈췄을 수 있어 멱등이다). 오프라인 안내(`speakOfflineNotice`, 기기 TTS) 재생 중 사용자 말이 시작되면 안내를 멈추고 듣는다. 전이 표 사례를 더한다.
- **글 입력으로 끼어들기**: 제니가 말하는 중 글을 입력해 보내면 재생을 멈추고(페이드) 취소 API(`last_played`·`played_ratio`)를 부른 뒤 글을 보낸다. 맞장구는 글 입력 턴에 적용하지 않는다.
- **쉬기·끝내기 음성 명령**: 이런 명령에도 맞장구가 나가고 직후 마무리 멘트가 이어진다. 의도된 동작이다.
- **취소 실패**: 컨트롤러가 오류를 삼키지 않고 재시도하며 `barge_in_event`에 결과를 남긴다.

## 5. 맞장구 설계 (V2-FR-06)

맞장구는 **끝 판정 뒤 첫 답변 소리가 나기 전의 공백을 메우는 제니의 짧은 소리**("음~", "네")다. 사용자 말 도중의 추임새(백채널)가 아니다.

- **언제**: 클라이언트가 턴 요청을 서버로 보낸 시각을 기준으로 `ack_delay_ms`(기본 300 **[가정]**) 안에 첫 문장 소리가 오지 않으면 재생한다. 기준을 "끝 판정"이 아니라 "요청 전송 시각"으로 둔다. 끝 판정은 이미 실제 말 끝 + 무음 대기(0.8~1.8초)다. 맞장구는 실제 말 끝 + 무음 대기(0.8~1.0) + 전송(약 0.2) + `ack_delay_ms`(0.3) ≈ 1.3~1.5초에 나온다(V2-NFR-02는 1.5초 이내). 무음 대기가 1.0초를 넘거나 맞장구의 시작 지연(디코드, 출력 지연)이 더해지면 NFR-02는 달성되지 않는다. 첫 답변은 3.4절 예산상 대개 3.7초 이후에 오므로 **맞장구는 거의 항상 재생된다**고 본다. "빨리 오면 건너뜀"은 예외 경로다.
- **재생하지 않는 경우**: 말이 `ack_min_speech_ms`(기본 1000 **[가정]**) 미만으로 짧은 대답("네", "응"), 글 입력 턴, 타이머가 만료될 때 첫 문장이 이미 재생 대기열에 들어가 있는 경우(디코드 중이어도), 검색 안내(`tool.notice`)가 먼저 도착한 경우(안내가 맞장구를 대체). **`no_speech`는 맞장구를 막지 못한다**: 맞장구는 요청 전송 + 0.3초에 나가는데 `no_speech`는 인식이 끝나는 약 1.1~1.5초 뒤에야 알 수 있다. 바람·숨소리로 `speech_end`가 나면 맞장구가 한 번 나가고 답이 없다. 줄이는 수단은 `ack_min_speech_ms`와 발화 에너지 조건뿐이다. 인식 결과(`transcript` 이벤트) 뒤로 옮기면 NFR-02와 충돌하므로 택하지 않는다.
- **음원**: 캐릭터의 목소리이므로 `shared/sounds`에 고정하지 않는다. 문구는 페르소나 YAML(`voice.ack_phrases`, 처음 2~3개, 같은 소리 연속 금지, X9), 서버가 현재 보이스로 합성해 캐시하고(`GET /api/voice/acks`) 웹이 세션 시작 때 받아 둔다. 설정 화면에서 보이스를 바꾸면(`PUT /api/profile`) 캐시를 다시 만들고, 웹은 다음 세션 시작 때 새로 받는다.
- **재생 구조**: 맞장구는 `AudioOutput` 재생 대기열의 **문장 번호 없는 항목**(V1의 인사말·검색 안내·마무리 멘트와 같은 종류)으로 넣되, 항목에 `kind`(`ack`·`notice`·`sentence` 등)를 붙인다.
  - 큐는 선입선출이므로 맞장구를 먼저 넣은 뒤에만 첫 문장이 뒤에 붙는다(위 "재생하지 않는 경우"가 그 반대 순서를 막는다). 맞장구가 끝나기 전에 첫 문장이 도착하면 맞장구가 끝난 뒤 이어서 재생된다(끊거나 겹치지 않는다).
  - 번호 없는 항목의 종료를 알리는 `AudioOutputEvent`가 V1에는 없다(`started`, `sentence_played`, `playback_idle`뿐이고 `started`는 `index`만 싣는다). `started`에 `kind`를 싣고 `item_done {kind}`를 신설하고 머신의 `ack_done`은 `kind == ack`일 때 낸다. `stopPlayback`·`fadeOutPlayback`으로 중단되면 `item_done`이 오지 않으므로 같은 명령 처리에서 `ackPlaying`을 해제한다.
  - V1의 지연 측정(`onPlaybackStarted`)은 번호 없는 첫 항목이 시작하면 `measuring`을 비우고 `notice`로 보고한다. 맞장구가 이를 소비하지 않도록 `kind == ack`는 제외한다. 맞장구는 `turn` 이벤트(인식 약 1.1~1.5초 뒤)보다 먼저 나가 보고할 턴 id가 아직 없으므로, `ack_ms`(요청 전송 대비)를 클라이언트가 보관했다가 `turn` 수신 때 해당 턴의 지연 보고에 싣는다.
  - `generation`은 V1과 같이 `stopPlayback`·`fadeOutPlayback`만 올린다. 맞장구 항목의 시작·종료는 올리지 않는다.
- **상태**: `processing`의 하위 플래그 `ackPlaying`을 둔다. 새 상태 이름은 만들지 않는다. `ackPlaying`은 `item_done`, `stopPlayback`, `fadeOutPlayback`뿐 아니라 **`enterListening`을 부르는 모든 경로**(턴 오류, `no_speech`, `queue_send_failed` 등)에서 비운다. 맞장구가 듣기 상태에서 계속 재생되고 VAD 모드가 남는 것을 막기 위해서다. 맞장구 항목이 있는 채 `enterListening`이면 `stopPlayback`도 함께 낸다.
- **맞장구가 첫 답변을 늦추지 않게**: 첫 문장이 맞장구 재생 시작 후 `ack_overlap_max_ms`(기본 300 **[가정]**) 이내에 도착하면 맞장구를 페이드아웃하고 바로 첫 문장을 재생한다. 그 이상 재생된 뒤면 끝난 뒤 이어서 재생한다. 첫 답변이 3.7초 이후라는 가정이 빗나가는 빠른 턴에서 맞장구가 답변 시간 단축에 반하지 않게 하는 규칙이다.
- **M1 최소 안전장치**: `playAck` 시작과 `ack_done`·중단에 짝지어 `setVadMode playback`·`normal`을 내는 것으로 표현한다(`tool.notice`와 같은 방식). 단점: 맞장구가 나가는 약 0.5~1초 동안 이어 말하기 감도가 재생 모드 값(0.8)으로 떨어진다. 병합이 노리는 바로 그 구간이므로 M2에서 4.2절 값으로 갱신한다.
- **충돌과 규칙**

  | 상황 | 규칙 |
  |---|---|
  | 맞장구 재생 중 사용자 발화 시작(상태가 아직 `processing`) | 즉시 멈추고(`stopPlayback`) 듣는다. 서버에는 취소를 보내지 않는다(맞장구는 서버가 모르는 소리). 말이 끝나면 V1 큐 보관, 첫 `sentence` 때 3.3절 규칙 |
  | 맞장구가 끝나기 전에 첫 문장 도착(상태가 `speaking`으로 넘어감) | 맞장구가 끝난 뒤 이어서 재생한다 |
  | 첫 문장이 이미 도착한 뒤 사용자 말이 시작 | 일반 끼어들기이며 `cancelTurn`을 보낸다. 맞장구는 문장 번호가 없으므로 `lastPlayed`에 영향을 주지 않는다 |
  | 맞장구 직후 본문이 "음~"으로 시작 | 서버는 맞장구가 재생됐는지 모른다. `rules.py`에 "답변을 추임새로 시작하지 마라" 한 줄을 넣고 톤 평가에 포함한다 |
  | 검색 턴 | `tool.notice`(검색 안내)가 오면 맞장구를 건너뛰고, 이미 맞장구가 나가는 중이면 안내를 뒤에 잇는다 |
  | 설정 | 설정 화면에서 끌 수 있다(`user_profile`에 불리언, 마이그레이션) |
- 맞장구 효과는 `ack_ms`(첫 반응)로 따로 측정하고, 끼어들기 평가에서는 맞장구 켠 경우와 끈 경우를 둘 다 돈다.
- SSE 규약에 이벤트를 늘리지 않는다. 맞장구는 클라이언트 단독 동작이고, `ack_ms`는 기존 클라이언트 지연 보고에 필드로 더한다.

## 6. 측정과 평가

| 지표 | 정의 | 측정 방법 | 목표 |
|---|---|---|---|
| 첫 답변·첫 반응 지연 | 3.2절 | 3.2절 평가 스크립트(브라우저 구동), 30턴 이상 | V2-NFR-01, 02 |
| 체감 정지·완전 정지 | 실제 발성 시작(평가 wav의 알려진 시각) → 볼륨 절반 이하 / 소리 정지 | 아래 "주입 방식". 클라이언트가 VAD probe·confirm·duck·`source.stop` 시각을 기록하고 정답 시각과 차이를 계산 | NFR-03, 04 |
| 오탐 | 사용자 발화 없이 끼어들기가 난 횟수 | 제니 음성(녹음 고정 파일, 아래)을 -20dB 안팎으로 마이크 스트림에 섞어 10분. 알림음·검색 안내·맞장구 포함 | NFR-05 |
| 누락 | 끼어들었는데 1초 안에 안 멈춘 비율 | 크기·잡음비를 바꾼 합성 발화 | NFR-06 |
| 끼어든 말 인식 | 첫 3어절 정확도 | 같은 wav를 재생 중 끼어든 경우와 재생 없이 보낸 경우로 비교(STT는 실제 OpenAI, 사용량 보고) | NFR-07 |
| 끼어든 뒤 응답 지연 | 끼어든 말의 실제 말 끝 → 첫 소리 | `turn_latency` + `cancel_wait_ms` | NFR-08 |
| 기록 일관성 | 서버 기록 vs 실제 들은 문장·부분 | 합성 시나리오(문장 번호·재생 위치를 알고 끊음). 문장 단위 100%, 부분은 ±1어절 | NFR-09 |
| 맥락 정합 | 4.6절 시나리오 평가 | `persona_eval` 확장(실제 CLI) | NFR-10 |
| 큐 뒷말 즉시 전송 | 병합 적중률 = 첫 `sentence` 시점 `queued > 0`인 턴 비율, 뒷말이 앞 턴의 `turn` 이벤트 전/후 어느 쪽에서 끝나는지, 뒷말 응답 지연, 병합 정확도(1턴 응답·안내 적용) | 이어 말하기 시나리오(가짜 마이크 시각 주입) + 현장 `merged` 비율 | M1 완료 기준, X11 |
| 취소 시 CLI 재기동 | `cli_restarted` 비율과 재기동 지연 | 취소 순서 변경 전후 비교 | V2-NFR-08 |

**주입 방식과 한계**

- E2E의 `--use-file-for-fake-audio-capture`는 시작부터 wav를 되풀이하므로 시각을 못 정한다(handoff 2장). 평가용으로는 `page.addInitScript`로 `getUserMedia`를 덮어써 `AudioContext.createMediaStreamDestination`의 스트림을 돌려주면 임의 시각에 발화를 넣고, 제니 출력을 감쇠해 같은 스트림에 섞어 되먹임도 만들 수 있다.
- 이 방식은 브라우저 `echoCancellation`을 우회하고 실제 이어폰 누설(지연·필터)을 모사하지 못한다. **임계값 감도 실험이지 에코 제거 검증이 아니다.**
- 헤드리스에서는 `outputLatency`가 0이고 실제 소리가 나지 않아, 정지 지연은 `GainNode`·`AnalyserNode` 값 기준의 소프트웨어 경로만 잰다. 블루투스 출력 지연은 폰 실기에서 따로 잰다(외부 녹음 등).
- 되먹임용 제니 음성은 실제 TTS(`nova`)로 한 번 만든 고정 파일을 쓴다 **[가정]**(E2E 서버의 가짜 TTS는 실제 음성이 아니다). 크기가 작은 문장 몇 개만 `server/tests/fixtures/`에 둔다.
- 현장 `barge_in_event`의 오탐 의심(끼어들기 직후 `no_speech`나 아주 짧은 인식)은 근사이므로, 설정 화면에 사용자가 직접 표시하는 "방금 오작동" 버튼을 후보로 둔다 **[가정]**.
- 이어폰 변형별(유선, 블루투스 A2DP, 블루투스 HFP — 마이크를 쓰면 통화 프로필로 바뀌어 출력 품질·지연이 달라질 수 있다) 측정 표를 실기 단계에서 채운다.
- 기준선(V1 현재 코드)은 M0에서 위 방법으로 먼저 재고 `docs/eval/barge-in-<날짜>.md`에 남긴다. 수치 목표의 **[가정]**은 이 기준선으로 확정한다.

## 7. 데이터·API·상태 머신 변경

모델을 바꾸면 같은 커밋에 Alembic 마이그레이션을 만든다. 번호는 문서에 박지 않고 작업 시작 때 `alembic heads`로 현재 head를 확인한다(V1 마지막은 0015).

### 데이터

| 변경 | 내용 | 마일스톤 |
|---|---|---|
| `turn_latency` 컬럼 | `cancel_wait_ms`, `cli_restarted`, `ack_ms`, `merged`, `queued_at_first_sentence`, `second_utterance_phase`(`before_turn`·`after_turn`), `cancelled_turn_id`. 기존 컬럼은 유지. 마이그레이션 충돌을 피하려고 컬럼은 M0에서 한 번에 만들고 값은 M0·M1에서 기록한다 | M0 |
| `turn.spoken_sentences` | 서버가 실제 내보낸 문장 목록(JSON, 기존 행 NULL) | M1 |
| `turn.interrupted_unheard` | 끼어들기로 못 들은 부분 | M2 |
| `barge_in_event` 신규 | session_id, 끼어든 턴 id, 시각, probe→confirm ms, 정지 ms, `played_ratio`, 결과(`real`·`suspected_false`·`probe_reverted`·`user_marked_false`, CHECK 없는 문자열), 다음 턴 id | M0·M2 |
| `user_profile` | 맞장구 사용 불리언 | M1 |

### API

| 엔드포인트 | 변경 | 마일스톤 |
|---|---|---|
| `POST /api/sessions/{id}/turns/{turn_id}/cancel` | 선택 필드 `reason`(`barge_in`·`continued`, `continued`면 `INTERRUPTED_NOTHING` 대신 `CONTINUED_UTTERANCE` 안내)은 M1, 선택 필드 `played_ratio`는 M2 | M1·M2 |
| 턴 요청(일반 끼어들기, 취소 진행 중) | `TurnBusy` 대신 취소 완료 이벤트를 상한까지 대기 | M2 |
| (조건부 M1b) `POST …/turns/audio` | 선택 쿼리 `replaces_turn_id` — 채택 시 3.3절 조건부 안의 제약대로 상세화 | M1b |
| `GET /api/voice/acks` | 신규, 현재 보이스의 맞장구 오디오 | M1 |
| `POST /api/barge-in-events` | 신규, 기기에 모은 이벤트 배치 업로드 | M0·M2 |
| `POST /api/sessions/{id}/turns/{turn_id}/latency` | `LatencyReport`에 선택 필드 `ack_ms`(요청 시작 대비 ms), `merged`, `queued_at_first_sentence`, `second_utterance_phase`(클라이언트가 병합 여부와 뒷말 시점을 보고) | M1 |
| `GET /api/latency` | 요약에 `cancel_wait_ms`, `ack_ms` | M0·M1 |
| `GET /api/profile` | `client.vad`에 4.2절 신규 값. 별도 그룹 `client.turn`에 병합(`merge_min_speech_ms`, `cancel_abort_wait_ms`)·맞장구(`ack_delay_ms`, `ack_min_speech_ms`, `ack_overlap_max_ms`) 설정 **[가정]** | M1·M2 |
| 인증·Origin 검사 | 9장 | M3 |

서버 API를 바꾸면 `npm run gen:api`로 `web/src/api/schema.d.ts`를 갱신하고, `client-contract.md`를 코드와 맞춘다.

### 상태 머신 (`sessionMachine.ts`, `shared/fixtures/transitions.json`)

- 이벤트 추가: `speech_probe`, `speech_misfire`(타이머 되돌림), `speech_misfire_after_confirm`, `ack_done`. `speech_end`에 `speechMs`를 싣는다. 상태에 `queuedSpeechMs`를 더하고 `queueUtterance` 명령과 `queue_sent` 이벤트가 이를 싣거나 갱신한다.
- 명령 추가: `duckPlayback`, `unduckPlayback`, `fadeOutPlayback`, `playAck`. `cancelTurn`에 재생 비율과 `reason`(`barge_in`·`continued`)을 싣는다. `fadeOutPlayback`과 `stopPlayback`은 둘 다 `generation`을 올려 이후 재생 이벤트를 막는다.
- 변경: 끼어들기·이어 말하기 경로의 `enterListening`은 `listen` 알림음을 내지 않는다. `processing`의 `sentence` 처리: V1의 `userSpeaking` 분기 **뒤에** `queued == 1`이고 `queuedSpeechMs ≥ merge_min_speech_ms`이면 첫 문장을 재생하지 않고 `stopPlayback`·`ackPlaying` 해제와 `cancelTurn(reason: continued)`를 낸 뒤, 취소 응답을 기다려 큐의 뒷말을 보낸다(3.3절). `processing`의 하위 플래그 `ackPlaying`.
- 전이 표(V1 사례 30개)에 3.3·4.7절 사례를 더하고, 의도적으로 바뀌는 사례(끼어들기 알림음, 병합, `speech_end` 형식)는 같은 커밋에서 고친다. 허용된 변경이며 회귀가 아니다.

### 컨트롤러·플랫폼 변경 (`voiceController.ts`, `audioInput.ts`, `audioOutput.ts`)

- `AudioInput`: 재생 모드 규칙(4.2절 7항), `setMode` 3상태, 발화 시작 모드 플래그와 앞 잡음 잘라내기, 적용된 무음 대기로 `speechEndedAt` 계산, 음성 프레임 수 기반 `speechMs`.
- `AudioOutput`: 마스터 `GainNode`(ducking·페이드, 페이드 종료까지 `finish()` 지연), `playedRatio()`, 항목 `kind`와 `item_done`, `started` 이벤트에 `kind`(5장).
- 컨트롤러: 취소 순서 변경(취소 API 먼저, 응답 또는 `cancel_abort_wait_ms` 뒤 연결 닫기, 3.3절 6번)과 이에 따른 턴별 `cancelled` 플래그(핸들러 맨 앞에서 `aborted || cancelled`이면 이벤트 버림), 취소 시점에 잡아 둔 이전 `AbortController`로 지연 close, 맞장구 타이머와 `ack_ms` 보관, 취소 API 재시도와 기기 보관, `tap`·끝내기·정리·`idle_timeout` 때 보관된 뒷말은 V1 큐 규칙을 따름.
- 웹 설정: `ClientVadConfig`·`VadSettings`·`vadSettingsFrom`에 4.2절의 신규 키를 추가하고 서버 `VadConfig`(`extra="forbid"`)에도 같은 키를 추가한다. 병합·맞장구 값은 `client.vad`와 별도 키 그룹(`client.turn`) **[가정]**으로 두며, 이 그룹은 `client-defaults.json`·서버 `ClientConfig`(최상위 `extra` 설정 확인)에 새로 만들고 `npm run gen:api`로 스키마를 갱신한다. `QueuedUtterance`에 선택 필드 `speechMs?`를 더한다(3.3절).
- **클라이언트 규약(`client-contract.md`) 개정 항목**(마일스톤별로 같은 커밋에서 고친다)
  - M1: 끼어들기 API 설명의 "스트림도 끊는다" 문장(취소 API 먼저, 응답 뒤 지연 close, 취소된 턴의 이벤트는 버림), `reason`, `cancelTurn` 명령 인자와 실행 설명, 이어 말하기에 큐 뒷말 즉시 전송 추가, 큐 항목의 `speechMs`, `speech_end`의 `speechMs`.
  - M2: `played_ratio`, 취소 중인 세션의 새 턴 대기("새 턴은 `turn_in_progress`가 될 수 있다" 문장), 글 입력의 "끼어든 직후에는 `cancelTurn` 요청이 끝난 뒤 보내고" 부분, 상태 머신의 새 이벤트·명령(`speech_probe`, `duckPlayback` 등).

## 8. 마일스톤

| 마일스톤 | 범위 | 선행 | 완료 기준 |
|---|---|---|---|
| **M0 기준선** | V1 마무리(S3-17, 종료 점검, 문서 일치) 포함 가정(X5), 지연 평가 스크립트, 끼어들기 평가 장치(정지 지연·오탐·누락·인식), `turn_latency`·`barge_in_event` 계측, `cancel_wait_ms` 측정, 저장소 `CLAUDE.md` 커밋 규칙 정리(X7, 자동 커밋·푸시로 복원됨) | - | 현재 코드의 지연·끼어들기 기준선 수치가 문서에 기록됨. V1 테스트 전체 통과 |
| **M1 답변 시간 단축** | 큐 뒷말 즉시 전송, 취소 순서 변경(CLI kill 회피), 서버 턴 경로, 무음 단축 비교, 첫 문장 분할과 `spoken_sentences`, 맞장구(최소 안전장치 포함), 스트리밍 TTS·선업로드 측정, 병합 지표 측정(첫 `sentence` 시점 `queued > 0` 비율, 뒷말 종료 시점 `turn` 전/후) | M0 | NFR-01·02 달성 또는 X1 결정. 이어 말하기 E2E 3회 연속 통과. 큐 뒷말 즉시 전송 정확도(1턴 응답, 안내 문구 적용). 톤 평가 18/20. 병합 지표 기록 후 M1b 채택 여부 결정(X11) |
| **M1b 뒷말 이어 붙이기**(조건부) | 3.3절 조건부 안 | M1, X11 | 채택 시 별도 완료 기준을 spec에 추가하고 시작 |
| **M2 자연스러운 끼어들기** | 두 단계 감지, 임계값·모드 확장, 알림음, 정리 대기, 들은 만큼 기록, 끊긴 뒤 이어짐 규칙, 엣지케이스, 평가 | M1 | NFR-03~10 달성(소프트웨어 경로), 폰 실기 측정 기록, 전이 표·서버 테스트 통과 |
| **M3 보안(최소)** | 인증, Origin·Content-Type 검사, 로그인 화면, 테스트·E2E 인증 주입 | M2 (X6에서 앞당길 수 있음) | 인증 없는 요청 401, 허용 밖 Origin 403, 기존 테스트 통과, 폰 로그인 유지 |

각 마일스톤은 구현 → 검증(Playwright 실구동, 실제 CLI·음성 확인 1회) → 서브에이전트 diff 리뷰 → 자동 커밋·푸시 → 마일스톤 종료 사용자 확인 순서다.

## 9. 보안(최소) 설계 (V2-FR-21~23, M3)

두 초점이 끝난 뒤 최소 범위로만 한다.

- **전제**: 서버는 계속 Tailscale Serve(tailnet 안)로만 연다. 인증은 두 번째 방어선이다.
- **인증 [가정]**: `.env`의 `API_TOKEN`(32바이트 이상). 웹 토큰 입력 → `POST /api/auth/login` → `HttpOnly; Secure; SameSite=Strict` 쿠키(만료 90일 **[가정]**). 토큰 비교는 상수 시간. 로그인 실패는 횟수 제한. 토큰은 로그에 남기지 않는다.
- **요청 검사**: 변경 요청의 `Origin`을 허용 목록과 대조하고 `Content-Type`을 확인한다. **턴·음성 턴 SSE는 POST**이고 오디오 업로드 본문은 오디오 바이트 그대로(`audio/webm`·`wav`·`mpeg`·`mp4`·`ogg`)이므로 검사 대상이다. GET은 쿠키만 검사한다.
- **제외**: `/api/health`, 정적 파일, 내부 MCP(`/internal/mcp/`는 `/api` 밖, V1의 대화별 토큰 유지).
- **개발·테스트**: 로컬 http에서는 `COOKIE_SECURE`를 끄고, Vite 프록시 Origin을 `ALLOWED_ORIGINS`에 넣는다. 테스트 `client` 픽스처, `npm run e2e` 서버, `./run.sh --fake`·`--phone`에 인증 설정과 토큰 주입을 만든다. 폰(A35) 로그인·홈 화면 설치·재시작을 확인한다.
- 세션별 `persona_id` 기록은 이번 범위에서 뺀다(후순위).

## 10. 결정 사항

| ID | 결정 | 필요 시점 | 상태 | 내용·제안 |
|---|---|---|---|---|
| X1 | 속도 기준: 엄격한 3초 vs 첫 반응 1.5초 + 첫 답변 4.5초 | M1 측정 후 | 대기 | 3.4절 예산상 엄격한 3초는 어렵다. 완화안을 기본 후보로 |
| X2 | 맞장구 허용 | - | **결정** | 허용(2026-10-19). 설정으로 끌 수 있게. M1에 최소 안전장치와 함께 넣음 |
| X3 | 스피커 지원 | - | **결정** | 지원 안 함. 이어폰 전제(2026-10-19) |
| X4 | 끼어든 뒤 제니의 행동 | - | **결정** | 못 들은 핵심을 먼저 다시 말한 뒤 답함(2026-10-19) |
| X5 | V1 3단계 마무리(S3-17, 종료 점검)를 M0에 포함 | 지금 | 대기 | 포함으로 가정 |
| X6 | 인증(M3)을 두 초점 뒤에 둠 | 지금 | 대기 | 뒤로 가정. 앞당기려면 M0 직후 |
| X7 | V2 중 커밋 방식 | - | **결정** | 서브에이전트 diff 리뷰 후 자동 커밋·푸시(저장소 `CLAUDE.md` 규칙). 2026-10-19에는 "리뷰 후 사용자 확인"으로 정했다가 2026-10-20 사용자 지시로 자동 커밋 허용으로 복원했다 |
| X8 | 짧은 호응("응")으로 끼어들면 못 들은 핵심을 다시 말하지 않는 예외 | M2 중, 끊긴 뒤 이어짐 작업 전 | 대기 | 예외를 두는 쪽을 제안 |
| X9 | 맞장구 문구 목록·빈도 | M1 중, 맞장구 서버 작업 전 | 대기 | 처음 2~3개, 같은 소리 연속 금지, 길이 1초 이내 |
| X10 | 끝내기·쉬기 요청이 걸린 턴에서 끼어들기 | M2 중, 엣지케이스 작업 전 | 대기 | `paused`는 자연 철회, `ended`는 철회 미지원(끼어들어도 종료 유지, 다시 열기로 이어 감)을 제안. 철회를 지원하려면 끝내기 반영을 재생 종료 확인까지 미뤄야 해 이번 범위에서 제외 |
| X11 | 뒷말만 보내 이어 붙이기(M1b, V2-FR-09) 채택 여부 | M1 측정 후 | 대기 | 기본은 채택하지 않음. 첫 `sentence` 시점 `queued > 0` 비율과 뒷말 응답 지연이 의미 있을 때만 채택 |

## 11. 리스크

| 리스크 | 영향 | 대응 |
|---|---|---|
| 지연 예산 합계(약 3.7~5.0초)가 3초를 넘는다 | V2-NFR-01 미달 | 맞장구로 첫 반응을 보완, X1에서 기준 재결정 |
| 무음 단축이 S3-33(긴 발화 끊김)을 되살린다 | 문장이 잘려 오해 | 큐 뒷말 즉시 전송을 먼저, 이어 말하기 E2E 3회 연속, 동적 방식 시험 |
| 큐 뒷말 즉시 전송에서 뒷말이 잡음이면 앞 답변만 취소됨 | 앞말이 답 없이 남음 | `merge_min_speech_ms` 조건(V1 `userSpeaking` 취소 경로와 같은 한계), 뒷말 응답 지연은 최악 약 2초 |
| 연결을 먼저 닫는 V1 취소 순서가 CLI를 kill하고 `--resume`으로 재기동 | 취소마다 1.4초 이상 지연, 부분 컨텍스트 유실 | 취소 API를 먼저 보내 정상 인터럽트하고 응답 뒤 연결을 닫음, `cli_restarted`를 M0에서 측정 |
| 병합 조건부 안(M1b)의 복잡도(매핑·제자리 수정·말풍선 교체·락 대기) | 일정·결함 | 측정으로 이득이 확인될 때만 채택(X11), 채택 시 3.3절 제약대로 상세화 |
| 병합 직후 뒷말 전송이 서버 일시 오류(`turn_in_progress` 등)로 실패하면 `queue_send_failed`로 `connected=false`가 되어 뒷말이 보관된 채 듣기로 돌아가고 `online`(30초 주기) 전까지 재시도되지 않음 | 뒷말 응답 지연(V1과 같은 동작이나 병합이 이 경로를 더 자주 탐) | 병합 경로의 서버 오류는 짧게 재시도, 지연 측정 시 이 경로 비율을 기록 |
| 재생 중 감지 기준을 낮추면 헛 끼어들기가 늘어난다 | 제니가 자꾸 멈춤 | ducking으로 영향 최소화, 프레임 연속·밀도 기준, 되먹임 실험으로 임계값 확정, 타이머 복구 |
| `onVADMisfire`를 쓸 수 없다(redemption 뒤에 발생) | ducking이 오래 안 풀림 | probe 타이머로 직접 되돌림(4.2절) |
| 문장 번호 어긋남(조기 분할 + 재분할 폴백) | 들은 문장 기록 오류 | `spoken_sentences` 저장, NFR-09 평가 |
| 들은 부분 가늠이 "더 들은 쪽"으로 틀림 | 못 들은 핵심을 다시 안 말함 | 보수적 계산(지연·페이드 차감, 어절 내림), 모호하면 못 들은 쪽 |
| 도구가 이미 실행된 턴을 끊음(메일·메모) | 중복 실행, 상태 불일치 | 4.6절 규칙, 도구 요약 전달, 끝내기는 철회 없이 종료 유지(X10) |
| 못 들은 핵심 다시 말하기가 답변을 길게 만든다 | 걸으며 듣기 피곤 | 1문장 안팎 상한, 호응 예외(X8), 톤 평가 |
| 맞장구가 사용자의 말을 가로막거나 어색 | 대화 부자연 | 짧은 말 제외, 사용자 발화 시 즉시 멈춤, 끌 수 있게, 본문 추임새 시작 금지 |
| 스트리밍 TTS가 큰 재설계 | 일정 지연 | M1에서는 측정만, 이득 0.5초 미만이면 제외 |
| 평가 장치(`getUserMedia` 덮어쓰기)가 실제 환경과 다르다 | 수치가 현장과 어긋남 | 소프트웨어 경로로 한정 명시, 폰 실기·현장 측정으로 교차 확인, 최종 기준은 실제 산책 |
| 블루투스 HFP 전환으로 출력 지연·품질 변화 | 실기에서 정지 지연이 늘어남 | 이어폰 종류별 실기 측정 표 |
| 병합·취소 증가로 구독 사용량 소모 | 한도 도달 | `GET /api/usage`로 평가 때 기록 |
| Claude CLI 지연·출력 형식 변경 | 응답 느려짐 | V1 대응(버전 고정, 파서 테스트) 유지 |
