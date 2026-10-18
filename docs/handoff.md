# 작업 인계 (2026-10-18, 3단계 종료 점검 중)

새 세션은 이 문서부터 읽는다. 규칙·명령은 [CLAUDE.md](../CLAUDE.md), 진행 상태는 [구현 계획서](implementation-plan.md) 2장 대시보드(작업별 내용·커밋은 각 작업 절과 12장 변경 이력), API·SSE·상태 머신은 [클라이언트 규약](client-contract.md)이 기준이다. 여기에는 그 문서들과 코드에 없는 맥락만 둔다. 끝난 내용은 지운다.

## 0. 새 세션 시작 프롬프트

```text
TrailTalk 작업을 이어서 진행합니다. docs/handoff.md를 읽고 구현 계획서 2장 대시보드를 확인하세요.
작업 규칙: 응답은 한글, 소스 수정 전 Plan Mode로 계획 승인, 유닛 테스트에 더해 Playwright 실제 구동 검증, 커밋 전 서브에이전트 diff 리뷰, 이 저장소는 자동 커밋·push 허용, 작업 시작·끝에 계획서 상태 갱신.
주의: .env 값은 열어 보지 마세요. 포트 8000의 사용자 서버(실제 DB)는 건드리지 말고 실제 구동 검증은 handoff 2장대로 다른 포트에서 하세요. 실제 Claude CLI(구독)와 OpenAI(과금)는 필요할 때만 쓰고 쓸 때 알려 주세요.
handoff 1장 "다음 작업"을 확인하고 Plan Mode로 계획을 세우세요.
```

## 1. 지금 상태와 다음 작업

- 0·1·2단계 완료. 3단계는 S3-17(일지 아이디어별 보기, 다른 세션 진행 중)만 남고 종료 점검 중이다. PC 브라우저와 폰(A35, `./run.sh --phone`)에서 음성 대화가 된다.
- **사용자 결정 대기**
  - NFR-01 미달: 책상 측정 중앙값 6.6초(목표 3초) = 무음 대기·전송 1.25 + 인식 1.1~1.5 + 인식 뒤 CLI 첫 글자 1.3 + 첫 문장 완성·합성 2.7초. 후보: 무음 대기 줄이기(`end_of_speech_silence_ms`), 첫 문장을 일찍 끊어 합성, 합성이 끝난 첫 문장도 다음 CLI 이벤트가 와야 나가는 점 고치기(`conversation._run_turn`의 `head_ready`는 이벤트 루프 안에서만 확인), 스트리밍 TTS, 맞장구 소리.
  - 결정 D4(제니가 먼저 말 걸기)·D7(안드로이드 포팅 시작 기준), 3단계 마일스톤 확인.
