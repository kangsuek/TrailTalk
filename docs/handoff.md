# 작업 인계 (2026-10-17, 3단계 진행 중: S3-01~S3-14 완료)

새 세션은 이 문서부터 읽는다. 작업 규칙과 명령은 [CLAUDE.md](../CLAUDE.md)에 있다. 진행 상태의 기준은 [구현 계획서](implementation-plan.md)의 진행 대시보드(2장)다. 이 문서에는 계획서·설계서에 없는 맥락만 둔다. 상태가 바뀌면 이 문서도 갱신하거나 지운다.

## 0. 새 세션 시작 프롬프트

새 세션에서 아래를 그대로 붙여 넣는다.

```text
TrailTalk 작업을 이어서 진행합니다. 먼저 docs/handoff.md를 읽고, 구현 계획서(docs/implementation-plan.md)의 진행 대시보드(2장)와 3단계 절(6장)을 확인하세요.
지금은 3단계(웹 음성 대화) 진행 중이고 S3-01~S3-14가 끝났고, PC 브라우저와 폰(Tailscale)에서 음성 대화가 됩니다. 다음 작업 후보는 handoff 1장 "다음 작업"에 있습니다.
작업 규칙: 응답은 한글, 소스 수정 전 Plan Mode로 계획 승인, 유닛 테스트에 더해 Playwright 실제 구동 검증, 커밋 전 서브에이전트 diff 리뷰, 이 저장소는 자동 커밋·push 허용, 작업 시작·끝에 계획서 상태 갱신.
주의: .env 값은 열어 보지 마세요. 포트 8000에 떠 있는 사용자 서버(실제 DB)는 건드리지 말고, 실제 구동 검증은 handoff 2장의 방법대로 다른 포트에서 하세요. 실제 Claude CLI(구독 사용량)와 OpenAI API(과금)는 필요할 때만 쓰고 쓸 때 알려 주세요.
다음 작업(handoff 1장의 순서)을 확인하고 Plan Mode로 계획을 세우세요.
```

## 1. 지금 어디까지 왔나

- **0·1·2단계 완료**(2단계는 2026-10-16 사용자 확인, 마일스톤 `5749ea3`). **3단계(웹 음성 대화) 진행 중**(진행 수치는 계획서 대시보드). PC 브라우저와 폰(`./run.sh --phone`, Tailscale HTTPS, S3-14)에서 "음성으로 대화"로 말로 대화할 수 있다.
- **3단계에서 끝낸 것**: S3-08 세션 상태 머신·S3-09 상태 전이 표(`9202e04`), S3-06 클라이언트 설정값(`2b643a9`). S3-01·S3-02·S3-03은 아래 절에 따로 적었다.
  - S3-06: `GET/PUT /api/profile`이 `client`(VAD·세션·오디오·오프라인 안내, 읽기 전용)를 준다. 서버가 시작할 때 `shared/client-defaults.json`을 `app/client_config.py`로 검증하고 틀리면 시작하지 않는다. `idle_timeout_minutes`는 서버 `IDLE_TIMEOUT_S`로 덮어쓴다. VAD 수치(0.5/0.35, 재생 중 0.8/0.65)는 시작값이라 실제 산책 측정에서 조정한다. 웹은 S3-13 컨트롤러가 `getProfile`로 받아 VAD(`vadSettingsFrom`)와 무발화 시간에 쓴다.
  - `web/src/core/sessionMachine.ts`: 이벤트 → 다음 상태 + 명령을 내는 순수 함수다. 마이크·재생·서버 호출은 하지 않는다.
  - `shared/fixtures/transitions.json`: 사례 22개. 안드로이드 테스트도 이 파일을 읽는다.
  - S3-13에서 화면에 연결했다(`web/src/screens/voiceController.ts`). 플랫폼이 지킬 약속은 규약 4절에 있다(인사말은 `session_started {turnId}`, `sentence`·`turn_done`에 턴 ID, 모든 요청은 성공·실패 이벤트로 끝냄, 큐의 말을 서버가 받으면 `queue_sent {remaining}`, 보내다 서버에 닿지 않으면 `queue_send_failed`).
