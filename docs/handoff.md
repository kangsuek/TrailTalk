# 작업 인계 (2026-10-16, 3단계 진행 중: S3-01·S3-02·S3-03·S3-06·S3-08·S3-09·S3-10 완료)

새 세션은 이 문서부터 읽는다. 작업 규칙과 명령은 [CLAUDE.md](../CLAUDE.md)에 있다. 진행 상태의 기준은 [구현 계획서](implementation-plan.md)의 진행 대시보드(2장)다. 이 문서에는 계획서·설계서에 없는 맥락만 둔다. 상태가 바뀌면 이 문서도 갱신하거나 지운다.

## 0. 새 세션 시작 프롬프트

새 세션에서 아래를 그대로 붙여 넣는다.

```text
TrailTalk 작업을 이어서 진행합니다. 먼저 docs/handoff.md를 읽고, 구현 계획서(docs/implementation-plan.md)의 진행 대시보드(2장)와 3단계 절(6장)을 확인하세요.
지금은 3단계(웹 음성 대화) 진행 중이고 S3-01·S3-02·S3-03·S3-06·S3-08·S3-09·S3-10이 끝났습니다. 다음 작업 후보는 handoff 1장 "다음 작업"에 있습니다.
작업 규칙: 응답은 한글, 소스 수정 전 Plan Mode로 계획 승인, 유닛 테스트에 더해 Playwright 실제 구동 검증, 커밋 전 서브에이전트 diff 리뷰, 이 저장소는 자동 커밋·push 허용, 작업 시작·끝에 계획서 상태 갱신.
주의: .env 값은 열어 보지 마세요. 포트 8000에 떠 있는 사용자 서버(실제 DB)는 건드리지 말고, 실제 구동 검증은 handoff 2장의 방법대로 다른 포트에서 하세요. 실제 Claude CLI(구독 사용량)와 OpenAI API(과금)는 필요할 때만 쓰고 쓸 때 알려 주세요.
다음 작업을 무엇으로 할지 제게 먼저 확인한 뒤 계획을 세우세요.
```

## 1. 지금 어디까지 왔나

- **0·1·2단계 완료**(2단계는 2026-10-16 사용자 확인, 마일스톤 `5749ea3`). **3단계(웹 음성 대화) 진행 중 7/16**, 전체 32/56. 앱 화면에서 음성 대화를 하려면 S3-11(재생)·S3-13(화면 연결)이 남았다.
- **3단계에서 끝낸 것**: S3-08 세션 상태 머신·S3-09 상태 전이 표(`9202e04`), S3-06 클라이언트 설정값(`2b643a9`). S3-01·S3-02·S3-03은 아래 절에 따로 적었다.
  - S3-06: `GET/PUT /api/profile`이 `client`(VAD·세션·오디오·오프라인 안내, 읽기 전용)를 준다. 서버가 시작할 때 `shared/client-defaults.json`을 `app/client_config.py`로 검증하고 틀리면 시작하지 않는다. `idle_timeout_minutes`는 서버 `IDLE_TIMEOUT_S`로 덮어쓴다. VAD 수치(0.5/0.35, 재생 중 0.8/0.65)는 시작값이라 실제 산책 측정에서 조정한다. 웹은 아직 프로필을 받아 쓰지 않는다(S3-13에서 `vadSettingsFrom(client.vad)`로 넘긴다).
  - `web/src/core/sessionMachine.ts`: 이벤트 → 다음 상태 + 명령을 내는 순수 함수다. 마이크·재생·서버 호출은 하지 않는다.
  - `shared/fixtures/transitions.json`: 사례 22개. 안드로이드 테스트도 이 파일을 읽는다.
  - 아직 화면에 연결하지 않았다(S3-13에서 연결). 플랫폼이 지킬 약속은 규약 4절에 있다(인사말은 `session_started {turnId}`, `sentence`·`turn_done`에 턴 ID, 모든 요청은 성공·실패 이벤트로 끝냄, 큐 비우기 결과는 `queue_flushed {remaining}`).