- **실제 산책에서 볼 것**: 지연·인식률(NFR-01·03), 제니 목소리로 인한 끼어들기 오작동, 답변 길이(상한 5문장), 홈 화면 추가·이어폰 버튼(Media Session), VAD 수치, 처리 중 검색 안내 음성이 마이크에 잡혀 큐에 들어가는지, 긴 발화 이어 말하기(S3-33: 무음 1.8초, 처리 중 소음으로 첫 답변이 취소되는지·말 끝 지연), 기억이 있을 때 첫인사(지난 아이디어부터 꺼냄)가 너무 길지 않은지, 일지 정리 대기(최대 45초, 문구만) 중 소리 안내가 필요한지.
- **다음 작업(사용자 요청, 새 세션에서 Plan Mode로 설계부터): 화자 인식(여러 참가자)** — 2026-10-18 세션에서 요구가 넓어졌다. 대화를 시작할 때 "저는 다니엘입니다", "저는 강석입니다", "저는 필재입니다"처럼 차례로 말하면 각 목소리가 화자로 등록되고, 그 뒤 여러 사람이 대화에 참여해도 **화자별 내용이 섞이지 않게** 인식해 질문으로 받는다. 등록하지 않은 소리(TV·지나가는 사람)는 버린다. **OpenAI 음성 인식 API(사용자는 "Whisper API"라고 부름)의 기능을 최대한 쓴다**(사용자 지시). 계획서에 새 작업 ID(S3-35~)로 추가해 진행한다. 아래 초안은 이전 세션이 승인 전에 멈춘 것이니 새로 검토해 계획을 다시 세운다.
  - **OpenAI 기능(2026-10 공식 가이드 [speech-to-text](https://developers.openai.com/api/docs/guides/speech-to-text.md) 확인)**: `gpt-4o-transcribe-diarize`는 `response_format=diarized_json`으로 구간마다 `speaker`·`start`·`end`·`text`를 준다. `known_speaker_names[]`·`known_speaker_references[]`(2~10초 클립, data URL, **최대 4명**)를 주면 구간을 등록한 이름에 맞춘다(등록 안 된 화자는 `A`·`B` 같은 라벨로 추정 — 실측 필요). 30초 넘는 오디오는 `chunking_strategy=auto` 필수. **prompt·logprobs·timestamp_granularities 미지원, Realtime 미지원** → 지금 쓰는 직전 답변 힌트(`create_audio_turn`의 `hint`)를 못 쓰고, 판정은 발화가 끝난 뒤 서버에서만 된다(말 시작 0.3초 안 판정 불가). 지금 본문 인식 모델 `gpt-transcribe`는 `prompt`·`keywords`·`languages`, `stream=true`를 지원한다. 실시간용은 `gpt-live-transcribe`(별도 가이드, 화자 구분 없음).
  - **초안 방향**: 화자 임베딩 ONNX를 브라우저에 넣지 않고 서버 diarize로 판정(클라이언트는 얇게, 안드로이드 포팅 부담 작음). 참가자를 등록하지 않은 대화는 지금 경로 그대로(NFR-01 6.6초를 더 늘리지 않게).
    - S3-35 스파이크(과금 소량, 쓰기 전 알림): TTS 보이스 여러 개로 참가자 흉내 → 짧은 한국어 발화 화자 정확도, 이어 말한 세 사람 분리, "저는 다니엘입니다"가 2초 미만일 때 클립 맞추기(앞뒤 여유·무음 채우기·안내 문구 길게), 같은 이름 클립 여러 개 허용 여부, 이름 추출 규칙(아래 정규식은 "하야입니다"를 "하"로 자르고 "다니엘이라고 합니다"를 놓친다), diarize 본문 대 `gpt-transcribe` 품질·지연, 제니 목소리(nova) 메아리를 known speaker로 넣으면 걸러지는지(넣으면 참가자는 3명까지). 결과는 `docs/spikes/`에.
    - 서버: 등록 API(예: `POST /api/sessions/{id}/speakers`, 오디오 → diarize → 정규식 `저는\s*(\S+?)\s*(입니다|이에요|예요|이야|야)`로 이름 추출 → ffmpeg로 구간을 잘라 클립 저장, 삭제 API). 음성 턴(`turns/audio`·`turns/audio/record`)은 참가자가 있으면 diarize로 → 같은 화자 구간 합치기, 미등록·제니 구간 버림, 남은 게 없으면 새 오류(예: `speaker_unknown` 422, `no_speech` 자리), diarize 실패·시간 초과는 일반 인식으로 대체(이때는 TV 소리도 들어간다 — 대화를 멈추지 않으려는 절충, 거절로 할지 재검토). `Turn`에 `speakers` JSON(`[{name,text}]`)을 더하고 `Turn.text`는 `"다니엘: …\n강석: …"`(마이그레이션). 추출(`jobs/extract.py`의 `"사용자"` 접두)·재개 프롬프트(`persona/prompt.py`)는 이름으로. 캐릭터 무관 규칙(여러 사람 말 섞지 않기)은 `persona/rules.py`(스냅샷 갱신), 참가자 안내는 `_run_turn`의 `cli_text` 앞(`now_note`·`heard_note` 패턴). SSE `transcript`에 `speakers` 추가 → 규약·`gen:api`.
    - 생체 정보: 등록 클립은 세션 동안만 두고 세션이 끝나면 파일을 지우는 안(이름만 일지 표시용으로 남김). 다시 열기(S3-26)면 다시 등록.
    - 웹: 음성 대화 시작 때 "혼자 할게요 / 함께할 사람 등록" → 등록 중 VAD 발화는 등록 API로, 이름 칩(삭제 ×, 44px)과 "다 됐어요". 말풍선·일지 상세는 화자 이름표로 나눠 보이기. `speaker_unknown`은 문구 없이 조용히 다시 듣고, 큐의 발화면 버리고 다음을 보낸다.
  - **끼어들기(사용자 결정 대기)**: 판정이 발화 끝 뒤라, 참가자가 있을 때 후보는 (1) 말하기 중 `speech_start`에 재생을 일시정지 → `speech_end` 뒤 서버 확인(예: `…/speakers/identify`) → 등록 화자면 지금의 끼어들기(취소+전송), 아니면 이어 재생(처리 중 `userSpeaking`도 같은 확인을 기다림, 상태 머신·`transitions.json`·규약 4절 변경), (2) 지금처럼 바로 끊고 발화만 거름, (3) 재생 중 음성 끼어들기 끄기(탭만). 이전 세션 추천은 (1). (1)은 identify와 턴에서 같은 오디오로 diarize를 두 번 부르게 되니, identify 결과(구간)를 턴 본문으로 바로 쓰는 방법을 검토한다. 한계: TV가 계속 말하면 VAD가 발화를 끝내지 않아 그동안 멈춰 있고, 동시에 말한 부분은 화자가 틀릴 수 있다.
  - 붙일 자리·제약(이전 조사): 웹 `web/src/platform/audioInput.ts`의 `onSpeechRealStart`(`speech_start`)·`onSpeechEnd`(16kHz 모노 샘플을 Opus(webm, 안 되면 WAV)로 인코딩해 `speech_end`). 서버 `server/app/api/sessions.py`의 `create_audio_turn`·`record_audio_turn`, `server/app/voice/stt.py`(`OpenAiStt`, 가짜는 `voice/fake.py`). `web/src/core`는 순수 TS. 상태 머신을 바꾸면 `shared/fixtures/transitions.json`과 규약 4절을 함께 고친다. 등록 화면은 모바일 우선(44px 터치, 호버 의존 금지). 실제 검증은 가짜 마이크 WAV에 여러 TTS 보이스("저는 ○○입니다" 등록 → 화자별 발화 → 미등록 목소리)를 이어 붙여 Playwright로 한다.
- S3-17이 병합되면 전체 테스트를 다시 돌리고 `CLAUDE.md`·규약을 코드와 대조한 뒤 3단계를 닫는다.
- **안드로이드(4단계)에 반영할 것**: 상태 머신·전이 표는 S3-12(오프라인 큐)와 처리 중 발화 큐잉(큐 순번은 말이 끝난 때)으로 바뀌었다. 기준은 `shared/fixtures/transitions.json`과 규약 4절이다. S3-33에서 `userSpeaking`(처리 중 이어 말하면 첫 답변 취소, 말하기 중 `speech_end` 큐잉)과 검색 안내 음성 동안 재생 중 VAD 임계값(플랫폼 쪽)이 더해졌다. 이어서 하기(S3-26)는 머신을 바꾸지 않고 '시작' 명령에서 새 대화 대신 다시 열기 API를 부른다(규약 2절 "다시 열기", 다른 대화가 진행 중이면 클라이언트가 막는다).

## 2. 실제 구동 검증 방법

- 포트 8000의 사용자 서버는 건드리지 않는다(그래서 `./run.sh --fake`는 실패할 수 있다). 임시 파일은 세션 scratchpad에 둔다(`/tmp` 금지).
- **가짜 CLI 서버(8300)**: 웹을 `npx vite build --outDir <임시>/dist`로 빌드하고 `server/`에서
  `CLAUDE_CLI_PATH=$R/server/tests/fakes/fake-claude FAKE_CLAUDE_FIXTURE=web_search FAKE_CLAUDE_ONESHOT=<임시>/oneshot.jsonl CLI_ENV_PASSTHROUGH='["FAKE_CLAUDE_*"]' VOICE_BACKEND=fake DATABASE_URL=sqlite+aiosqlite:///<임시>/fake.db CLI_WORK_DIR=<임시>/cli AUDIO_DIR=<임시>/audio INTERNAL_BASE_URL=http://127.0.0.1:8300 WEB_DIST_DIR=<임시>/dist uv run uvicorn app.main:app --port 8300`
  - `oneshot.jsonl`은 `server/tests/fixtures/claude_cli/extract.jsonl`의 사본(가짜 CLI가 여러 줄 파일의 첫 줄을 지운다).
  - 답변을 늦추려면 `FAKE_CLAUDE_DELAY=0.3`(이벤트마다), 정리 지연은 `EXTRACT_WAIT_S=1 FAKE_CLAUDE_ONESHOT_DELAY=5`.
  - 실제 OpenAI 음성은 `VOICE_BACKEND=fake`를 빼고 `FFMPEG_PATH=$HOME/.local/bin/ffmpeg`를 준다. 실제 CLI는 `CLAUDE_CLI_PATH`·`FAKE_*`·`CLI_ENV_PASSTHROUGH`를 빼면 된다.
  - 서버를 띄운 채 DB 파일을 지우면 readonly 오류가 난다(서버를 내린 뒤 지운다).
- **Playwright**: 스크립트에서 `require('<저장소>/web/node_modules/playwright')`, headless(사용자가 보는 창을 쓰면 사용자 입력에 스크립트가 꼬인다). 화면 캡처도 Playwright로 한다.
  - 모듈 하나만 시험할 때는 Vite 개발 서버를 다른 포트(예: 5299, `VITE_API_TARGET=http://127.0.0.1:8300`)에 띄우고 페이지에서 `import('/src/platform/…')`로 부른다.
  - 가짜 마이크: `--use-fake-ui-for-media-stream --use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<wav>` + 권한 `microphone`. 파일을 되풀이하므로 뒤 무음을 길게 둔다(짧으면 답변 중 끼어들기로 잡힘). E2E용 `web/e2e/fixtures/utterance.wav`(약 24초 주기)를 그대로 써도 된다.
  - 상태는 `.voice-controls[data-state]`로 기다린다. 가짜 음성에서는 "생각하는 중"이 0.1초뿐이라 문구로는 놓친다. 기기 TTS(오프라인 안내)는 `addInitScript`로 고정하는 편이 안정적이다(`web/e2e/voice.spec.ts`).
  - Vite 개발 서버는 `localhost`(IPv6)에만 붙는다. 헤드리스 Chromium은 마이크 권한이 없으면 `NotSupportedError`를 준다. 오프라인 시험은 `context.setOffline`.
- **폰 경유 확인**: `tailscale serve --bg --https=8443 http://127.0.0.1:8300`으로 임시로 열고 끝나면 `--https=8443 off`(443은 사용자 폰 모드용).
- **실제 CLI 수동 확인 뒤**: 임시 `CLI_WORK_DIR`이면 `~/.claude/projects/`에 그 이름의 폴더(빈 `memory/`)가 생기니 지운다. 사용량을 보고한다.
- 비대화형 셸에서 `&`로 띄운 작업은 SIGINT를 무시한다(종료 시험은 SIGTERM). `./stop.sh`는 이 저장소 `server/`·`web/` 작업 폴더의 프로세스만 끈다 — 사용자가 띄운 `./run.sh`도 끄므로 시험 전에 떠 있는지 확인한다.

## 3. 환경

- 서버 PC: Intel i9 Mac(x86_64), 64GB. 결정 D1에 따라 서버도 이 Mac, 폰은 Tailscale Serve(tailnet 안에서만 HTTPS. API에 로그인이 없어 공개 Funnel은 쓰지 않는다). 폰은 tailnet의 "강석의 A35"(Galaxy A35).
- OpenAI 키: 설정 이름 `OPENAI_API_KEY`, 예전 이름 `WHISPER_API_KEY`도 받는다(사용자 `.env`는 `WHISPER_API_KEY`). 키가 없으면 음성 호출만 `voice_unavailable`.
- ffmpeg 7.1: `~/.local/bin/ffmpeg`(Homebrew 없음·MacPorts는 sudo 필요라 PyPI `imageio-ffmpeg` 0.6.0 휠의 정적 빌드를 꺼내 넣음, 코드 서명 없음). `ffprobe`는 없다(길이는 `ffmpeg -i`의 Duration으로 본다).
- 보이스 샘플 `server/data/voice-samples/`(커밋 안 함, `uv run python -m tests.voice_samples`). 사용자가 `nova`를 골랐다.
- vite-plugin-pwa는 1.3.0(2.0.0은 당시 배포 2주 미만이라 보류).

## 4. 배운 것(코드만 봐서는 알기 어려운 것)

- **지연**: 텍스트 응답 대기 약 0.9초는 API 첫 토큰 시간이다(haiku·`--effort low`로도 줄지 않아 sonnet 유지, 사용자 결정). 도구 뒤 답변은 생각을 끝낸 뒤 한꺼번에 온다(약 4.7초). 음성 인식은 앱 경로(`gpt-transcribe`, webm)에서 1.1~1.6초, 때로 2.9초까지 흔들린다. "글자를 생성되는 대로 표시"(약 0.4초)는 사용자가 아직 고르지 않았다.
- **Claude CLI**(근거 [spikes/claude-cli.md](spikes/claude-cli.md)): MCP 도구에 `ENABLE_TOOL_SEARCH=false` 필요, 오류는 `is_error`로 판정, `system/init`은 턴마다 옴, 계정 이메일이 맥락에 붙음(언급 금지 규칙), 웹 검색 결과에 "출처 링크를 달라"는 안내가 붙음(규칙으로 사이트 이름만). 작업 폴더마다 `~/.claude/projects/<폴더>/`를 만든다. 가짜 녹화 `web_search`는 규칙 이전 답변이라 `Sources:` 링크가 있다(실제 CLI는 없음).
- **TTS**: OpenAI TTS는 피치가 없고 `gpt-4o-mini-tts`는 `speed`를 덜 따른다. 말투·빠르기는 `instructions`로도 지시한다(실측: 0.85 +34%, 1.35 -21%, 1.2는 차이 작음). 보이스만 바꿔도 페르소나 말투 지시("20대 여성…")가 그대로 붙는다.
- **vad-web**: 첫 `start()`가 실패하면 "errored"로 굳는다. 그래서 마이크·AudioContext를 직접 열고 실패하면 VAD를 버려 다음에 새로 만든다. `speech_start`는 `onSpeechRealStart`(0.3초 이어진 뒤)에 연결해 재생 중 짧은 소음에 끊기지 않게 했다.
- **평가**: 추출 평가(가짜 대화)는 처음부터 100%였지만 실제 대화에서 중복 노트·진행 기록 메모가 드러났다(실제 대화는 `save_note`가 먼저 저장하고 추출이 다시 뽑는다). 마일스톤 끝 실제 CLI 확인을 건너뛰지 않는다. 회차마다 재현율이 1건 안팎 흔들린다. 톤 평가 채점 모델은 관대할 때가 있어 실패 사유를 읽고 경계 판정을 리포트에 적는다.
- **중복 제거는 보수적으로**: 느슨한 문자열 규칙은 "치과 (3시)/(5시)"처럼 다른 항목을 지웠다. 표현만 다른 중복은 추출 지시에 맡긴다. 유사도 0.8 규칙도 한 낱말만 다른 항목을 같다고 볼 수 있다(남은 한계).
- **관찰(미처리)**: 제니가 제안하고 사용자가 받아들이지도 거절하지도 않은 내용이 아이디어로 들어간 적이 있다. 실제 일지를 보며 지시를 조정할지 정한다.
- 전체 pytest에서 재현되지 않는 실패가 1회 있었다(시간에 민감한 `test_server_kill`·`test_idle`·`test_extract` 의심). 다시 보이면 `-rf`로 이름을 남긴다. 음성 E2E도 시간에 민감하니 고치면 3번 연속 돌린다.

## 5. 남은 과제(정해진 단계에서 처리)

| 과제 | 처리 시점 |
|---|---|
| 답변 속 마크다운(`**굵게**`, 링크)이 화면에 그대로 보임(음성은 `speech_text`가 지움) | 필요 시 |
| 인증 없는 `/api`가 tailnet에 열림: 폰 브라우저의 악성 사이트가 단순 POST(CSRF)로 부작용을 낼 여지. Origin·Content-Type 검사 검토 | 필요 시 |
| 일지 상세의 화자 이름은 현재 페르소나(세션에 persona_id 없음), 오프라인 안내 문구(`client.offline_notice`)가 공유 JSON에 있음(페르소나 YAML로) | S5-01 페르소나 전환 전 |
| 추출 재현율을 실제 일지로 다시 재기, 평가 정답 사용자 검토 | 실제 일지가 쌓인 뒤 |
| 오프라인 큐: 포기 표시 저장이 계속 실패하면 같은 말 재전송, 정리 다시 돌기 5번 소진 시 재시작까지 pending | 필요 시 |
| 호칭을 대화 중 바꾼 뒤 `--resume`으로 CLI가 다시 뜨면 고정 프롬프트에 옛 호칭이 남음(규칙·기록으로 새 호칭 우선, 실제 확인 안 함) | 필요 시 |
| `web/src/core`의 브라우저 API 비의존을 린트로 강제 | 필요 시 |
| 쉬기 안내의 "30분"이 화면 문구에 고정(`VoiceControls`·`ConversationScreen`). `IDLE_TIMEOUT_S`를 바꾸면 어긋남 | 필요 시 |
| iOS Safari(오디오 열기·마이크)는 확인하지 않음(폰 확인은 안드로이드 A35만) | iOS로 쓸 때 |

## 6. 작업 방식(사용자가 원하는 흐름)

- 응답과 중간 진행 메시지는 한글. 소스 수정 전 Plan Mode 승인. 유닛 테스트 + Playwright 실제 구동. 커밋 전 서브에이전트 diff 리뷰 반영. 자동 커밋·push 허용.
- 실제 CLI·OpenAI는 필요할 때만 쓰고 대략의 사용량을 알린다. 측정이 기대와 다르면 멈추고 사실대로 보고한 뒤 방향을 묻는다.
- 다른 세션이 같은 저장소를 동시에 고칠 때가 있다. 커밋은 내 파일만 경로를 지정해 담는다(남의 스테이징을 휩쓸지 않게 `git commit -- <경로>`).