- **S3-01·S3-02(`f89057b`·`ef035e2`, 완료)**: `app/voice/stt.py`·`tts.py`·`audio.py`·`openai_http.py`. 앱에서 `app.state.stt`·`app.state.tts`로 쓴다.
  - 실제 확인(2026-10-16, 크레딧 충전 뒤): `RUN_REAL_OPENAI=1 uv run pytest tests/test_voice_real.py -q -s` 통과(TTS 1회·STT 2회, webm·ogg 모두 원문과 같음). ffmpeg가 PATH에 없으면 `FFMPEG_PATH=~/.local/bin/ffmpeg`를 준다. `languages` 필드는 API가 읽는다(틀린 코드 400). 7초 발화 인식 응답은 앱 경로(`gpt-transcribe`, webm)에서 약 1.3초, 다른 모델·형식은 1.5~3초였다(WAV는 업로드가 커서 느림).
  - 보이스는 6종 샘플(`uv run python -m tests.voice_samples`, `server/data/voice-samples/`, 커밋 안 함)을 사용자가 듣고 `nova`로 골랐다. `instructions`(말투 지시)는 그대로 두었다.
  - S3-03 음성 턴도 가짜 CLI + 실제 OpenAI로 확인했다(2장 명령에 `VOICE_BACKEND=fake` 없이 `FFMPEG_PATH`를 더한다). 가짜 CLI 녹화 `web_search`는 지금 출처 규칙 이전 답변이라 `Sources:`·링크 줄까지 소리로 만든다. 실제 CLI 음성 답변에서는 마일스톤 끝 실제 확인 때 본다.
  - OpenAI TTS에는 피치가 없어 페르소나 `voice.pitch`를 지우고 `instructions`(말투 지시)를 넣었다. `gpt-4o-mini-tts`는 `speed`를 무시한다는 보고가 있어, 빠르기는 `instructions`에도 적었다.
  - TTS 전처리 `speech_text`는 음성에만 쓰고 화면 문장(`sentence.text`)은 그대로 둔다.
  - 그대로 못 보내는 업로드(ogg 등)는 WAV가 아니라 16kHz 모노 webm/opus(24kbps)로 바꾼다(업로드 크기가 응답 지연에 더해지므로). 설정은 빈 값(`KEY=`)을 없는 것으로 본다(`env_ignore_empty`).
- **S3-03 음성 턴(`bafcea9`, 완료)**: `POST /api/sessions/{id}/turns/audio`(오디오 바이트 본문) → SSE 전에 인식 → `transcript`·`turn`·`sentence(audio)`·`done`. 합성은 `app.state.speech`(`app/voice/speech.py`, 동시 3개·실패는 null·안내 캐시)로만 한다.
  - `_run_turn`은 문장 합성을 띄워 두고 CLI를 계속 읽는다. 소리가 된 맨 앞 문장부터 보내고, 도구 이벤트 앞과 답변 끝에서만 남은 문장을 끝까지 기다린다(순서 유지). 끊긴 턴(`interrupted`)은 남은 합성을 취소하고 글만 보낸다.
  - 가짜 음성 백엔드 `VOICE_BACKEND=fake`(`app/voice/fake.py`): 업로드가 `FAKE_STT:<글>`로 시작하면 그 글을, 아니면 `FAKE_STT_TEXT`를 인식 결과로 돌려준다. 합성은 0.3초 무음 MP3. `run.sh --fake`·E2E가 쓰고, 음성 화면 실제 구동 확인 때도 쓴다(handoff 2장 명령에 `VOICE_BACKEND=fake`를 더한다).
  - CLI 오류(시간 초과·크래시)로 끝나도 합성 대기 중이던 문장과 끝 조각은 글로 보내고 끊긴 답변으로 저장한 뒤 오류를 보낸다(3단계 중간 점검에서 수정). 남은 한계: 맨 앞 소리가 다 돼도 다음 CLI 이벤트가 와야 나간다(보통 짧다).
- **결정(2026-10-16)**
  - D2 음성 인식은 OpenAI API다. 서버 PC가 Intel CPU라 로컬 큰 모델로는 3초 목표가 어렵다.
  - D3 목소리는 OpenAI TTS다. 인식과 같은 OpenAI 키를 쓰고, 보이스는 샘플 청취로 `nova`를 골랐다.
  - 쉬는 중에도 30분 동안 말이 없으면 대화를 끝낸다(서버와 같음). 상태 머신과 쉬기 문구에 반영했다.
  - D1(서버 위치)은 아직 정하지 않았다. S3-14 전에 정한다.
- **환경**
  - OpenAI 키: 설정 이름은 `OPENAI_API_KEY` 하나로 합쳤고 예전 이름 `WHISPER_API_KEY`도 받는다(사용자 `.env`는 `WHISPER_API_KEY`에 값이 있음). 키가 없어도 서버는 시작하고 음성 호출만 `voice_unavailable`(503)이 된다. `.env` 값은 보지 않는다.
  - ffmpeg 7.1을 `~/.local/bin/ffmpeg`에 설치했다(2026-10-16). Homebrew가 없고 MacPorts는 sudo가 필요해서, PyPI `imageio-ffmpeg` 0.6.0 휠에 든 Intel macOS 정적 빌드를 꺼내 넣었다(코드 서명 없음). Opus 인코딩·디코딩, MP3, 16kHz 모노 WAV 변환을 확인했다. 다른 서버로 옮길 때(D1)는 그곳에 따로 설치하거나 `imageio-ffmpeg` 의존성으로 경로를 얻는 방식을 검토한다.
  - 서버 PC는 Intel i9 Mac(x86_64), 메모리 64GB다.