- **S3-01·S3-02(`f89057b`·`ef035e2`, 완료)**: `app/voice/stt.py`·`tts.py`·`audio.py`·`openai_http.py`. 앱에서 `app.state.stt`·`app.state.tts`로 쓴다.
  - 실제 확인(2026-10-16, 크레딧 충전 뒤): `RUN_REAL_OPENAI=1 uv run pytest tests/test_voice_real.py -q -s` 통과(TTS 1회·STT 2회, webm·ogg 모두 원문과 같음). ffmpeg가 PATH에 없으면 `FFMPEG_PATH=~/.local/bin/ffmpeg`를 준다. `languages` 필드는 API가 읽는다(틀린 코드 400). 7초 발화 인식 응답은 앱 경로(`gpt-transcribe`, webm)에서 약 1.3초, 다른 모델·형식은 1.5~3초였다(WAV는 업로드가 커서 느림).
  - 보이스는 6종 샘플(`uv run python -m tests.voice_samples`, `server/data/voice-samples/`, 커밋 안 함)을 사용자가 듣고 `nova`로 골랐다. `instructions`(말투 지시)는 그대로 두었다.
  - S3-03 음성 턴도 가짜 CLI + 실제 OpenAI로 확인했다(2장 명령에 `VOICE_BACKEND=fake` 없이 `FFMPEG_PATH`를 더한다). 가짜 CLI 녹화 `web_search`는 지금 출처 규칙 이전 답변이라 `Sources:`·링크 줄까지 소리로 만든다. 실제 CLI 음성 답변에서는 마일스톤 끝 실제 확인 때 본다.
  - OpenAI TTS에는 피치가 없어 페르소나 `voice.pitch`를 지우고 `instructions`(말투 지시)를 넣었다. `gpt-4o-mini-tts`는 `speed`를 무시한다는 보고가 있어, 빠르기는 `instructions`에도 적었다.
  - TTS 전처리 `speech_text`는 음성에만 쓰고 화면 문장(`sentence.text`)은 그대로 둔다.
  - 그대로 못 보내는 업로드(ogg 등)는 WAV가 아니라 16kHz 모노 webm/opus(24kbps)로 바꾼다(업로드 크기가 응답 지연에 더해지므로). 설정은 빈 값(`KEY=`)을 없는 것으로 본다(`env_ignore_empty`).
- **S3-03 음성 턴(`bafcea9`, 완료)**: `POST /api/sessions/{id}/turns/audio`(오디오 바이트 본문) → SSE 전에 인식 → `transcript`·`turn`·`sentence(audio)`·`done`. 합성은 `app.state.speech`(`app/voice/speech.py`, 동시 3개·실패는 null·안내 캐시)로만 한다.
  - `_run_turn`은 문장 합성을 띄워 두고 CLI를 계속 읽는다. 소리가 된 맨 앞 문장부터 보내고, 도구 이벤트 앞과 답변 끝에서만 남은 문장을 끝까지 기다린다(순서 유지). 끊긴 턴(`interrupted`)은 남은 합성을 취소하고 글만 보낸다.
  - 가짜 음성 백엔드 `VOICE_BACKEND=fake`(`app/voice/fake.py`): 업로드가 `FAKE_STT:<글>`로 시작하면 그 글을, 아니면 `FAKE_STT_TEXT`를 인식 결과로 돌려준다. 합성은 0.3초 무음 MP3. `run.sh --fake`·E2E가 쓰고, S3-13 화면 작업과 실제 구동 확인 때도 쓴다(handoff 2장 명령에 `VOICE_BACKEND=fake`를 더한다).
  - 남은 한계: CLI 오류(시간 초과·크래시)로 끝나면 합성 대기 중이던 문장은 보내지 않는다. 맨 앞 소리가 다 돼도 다음 CLI 이벤트가 와야 나간다(보통 짧다).
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
- **테스트(현재)**: pytest 485(4개는 실제 CLI·OpenAI라 건너뜀), Vitest 155, E2E 5.
- **다음 작업**(사용자에게 먼저 고르게 한다)
  - S3-04 끼어들기 API(재생한 문장까지 기록, 끝난 턴의 cancel 처리).
  - 웹: S3-11 AudioOutput(base64 MP3 이어 재생, 재생한 문장 번호, 즉시 정지) → S3-13 대화 화면 음성 모드(상태 머신·AudioInput·AudioOutput 연결). 이 둘이 끝나면 PC 브라우저에서 음성 대화가 된다. 가짜 음성 백엔드로 끝까지 이어 볼 수 있다.
  - 작업마다 Plan Mode로 계획을 승인받는다.