- **2단계 점검 결과**(사용자 요청 2회): 1차 오류 2건·개선 4건, 2차(10-16) 오류 3건·개선 2건(`a5719a3`·`ec34790`)을 고쳤다. 2차 내용은 다음과 같다.
  - 턴 도중 다른 곳(끝내기 API·무발화 감시)이 세션을 끝내면 `session_ended`로 알린다.
  - 일지 정리 결과의 줄바꿈과 태그 `#`을 정리한다.
  - 무발화 종료의 `ended_at`을 마지막 활동 시각으로 기록한다.
  - 끝내기 응답이 `pending`이면 정리 중 안내를 보인다.
  - 진행 중 대화의 일지 상세에 안내를 보인다.
- **S3-10 AudioInput(`20cd16a`, 완료)**: `createAudioInput(settings, onEvent)`(`web/src/platform/audioInput.ts`)이 상태 머신 명령 `micOn`/`micOff`/`setVadMode`를 `start`/`stop`/`setMode`로 받고 `speech_start`·`speech_end {audio}`·`error`를 낸다. 인코딩은 `encodeAudio.ts`(Opus webm, 안 되면 WAV).
  - vad-web은 첫 `start()`가 실패하면 "errored"로 굳어 다시 못 쓴다. 그래서 마이크·AudioContext를 직접 열고, 실패하면 VAD를 버리고 다음 `start()`에 새로 만든다.
  - 재생 중 짧은 소음으로 답변이 끊기지 않게 `speech_start`는 `onSpeechRealStart`(말이 0.3초 이어진 뒤)에 연결했다.
  - 실제 구동 확인은 Vite 개발 서버를 다른 포트(예: 5299, `VITE_API_TARGET=http://127.0.0.1:8300`)로 띄우고 페이지에서 `import('/src/platform/audioInput.ts')`로 한다. Chromium 가짜 마이크 인자: `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<wav>`(파일을 반복 재생하므로 앞뒤 무음을 넣는다). Vite는 `localhost`(IPv6)에만 붙으니 `127.0.0.1`이 아니라 `localhost`로 연다. 헤드리스 Chromium은 마이크 권한이 없으면 `NotAllowedError`가 아니라 `NotSupportedError`를 준다.
  - onnxruntime wasm이 14MB(압축 3.7MB)라 S3-14 PWA 캐시 설정 때 고려한다.
- **S3-11 AudioOutput(`8c04f44`)·S3-13 음성 모드(`0465493`, 완료)**
  - 컨트롤러 `voiceController.ts`가 상태 머신 명령을 실행한다(React와 분리, 의존성 주입으로 테스트). 훅 `useVoiceConversation`은 수명·Wake Lock·Media Session, `VoiceControls`는 큰 버튼(탭은 onClick, 포인터는 길게 누르기만).
  - 끼어들기(`cancelTurn`)는 턴 요청 연결을 끊고 cancel API(S3-04)로 들려준 문장까지만 남기게 한다.
  - 네트워크 오류는 S3-12에서 오프라인 보관(`send_failed`·큐 명령)으로 연결했다(아래 S3-12 절).
  - 음성 모듈은 `lazyPlatform.ts`로 지연 로딩한다. 다 불러오기 전에는 "음성으로 대화"가 막힌다(오디오를 누른 동작 안에서 열려고).
  - 실제 구동 확인: 가짜 마이크 wav는 "무음 1초 + 문장 + 무음 30초"처럼 뒤를 길게 둔다(반복 재생이 겹치면 말하는 중 끼어들기로 잡힌다). "생각하는 중"은 가짜 음성 백엔드에서 0.1초뿐이라 Playwright로 기다리면 놓친다. 빌드본은 `WEB_DIST_DIR`로 FastAPI가 서빙하게 해서 `/vad/`·지연 청크를 운영 경로로 확인한다.
  - 상태 머신 변경: 처리 중 탭에도 `stopPlayback`(검색 안내 음성 정지). 전이 표 사례 1개 갱신(안드로이드도 반영).
- **S3-05 음성 원본 보관(`d8d5876`, 완료)**: 프로필 `keep_audio`가 켜진 음성 턴의 녹음을 `AUDIO_DIR`(기본 `server/data/audio`)에 저장하고 30일 뒤 지운다(`app/jobs/audio.py`, 무발화 감시 루프). 설정 화면(S3-18)에서 켠다. 실제 구동 확인 때는 `AUDIO_DIR`을 scratchpad로 준다.
- **S3-07 지연 측정(`dce5350`, 완료)**: 음성 턴마다 `turn_latency`(마이그레이션 0005)에 서버 단계 시간과 웹 보고(말 끝 → 요청, 요청 → 첫 소리, 첫 소리가 검색 안내였는지)를 남기고 `GET /api/latency`로 중앙값·p90을 본다(NFR-01 측정 방법은 계획서 완료 기준 표 아래).
  - 첫 측정(실제 OpenAI 음성, 가짜 CLI, 1턴): 총 5.8초 = 말 끝 → 요청 1.3초(무음 대기 1.2초 포함) + 인식 2.9초 + … 첫 소리(검색 안내). 인식이 앞선 실측(0.9~1.6초)보다 길어 변동이 크다. 3초 목표에서 무음 대기 1.2초가 큰 몫이라, 산책 측정 뒤 `end_of_speech_silence_ms` 조정과 인식 모델 선택을 검토한다.
- **S3-12 오프라인 큐(`30b8576`, 완료)**: 사용자 결정(2026-10-16)으로 **복구되면 쌓인 말을 보통 턴처럼 차례로 보내 캐릭터가 대답**한다.
  - **상태 머신·전이 표가 바뀌었다(안드로이드도 반영 필요)**: `flushQueue`→`sendQueued`, `queue_flushed`→`queue_sent {remaining}`, 새 `queue_send_failed`, 상태 `connected`·`sendingQueued`. 턴 끝·오프라인 안내 끝·쉬기 재개·오류 뒤에 연결돼 있고 큐가 있으면 큐부터 보낸다(끼어들기는 바로 듣기).
  - 대답할 수 없는 말(서버가 대화를 끝냄, 새로 고침, 5번 실패)은 `POST …/turns/audio/record`로 기록만 남긴다. 끝난 대화면 일지를 다시 정리하고, 정리 도중 턴이 들어오면 `_guarded`가 최대 5번 다시 돈다.
  - 실제 구동 확인은 Playwright `context.setOffline(true/false)`로 한다. 가짜 마이크는 "무음 1초 + 문장 + 무음 4초"(약 12초마다 말함)로 두면 끊긴 동안 여러 번 말하게 할 수 있다. 서버를 띄운 채 DB 파일을 지우면 readonly 오류가 나므로 서버를 내린 뒤 지운다.
  - 남은 것(드묾): 포기 표시 저장이 계속 실패하면 같은 말을 되풀이해 보낸다. 정리 다시 돌기 5번을 다 쓰면 앱 재시작 때까지 pending이다.
- **3단계 중간 전체 점검(10-16, 사용자 요청)**: 기준선 테스트·실제 구동 모두 정상이었고, 오류 경로 시험으로 아래를 고쳤다.
  - 음성 세션에서 CLI가 답변 도중 죽으면 합성을 기다리던 문장이 화면·DB에서 사라지던 문제(텍스트는 끝 조각만 유실).
  - 글 대화에서 답변을 기다리는 동안 "대화 끝내기"가 막혀 CLI가 멈추면 최대 2분 못 끝내던 문제. 받던 말풍선은 끊긴 답변으로 마무리한다.
  - **상태 머신·전이 표 변경(안드로이드도 반영 필요)**: 처리 중(답변 대기) `speech_end`는 버리지 않고 항상 `queueUtterance`로 큐 뒤에 넣는다. 턴이 끝나면 기존 규칙대로 큐부터 보낸다. 큐 순번은 말이 끝난 때 정해, 보내던 말이 나중에 실패해 큐에 들어가도 그사이 넣은 뒷말보다 앞에 선다(커밋 전 리뷰에서 발견). 화면은 연결돼 있으면 "이어서 한 말 N개 · 답변 뒤에/다음 차례에 보내요". `sendingQueued`는 이제 정보용이다. 처리 중 검색 안내 음성이 마이크에 잡히면 큐에 들어갈 수 있다(말소리 없음이면 버려짐) — 실기기에서 확인한다.
  - 점검했지만 그대로 둔 것: 말풍선 마크다운 원문 노출(4장 과제), 쉬기 안내의 "30분" 고정 문구(서버 기본값과 같음).
- **S3-16 음성 흐름 E2E(10-17)**: `web/e2e/voice.spec.ts`(Playwright 프로젝트 `voice`)가 발화 → 답변 → 끼어들기 → 오프라인 보관·복구 → 끝내기를 가짜 마이크로 시험한다. 가짜 마이크 `web/e2e/fixtures/utterance.wav`는 앞 무음 1초 + macOS `say -v Yuna` 문장(가짜 인식 결과와 같은 글) + 뒤 무음 20초(약 24초마다 말함, `make-utterance.sh`로 다시 만듦). 상태는 `.voice-controls[data-state]`로 기다리고 기기 TTS는 2초로 고정한다(`addInitScript`). 시간에 민감하므로 고칠 때는 3번 연속 돌려 본다(지금 약 35초, 전체 E2E 약 45초). 오프라인 단계는 Chromium 오프라인 흉내가 Vite HMR 웹소켓을 끊지 않는 데 기댄다.
- **3단계 종료 점검 중(10-17)**: 실제 CLI 수동 통합 테스트를 했다(임시 DB, 8300). 이중 인터럽트(연결 끊김 + cancel) 경고 없음, 끊긴 답변은 빈 글·interrupted로 남음, 음성 검색 답변은 출처를 사이트 이름으로만 말함(가짜 녹화의 `Sources:` 문제는 실제 CLI에는 없음).
  - **NFR-01 미달**: 책상 측정 중앙값 6.6초(목표 3초). 내역: 무음 대기·전송 준비 1.25초, 인식 1.1~1.5초, 인식 뒤 CLI 첫 글자 약 1.3초, 첫 문장 완성·합성 약 2.7초. 개선 후보: 무음 대기 줄이기(VAD `end_of_speech_silence_ms`), 첫 문장을 더 일찍 끊어 합성 시작, 스트리밍 TTS, 맞장구 소리로 빈 시간 메우기. 사용자 결정 필요.
  - 남은 사용자 몫: 실제 산책(NFR-01·03 실측, 끼어들기 오작동, 답변 길이 체감), 결정 D4(제니가 먼저 말 걸기)·D7(안드로이드 포팅 시작 기준), 마일스톤 확인. S3-17 웹 부분과 기존 일지 분류는 다른 세션에서 진행 중.