## 2. 3단계를 진행할 때 알아야 할 것

- **끼어들기(S3-04)**
  - 답변은 `sentence`를 보내기 전에 문장마다 DB에 커밋된다(`conversation._run_turn`의 `sentences()`·`_save_reply`). 끝나기 전에는 `interrupted=True`이고 `done` 때 최종 텍스트로 바뀐다.
  - 지금은 보낸 문장 기준이고, 음성에서는 **재생한 문장** 기준이 필요하다. 상태 머신은 `cancelTurn {turnId, lastPlayed}`(다 들려준 마지막 문장 번호, 없으면 -1)를 보낸다.
  - 상태 머신은 이미 끝난 턴(인사말, `done` 뒤 재생 중 끼어들기)에도 `cancelTurn`을 보낸다. 서버가 이를 멱등으로 받아 `lastPlayed`로 자를지 S3-04에서 정한다(계획서 S3-04 체크박스).
- **인사말**: 시작 응답(`POST /api/sessions`)의 JSON으로 오고 SSE가 아니다. 음성 세션이면 `greeting.audio`(MP3 base64)가 함께 온다(S3-03). 마무리 멘트도 `closing_audio`로 온다.
- **마무리 멘트**: `POST /api/sessions/{id}/end`가 일지 정리를 최대 45초 기다린 뒤 `closing`(페르소나 YAML 문구)을 준다. 음성 세션이면 `closing_audio`(MP3)도 준다(S3-03). 정리를 기다리는 최대 45초 동안 효과음·안내를 낼지는 S3-13에서 정한다.
- **오프라인 큐(S3-12)**: 큐 항목이 어느 세션에 속하는지, 끝내기 전에 큐를 비울지는 아직 정하지 않았다(규약 4절에 미정으로 적음).
- **기억 블록**: 기억이 있으면 첫인사에서 지난 아이디어를 먼저 꺼낸다(`prompt.py`의 "앱 안내"). 음성 인사말이 길어지지 않는지 확인한다.
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
| 도구 알림의 출처 호스트 추출을 서버로 옮기기(지금은 웹 `toolNotice`) | S3-15 summary 스키마 확정 때 |
| 음성 답변 상한 5문장이 걸으며 듣기에 길지 않은지 | 3단계 완료 기준 표에 항목 있음 |
| 끼어들기 때 "재생한 문장까지만" 기록(지금은 보낸 문장까지), 끝난 턴의 cancel 처리 | S3-04 |
| 일지 상세의 화자 이름은 현재 페르소나(세션에 persona_id 없음) | 5단계 페르소나 전환(S5-01) |
| 추출 재현율을 실제 일지로 다시 재기, 평가 정답 사용자 검토 | 실제 사용 일지가 쌓인 뒤 |
| `web/src/core`의 브라우저 API 비의존을 린트로 강제 | 필요 시 |
| 결정 D1(서버 위치) | S3-14 전 |
| 오프라인 큐의 세션 소속, 끝내기 전 큐 비우기 | S3-12 |
| 상태 머신을 대화 화면에 연결 | S3-13 |
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