- **테스트(현재)**: pytest 통과 565·건너뜀 4(실제 CLI·OpenAI), Vitest 234, E2E 7(음성 1 포함).
- **S3-14 완료(10-17, 폰 A35에서 음성 대화 사용자 확인)**: 결정 D1 = 집 Mac + Tailscale Serve(tailnet 안에서만 HTTPS, 공개 Funnel 안 씀 — 서버 API에 인증이 없어서). 폰은 tailnet의 안드로이드 "강석의 A35"(Galaxy A35).
  - `./run.sh --phone`: 웹을 `web/dist`로 빌드해 서버(8000)가 서빙, `caffeinate -is`로 잠자기 방지, `tailscale serve --bg --https=443`, Ctrl+C 때 serve off. 인증서가 꺼져 있으면 안내 후 종료, serve가 허용 링크를 내며 멈추면 15초 뒤 끊고 출력을 보여 준다. 사용법은 `docs/phone.md`.
  - PWA: vite-plugin-pwa **1.3.0**(2.0.0은 배포 2주 미만이라 보류). `registerType: 'prompt'`(자동 새로 고침 없음), 앱 셸 precache, `/vad/`는 런타임 CacheFirst(첫 방문은 서비스 워커가 페이지를 아직 제어하지 않아 두 번째 열기부터 저장됨), `/api`·`/internal`·`/docs` 제외. 아이콘은 `web/public/icon.svg`에서 Playwright로 PNG를 만들었다(favicon도 교체).
  - `/internal/*` 방어: MCP 미들웨어가 Tailscale Serve가 늘 붙이는 `X-Forwarded-Host`(그리고 `X-Forwarded-Proto`·`Tailscale-User-Login`)도 프록시 요청으로 보고 403(기존 X-Forwarded-For 검사와 함께).
  - 음성 감지 자산은 버전 폴더 `/vad/<vad-web>-<onnxruntime>/`(`web/vadAssets.ts`, `__VAD_DIR__` define)에 둔다. 해시 없는 이름이라 CacheFirst가 의존성을 올린 뒤에도 옛 wasm을 줄 수 있어서다(커밋 전 리뷰).
  - 새 버전: `registerType: 'prompt'` + `UpdateBanner`(useRegisterSW, 한 시간마다 확인) "새 버전 적용" 버튼. 홈 화면 앱은 잘 닫히지 않아 버튼 없이 두면 옛 앱에 갇힌다(커밋 전 리뷰).
  - 알려진 위험(나중 과제): 인증 없는 `/api`가 tailnet에 열려, 폰 브라우저의 악성 사이트가 단순 POST(CSRF)로 부작용을 낼 여지가 있다(응답은 못 읽음). 필요하면 Origin·Content-Type 검사를 넣는다.
  - localhost 실제 확인: 서비스 워커 등록·manifest·오프라인 다시 열기·제어 상태 음성 한 바퀴·vad 캐시 4개. 사용자가 Serve를 허용한 뒤(10-17) Mac에서 ts.net 주소(임시 8443 → 8300)로 같은 확인과 음성 턴 2회, `/internal/mcp/` 403을 실측했다. Serve가 붙이는 헤더: X-Forwarded-For/Host/Proto, Tailscale-User-Login/Name/Profile-Pic, Tailscale-Headers-Info. 사용자가 A35 Chrome에서 음성 대화가 잘 되는 것을 확인했다(10-17). 홈 화면 추가·이어폰 버튼(Media Session)은 아직 따로 확인하지 않았다 — 실제 산책 때 본다. 끄기는 `./stop.sh`(이 저장소 server/·web/ 작업 폴더의 프로세스만, 443이 이 서버를 가리킬 때만 Serve off).
- **S3-18 웹 설정 화면(10-17, 사용자 요청으로 S5-01 웹 부분 앞당김)**: 호칭·관심사·보이스(미리 듣기)·말 속도·음성 원본 보관. 서버는 `speaking_rate`(마이그레이션 0007), 보이스 검증(`app/voice/tts.py` `OPENAI_VOICES`), `GET /api/voices`·`/voices/{voice}/sample`, `services/profile.voice_style`로 페르소나 보이스에 프로필 값을 덮어써 턴·인사말·마무리에 쓴다(`open_llm`이 보이스도 돌려준다).
  - 말 속도는 `speed`만으로 약해서 말투 지시(`rules.SPEECH_RATE_*`)를 함께 붙인다. 실측(같은 문장): 기본 6.67초, 느리게 0.85 8.93초, 빠르게 1.35 5.28초. 1.2는 6.0~6.3초로 차이가 작았다.
  - 미리 듣기는 속도를 0.05 단위로 묶고, 합성 캐시(`app/voice/speech.py`)는 최근 64개만 둔다. 예전 API가 저장한 목록 밖 보이스는 캐릭터 기본으로 본다.
  - 알려진 점: 보이스만 바꾸면 페르소나 말투 지시("20대 여성…")가 다른 보이스(남성 보이스 포함)에도 그대로 붙는다.
  - 안드로이드 설정 화면은 5단계 S5-01에 남았다.
- **S3-15 규약 확정(10-17)**: 도구 `summary`를 `kind`(`web_search`·`web_fetch`·`result`)로 구분하는 타입으로 고정하고, 출처 호스트(`sources`·`host`)를 서버(`app/llm/parser.py` `host_of`)가 만든다. web_fetch 출처는 CLI WebFetch 결과의 `url` 필드에 기댄다(없으면 "페이지 읽기 완료"). `docs/client-contract.md`는 확정본이며 바꾸는 규칙(문서·스키마·전이 표 함께, 안드로이드 반영 메모)을 서문에 적었다. 바뀐 필드 계산은 `web/src/core/settings.ts`(포팅 대상).
- **다음 작업**(사용자 요청 10-17: "3단계를 모두 개발", 작업마다 Plan Mode 승인)
  1. S3-15 클라이언트 규약 확정, S3-16 음성 흐름 E2E, 이어서 3단계 마일스톤 종료 점검(S3-17은 다른 세션이 진행 중).
  2. 실제 산책에서 확인할 것: 홈 화면 추가·이어폰 버튼(Media Session), 지연(NFR-01)·인식률, VAD 수치.

## 2. 3단계를 진행할 때 알아야 할 것

- **끼어들기(S3-04)**
  - 답변은 `sentence`를 보내기 전에 문장마다 DB에 커밋된다(`conversation._run_turn`의 `next_sentence`·`_save_reply`). 끝나기 전에는 `interrupted=True`이고 `done` 때 최종 텍스트로 바뀐다.
  - S3-04(`22f4e5e`)에서 `POST …/turns/{turn_id}/cancel {last_played}`로 **들려준 문장**까지 자른다. 런타임이 진행 중인 턴(`active_turn`)과 최근 답변 3개의 문장 목록(`reply_sentences`)을 들고 있고, 없으면 저장된 답변을 다시 나눈다(번호가 조금 어긋날 수 있음). 자르기는 턴 락 안에서 한다.
  - 자른 경우 다음 턴 CLI 입력 앞에만 `rules.INTERRUPTED_HEARD/NOTHING` 안내를 붙인다(`runtime.heard_note`, 기록에는 없음). 프롬프트 스냅샷과는 무관하다.
  - 남은 점검: 연결 끊기와 cancel이 겹쳐 인터럽트가 두 번 가는 경우를 실제 CLI로 확인(마일스톤 끝). 끝내기 요청이 락 대기에서 cancel보다 앞서면 일지 정리가 자르기 전 원문을 읽을 수 있다(웹은 cancel을 먼저 보내 보통 문제 없음).
- **인사말**: 시작 응답(`POST /api/sessions`)의 JSON으로 오고 SSE가 아니다. 음성 세션이면 `greeting.audio`(MP3 base64)가 함께 온다(S3-03). 마무리 멘트도 `closing_audio`로 온다.
- **마무리 멘트**: `POST /api/sessions/{id}/end`가 일지 정리를 최대 45초 기다린 뒤 `closing`(페르소나 YAML 문구)을 준다. 음성 세션이면 `closing_audio`(MP3)도 준다(S3-03). 정리를 기다리는 동안은 "일지로 정리하는 중…" 문구와 "그만 기다리기" 버튼만 보인다(S3-13, 효과음 없음). 효과음·안내 음성이 필요한지는 실제 산책 확인 때 본다.
- **오프라인 큐(S3-12)**: 큐 항목은 대화 ID와 함께 보관한다. 끝내기 전에 큐를 비우지 않는다. 끝난 대화에 남은 말은 대기로 돌아갈 때 기록만 남긴다(규약 4절).
- **기억 블록**: 기억이 있으면 첫인사에서 지난 아이디어를 먼저 꺼낸다(`prompt.py`의 "앱 안내"). 음성 인사말이 길어지지 않는지 확인한다.
- **호칭 바꾸기(10-17, 사용자 요청 추가)**: 대화 중 "앞으로 OO라고 불러줘"면 MCP `set_nickname`이 프로필 호칭을 바꾼다. 검색 결과 속 지시로 바뀌지 않게 이번 사용자 발화에 호칭 핵심부(공백·끝의 님/씨 제외)가 있을 때만 받는다. 세션 프롬프트는 세션 행에 고정이라 바꾼 뒤 `--resume`으로 CLI가 다시 뜨면 옛 호칭이 프롬프트에 남는다(규칙·대화 기록이 새 호칭을 우선하게 함, 실제 확인 안 함). 다음 대화는 미리 띄운 CLI가 프롬프트 비교로 다시 뜬다.
- **일지 정리(추출)**: haiku 단발 호출(`claude_cli.run_oneshot`)이다. 대화 중 `save_note`가 저장한 노트를 종류와 함께 알려 같은 항목을 다시 뽑지 않게 한다.
- **실제 구동 검증 환경**
  - 포트 8000에는 사용자가 띄운 서버(실제 DB)가 떠 있을 수 있어 `./run.sh --fake`가 실패한다. 이 서버는 건드리지 않는다.
  - 대신 `web/`에서 웹을 임시 폴더로 빌드(`npx vite build --outDir <임시>/dist`)하고, `server/`에서 가짜 CLI 서버를 다른 포트에 띄운다(경로는 절대 경로, `R`은 저장소 루트):
    `CLAUDE_CLI_PATH=$R/server/tests/fakes/fake-claude FAKE_CLAUDE_FIXTURE=web_search FAKE_CLAUDE_ONESHOT=<임시>/oneshot.jsonl CLI_ENV_PASSTHROUGH='["FAKE_CLAUDE_*"]' DATABASE_URL=sqlite+aiosqlite:///<임시>/fake.db CLI_WORK_DIR=<임시>/cli INTERNAL_BASE_URL=http://127.0.0.1:8300 WEB_DIST_DIR=<임시>/dist uv run uvicorn app.main:app --port 8300`
  - `oneshot.jsonl`은 `server/tests/fixtures/claude_cli/extract.jsonl`의 사본이다(가짜 CLI는 줄이 여러 개면 파일의 첫 줄을 지우므로 원본 대신 사본을 쓴다).
  - 정리가 늦는 상황은 `EXTRACT_WAIT_S=1 FAKE_CLAUDE_ONESHOT_DELAY=5`로 흉내 낸다.
  - Playwright 스크립트는 `require('<저장소>/web/node_modules/playwright')`로 불러 headless로 돌린다.
  - 임시 파일은 세션 scratchpad에 두고 `/tmp`는 쓰지 않는다.

## 2-1. 2단계에서 배운 것

- **평가 세트만으로는 부족했다**: 추출 평가(가짜 대화)는 처음부터 100%였지만, 실제 대화 5회에서 중복 노트와 진행 기록 메모가 드러났다. 원인은 실제 대화에서는 `save_note`가 먼저 저장하고(괄호 맥락이 붙음) 추출이 이를 다시 뽑는다는 점이다. 마일스톤 끝의 실제 CLI 확인을 건너뛰지 않는다.
- **문자열 중복 제거는 보수적으로**: 느슨한 규칙(글자 2-gram, 괄호 제거)은 "팟캐스트 대본 쓰기/녹음하기", "치과 (3시)/(5시)"처럼 다른 항목을 지워 데이터를 잃었다(리뷰에서 발견). 표현을 줄인 중복은 추출 지시(LLM)에 맡긴다. 기존 유사도 규칙(0.8)도 "월요일/화요일 회의 자료 준비"처럼 한 낱말만 다른 항목을 같다고 볼 수 있다(남은 한계).
- **Claude CLI는 작업 폴더마다 `~/.claude/projects/<폴더 이름>/`을 만든다**(`--no-session-persistence`여도 빈 `memory/` 폴더). 단발 호출은 고정 작업 폴더(`cli_work_dir/oneshot`)를 쓴다. 수동 확인 때 임시 `CLI_WORK_DIR`을 쓰면 끝난 뒤 그 이름의 폴더를 지운다.
- **추출 평가의 변동**: 같은 세트에서 회차마다 재현율이 96~100%로 1건 안팎 달라진다. 채점은 sonnet(추출 haiku보다 강한 모델)이 하고, 경계 판정은 리포트의 "사람 검토" 절에 적는다.
- **관찰(미처리)**: 제니가 제안하고 사용자가 받아들이지도 거절하지도 않은 내용이 아이디어로 들어간 적이 있다(예: "걸음 박자에 맞춰 단어를 들려주는 방식"). 정답 기준("사용자가 받아들인 것")으로는 경계다. 실제 일지를 보며 지시를 조정할지 정한다.
- **전체 테스트에서 1회 실패가 있었으나 재현되지 않았다**(그 뒤 14회 반복 모두 통과, 실패 테스트 이름은 못 남김). 시간에 민감한 테스트(`test_server_kill`·`test_idle`·`test_extract`)가 의심된다. 다시 보이면 `-rf`로 이름을 남긴다.

## 3. 1단계에서 배운 것 (코드만 봐서는 알기 어려운 것)

- **응답 대기 약 0.9초는 API 첫 토큰 시간이다**(실측 구성: 우리 서버·CLI 0.02초, API 0.87초, 첫 문장 완성까지 +0.4초).
  - 대화 모델을 haiku로 바꿔도 줄지 않아서 sonnet을 유지한다(사용자 결정).
  - `--effort low`도 효과가 없었다.
  - 남은 개선 후보는 "답변 글자를 생성되는 대로 바로 표시"(약 0.4초)다. 사용자가 아직 고르지 않았다.
- **도구를 쓴 턴의 지연**: 도구 뒤 답변은 모델이 생각(thinking)을 끝낸 뒤 한꺼번에 온다(약 4.7초, CLI 단독 실행에서도 같음). 3단계 음성에서 "잠깐 찾아볼게요" 안내로 대응할 예정이다(S3-03).
- **Claude CLI의 특성**(근거: [spikes/claude-cli.md](spikes/claude-cli.md))
  - MCP 도구를 쓰려면 `ENABLE_TOOL_SEARCH=false`가 필요하다.
  - 오류 판정은 `is_error`로 한다.
  - `system/init`은 턴마다 온다.
  - 계정 이메일이 맥락에 자동으로 붙는다(프롬프트에 언급 금지 규칙이 있음).
  - 웹 검색 결과에는 "출처 링크를 달라"는 도구 안내가 붙는다(규칙으로 처리함).
- **톤 평가**: `RUN_REAL_CLI=1 uv run python -m tests.persona_eval.run_eval`. 결과는 `docs/eval/`에 저장된다(같은 날이면 `-2`, `-3`… 이름).
  - 프롬프트(`rules.py`·`prompt.py`·YAML)를 바꾸면 스냅샷 갱신과 함께 다시 돌린다.
  - 채점 모델이 관대할 때가 있다. 실패 사유를 읽고 경계 판정을 리포트에 적는다.
- **실제 CLI로 수동 확인하는 법**
  - `./run.sh`(실제 CLI) 또는 임시 DB로 따로 띄운다: `DATABASE_URL=sqlite+aiosqlite:///<임시>.db CLI_WORK_DIR=<임시> uv run uvicorn app.main:app --port 8000`
  - 브라우저 확인은 Playwright headless 스크립트로 한다(전역 규칙: 화면 캡처는 Playwright).
  - 사용자가 지켜보는 창(headless 아님)을 쓰면, 사용자가 직접 입력해 스크립트가 꼬일 수 있다.
  - 끝나면 `~/.claude/projects/`에 생긴 임시 작업 폴더 이름의 폴더를 지운다.
- **백그라운드 작업과 Ctrl+C 시험**: 비대화형 셸에서 `&`로 띄운 작업은 SIGINT를 무시한다. 종료 시험은 SIGTERM으로 한다.

## 4. 남은 과제(정해진 단계에서 처리)

| 과제 | 처리 시점 |
|---|---|
| 답변 속 마크다운(`**굵게**`, 링크)이 화면에 그대로 보임(음성은 `speech_text`가 지움, `f89057b`) | 필요 시 화면 표시 정리 |
| 음성 답변 상한 5문장이 걸으며 듣기에 길지 않은지 | 3단계 완료 기준 표에 항목 있음 |
| 일지 상세의 화자 이름은 현재 페르소나(세션에 persona_id 없음) | 5단계 페르소나 전환(S5-01) |
| 추출 재현율을 실제 일지로 다시 재기, 평가 정답 사용자 검토 | 실제 사용 일지가 쌓인 뒤 |
| `web/src/core`의 브라우저 API 비의존을 린트로 강제 | 필요 시 |
| 결정 D1(서버 위치) | S3-14 전 |
| 오프라인 큐: 포기 표시 저장이 계속 실패하면 같은 말 재전송, 정리 다시 돌기 5번 소진 시 재시작까지 pending | 필요 시 |
| iOS Safari 오디오 열기(사용자 동작 안), Media Session 이어폰 버튼 실동작 | S3-14 실기기 |
| 오프라인 안내 문구(`client.offline_notice`)가 캐릭터 말투인데 공유 JSON에 있음. 페르소나 YAML에 두고 프로필 응답에서 덮어쓰기(S3-06 리뷰) | S5-01 페르소나 전환 전 |
| 서버만 따로 배포하면 `shared/client-defaults.json`이 없어 시작 실패. `shared/`를 함께 두거나 `CLIENT_DEFAULTS_PATH` 지정 | S3-14·결정 D1 |

## 5. 작업 방식 (사용자가 원하는 흐름)

- 모든 응답과 중간 진행 메시지는 한글로 쓴다.
- 기능 추가·버그 수정은 소스를 고치기 전에 Plan Mode로 계획을 승인받는다.
- 검증은 유닛 테스트에 더해 Playwright로 실제 구동까지 한다.
- 커밋 전에는 매번 서브에이전트 diff 리뷰를 받고 반영한다.
- 이 저장소는 자동 커밋·push가 허용돼 있다.
- 실제 CLI는 구독 사용량을 쓴다. 필요할 때만 쓰고, 보고할 때 대략의 사용량을 알린다.
- 측정 결과가 기대와 다르면(예: haiku 전환 효과 없음) 진행을 멈추고 사실대로 보고한 뒤 방향을 묻는다.
- 계획서의 작업 상태·체크박스·커밋 해시·변경 이력은 작업을 시작하고 끝낼 때마다 갱신한다(계획서 1장).
