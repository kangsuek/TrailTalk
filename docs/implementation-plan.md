# TrailTalk 구현 계획서

- 기준 문서: [requirements-design.md](requirements-design.md) (이하 "설계서")
- 최종 갱신: 2026-10-17

## 1. 문서 사용법

설계서의 5단계 개발 방법을 0~5단계 마일스톤과 작업 단위로 나누고, 각 작업의 세부 단계와 진행 상태를 이 문서 하나에서 관리한다. 작업 ID(예: `S1-03`)는 Claude Code에 "S1-03 구현"처럼 요청하는 단위다.

**상태값**: `완료` · `진행 중` · `대기` · `막힘`(사유를 비고에 적는다)

**갱신 규칙**

1. 작업을 시작하면 작업 목록 표의 상태를 `진행 중`으로 바꾸고, 대시보드의 "현재 작업"을 갱신한다.
2. 세부 단계를 끝낼 때마다 체크박스를 `- [x]`로 바꾼다.
3. 작업이 끝나면 상태를 `완료`로 바꾸고 커밋 해시를 적는다.
4. 마일스톤(단계)이 끝나면 완료 기준 표의 측정값·결과, 진행 대시보드, 요구사항 추적표, 변경 이력을 갱신한다.
5. 요구사항 추적표의 상태는 관련 작업이 모두 `완료`이고 검증 단계의 완료 기준을 통과하면 `완료`, 일부만 끝났으면 `진행 중`으로 적는다.
6. 커밋 해시는 커밋 전에는 알 수 없으므로, 해당 커밋 직후 다음 갱신 때 채운다.

## 2. 진행 대시보드

| 단계 | 상태 | 작업 | 기간(예상) | 시작 | 완료 | 마일스톤 커밋 |
|---|---|---|---|---|---|---|
| [0. 준비·기술 검증](#3-0단계--준비와-기술-검증) | 완료 | 5/5 | 3~5일 | 2026-10-12 | 2026-10-12 | `a9b2970` |
| [1. 제니 텍스트 대화](#4-1단계--제니-텍스트-대화) | 완료 | 11/11 | 1~2주 | 2026-10-12 | 2026-10-15 | `4dac567` |
| [2. 대화 기록](#5-2단계--대화-기록) | 완료 | 9/9 | 1~2주 | 2026-10-15 | 2026-10-16 | `5749ea3` |
| [3. 웹 음성 대화](#6-3단계--웹-음성-대화) | 진행 중 | 29/30 | 2~3주 | 2026-10-16 | | |
| [4. 안드로이드 포팅](#7-4단계--안드로이드-포팅) | 대기 | 0/9 | 3주 | | | |
| [5. 다듬기·확장](#8-5단계--다듬기와-확장) | 대기 | 0/6 | 2주 | | | |
| **전체** | | **54/70** | 약 10~13주 | | | |

- **현재 작업**: S3-17 일지 정렬·아이디어별 보기(다른 세션)
- **다음 작업**: 3단계 종료 점검 진행 중(NFR-01 미달 대응 결정 대기, 실제 산책·D4·D7은 사용자), S3-17 마무리(다른 세션)

## 3. 0단계 — 준비와 기술 검증

**목표**: 저장소 골격을 만들고, 설계 전체가 기대는 "Claude CLI를 서버의 상주 대화 엔진으로 쓰는 방식"(설계서 4.9)을 1단계 전에 검증한다.

- 대상 요구사항: NFR-06(비밀값 서버 보관)
- 선행 조건: 없음

**환경 점검** (2026-10-12)

| 항목 | 상태 | 조치 |
|---|---|---|
| 저장소 | GitHub 공개 저장소 kangsuek/TrailTalk | — |
| Python | 시스템 3.9.6, 서버는 `uv`로 3.12 구성 | — |
| Node | v24.21 | 테스트 의존성 기준 22.22.2 이상 또는 24.15 이상 필요 |
| Claude Code CLI | 2.1.296(`~/.local/bin/claude`), 서버용 토큰 발급 완료 | 자동 업데이트 끄기(`DISABLE_AUTOUPDATER=1`) |
| ffmpeg | 미설치 | 3단계 전 설치 |

**작업 목록**

| ID | 작업 | 상태 | 산출물 | 커밋 |
|---|---|---|---|---|
| S0-01 | 저장소 골격과 문서 | 완료 | 폴더 구조, `.gitignore`, `CLAUDE.md`, `README.md` | `813d01e` |
| S0-02 | 서버 개발 환경 | 완료 | `server/pyproject.toml`, `/api/health` | `813d01e` |
| S0-03 | 웹 개발 환경 | 완료 | `web/package.json`, 4개 화면 자리, E2E 스모크 | `813d01e` |
| S0-04 | Claude CLI 검증 스파이크 | 완료 | `docs/spikes/claude-cli.md`, `server/tests/fixtures/claude_cli/` | `1306053` |
| S0-05 | 서버용 토큰과 비밀값 관리 | 완료 | `.env.example`, 보고서 8절 | `1306053` |

#### S0-01 저장소 골격과 문서
- [x] `git init`, 설계서 5장의 폴더 구조 생성
- [x] `.gitignore`, `.env.example`, `README.md`
- [x] `CLAUDE.md`: 폴더 구조, 실행·테스트 명령, 페르소나 분리 원칙, 작업 규칙
- [x] GitHub 원격 연결과 push

#### S0-02 서버 개발 환경
- [x] `uv`로 Python 3.12 + FastAPI + SQLAlchemy + pydantic-settings + PyYAML
- [x] pytest + httpx2, ruff 설정
- [x] `/api/health`, 설정 로딩, `web/dist` 정적 서빙
- [x] `personas/jenny.yaml`과 필수 키 테스트

#### S0-03 웹 개발 환경
- [x] Vite + React + TypeScript, oxlint
- [x] Vitest + Testing Library, 4개 화면 탭 전환과 서버 상태 표시 테스트
- [x] Playwright 스모크 E2E(서버·웹 자동 기동)

#### S0-04 Claude CLI 검증 스파이크
- [x] 검증 스크립트 작성(`docs/spikes/`), CLI 버전 기록 및 고정 방법 정리
- [x] `--input-format stream-json --output-format stream-json --include-partial-messages`로 프로세스 1개에 여러 턴을 보내고 부분 출력 확인
- [x] 생성 도중 인터럽트(stdin 제어 메시지 또는 시그널) 후 같은 프로세스로 다음 턴이 이어지는지 확인
- [x] `--system-prompt`, `--model sonnet/haiku`, `--mcp-config` + `--allowedTools "mcp__trailtalk__*"` 조합 확인(내장 도구 차단은 `--disallowedTools` 대신 `--tools ""`로 확인)
- [x] 빈 작업 폴더에서 사용자 설정·CLAUDE.md가 섞이지 않는지(`--setting-sources` 등) 확인
- [x] 프로세스 종료 후 `session_id`로 `--resume`해 맥락이 이어지는지 확인
- [x] 첫 토큰까지의 지연 측정(콜드 스타트 vs 상주 프로세스)
- [x] 출력 이벤트 샘플을 파일로 녹화(S1-04 가짜 CLI 입력)
- [x] 결과와 대체 방안 판단을 `docs/spikes/claude-cli.md`에 기록

결과: 상주 프로세스 방식 채택, 대체 방안(턴마다 `--resume`)은 불필요. 상세와 1단계 반영 사항은 [스파이크 보고서](spikes/claude-cli.md).

#### S0-05 서버용 토큰과 비밀값 관리
- [x] `claude setup-token`으로 서버용 토큰 발급
- [x] `.env`에 `CLAUDE_CODE_OAUTH_TOKEN` 설정, 서버 설정에서 읽어 CLI 프로세스 환경으로 전달하는 방식 결정
- [x] 배포 환경의 비밀값 보관 방식 정리(설계서 NFR-06)

**완료 기준**

| 기준 | 목표값 | 측정값 | 결과 |
|---|---|---|---|
| 서버·웹 테스트와 E2E 스모크 | 모두 통과 | pytest 2, Vitest 5, E2E 1 통과 | 통과 |
| CLI 상주 프로세스 스트리밍·인터럽트·MCP 도구 호출 | 모두 동작 또는 대체 방안 확정 | 모두 동작(MCP는 `ENABLE_TOOL_SEARCH=false` 필요) | 통과 |
| 상주 프로세스 첫 토큰 지연 | 기록 | 중앙값 haiku 0.677s, sonnet 0.740s (콜드 1.557s / 1.619s) | 통과 |
| 토큰 인증(`CLAUDE_CODE_OAUTH_TOKEN`) | 키체인 없이 동작 | 정상 토큰 성공, 잘못된 토큰 401 | 통과 |

**마일스톤 종료 체크리스트**
- [x] 유닛 테스트와 Playwright 실제 구동 검증 통과
- [x] `CLAUDE.md`·`client-contract.md`가 실제 코드와 일치
- [x] 서브에이전트 diff 리뷰 반영
- [x] 커밋·push
- [x] 사용자 확인
- [x] 대시보드·추적표·변경 이력 갱신

## 4. 1단계 — 제니 텍스트 대화

**목표**: 텍스트로 제니와 대화하는 전체 경로(웹 → 서버 → Claude CLI → 문장 단위 스트리밍)를 완성하고, 페르소나 일관성을 측정 가능하게 만든다.

- 대상 요구사항: FR-07, FR-08, FR-09, FR-10(일부), FR-20, NFR-06, NFR-07, NFR-08
- 선행 조건: 0단계 완료(S0-04 결과로 CLI 호출 방식 확정)

**작업 목록**

| ID | 작업 | 상태 | 산출물 | 커밋 |
|---|---|---|---|---|
| S1-01 | 공통 오류 응답·로깅·DB 세션 의존성 | 완료 | `server/app/errors.py`, `request_context.py`, `db/session.py` | `93f315d` |
| S1-02 | DB 모델과 마이그레이션 | 완료 | `server/app/db/models.py`, `server/migrations/` | `0169050` |
| S1-03 | LLM 백엔드와 Claude CLI 프로세스 관리 | 완료 | `server/app/llm/` | `19fb1ed` |
| S1-04 | 가짜 CLI와 파서 테스트 | 완료 | `server/tests/fakes/` | `19fb1ed`, `aec44df` |
| S1-05 | 페르소나 스키마와 프롬프트 조립기 | 완료 | `server/app/persona/` | `9e7ff4e` |
| S1-06 | 제니 도구 MCP 서버 | 완료 | `server/app/mcp/`, `server/app/services/runtime.py` | `03bf1c8` |
| S1-07 | 한국어 문장 분할기 | 완료 | `server/app/voice/sentences.py` | `010bf5b` |
| S1-08 | 세션·턴·프로필 API | 완료 | `server/app/api/`, `server/app/services/conversation.py` | `e4e9a7d` |
| S1-09 | SSE 이벤트 스키마 초안 | 완료 | `server/app/api/events.py` | `231fdb4` |
| S1-10 | 웹 텍스트 대화 화면 | 완료 | `web/src/screens/`, `web/src/api/` | `aec44df` |
| S1-11 | 페르소나 톤 평가 | 완료 | `server/tests/persona_eval/` | `d867e14`, `ea609ec` |

#### S1-01 공통 오류 응답·로깅·DB 세션 의존성
- [x] 오류 응답 형식(코드, 메시지) 정의와 예외 핸들러(`AppError`, 클라이언트 규약 7절)
- [x] 요청 로깅(요청 ID, 지연 시간): `X-Request-ID` 헤더, 응답 완료 시점 기록(SSE 대응), 쿼리스트링을 남기는 uvicorn 기본 access 로그는 끔
- [x] DB 세션 의존성 주입: 비동기 SQLAlchemy(`aiosqlite`), `DbSession`, 앱 팩토리 `create_app`
- [x] 테스트: 오류 형식·요청 ID·로그·rollback·외래 키·스트림 도중 오류·웹 정적 서빙 시 `/api` 404/405(pytest 19개), 실제 서버 curl 확인

#### S1-02 DB 모델과 마이그레이션
- [x] SQLAlchemy 모델: `conversation_session`, `turn`, `note`, `user_profile`, `persona`(설계서 4.5). UUID 문자열 ID, UTC 시각(`UTCDateTime`), 열거값 CHECK 제약, `cli_session_id` 추가
- [x] Alembic 초기 마이그레이션(`0001`, 비동기 env, batch 모드, 제약 이름 규칙). 앱 시작 때 자동 적용(`auto_migrate`)
- [x] 테스트용 임시 SQLite 픽스처(`db_session`, 마이그레이션 적용)
- [x] 테스트: 모델 생성·조회, 제약(유일·CHECK·FK·CASCADE·SET NULL), UTC, JSON 목록 제자리 수정, 단일 프로필 행, 마이그레이션과 모델·열거값 CHECK 일치, batch 재생성 시 자식 행 보존, downgrade(pytest 40개)

#### S1-03 LLM 백엔드와 Claude CLI 프로세스 관리
- [x] `LlmBackend` 인터페이스(턴 전송, 부분 출력 이터레이터, 인터럽트, 종료)
- [x] `ClaudeCliBackend`: 세션별 상주 프로세스 생성·종료, 유휴 프로세스 정리. 실행 인자·환경(`ENABLE_TOOL_SEARCH=false`, 토큰 전달, 격리 옵션)은 [스파이크 보고서](spikes/claude-cli.md) "1단계 반영 사항"을 따른다. 내장 도구는 `--tools "WebSearch,WebFetch"`만, 허용 목록은 `mcp__trailtalk__*,WebSearch,WebFetch`
- [x] stream-json 파서(부분 텍스트, 도구 호출, 결과, 오류). 턴 경계는 `result`, 오류는 `is_error`로 판정
- [x] 인터럽트(`control_request`/`interrupt`, 중단 턴은 `terminal_reason=aborted_streaming`)와 `--resume` 복구(세션 저장 켜고 매니저가 마지막 `cli_session_id`로 재기동). DB 보관은 호출하는 S1-08에서
- [x] 리뷰 반영: 취소(클라이언트 연결 끊김) 시 즉시 kill, 버려진 스트림은 멈춘 턴으로 강제 정리, 자식 환경 허용 목록, 세션 키 경로 검증, 시작 실패 처리, 키별 락
- [x] CLI 실행 경로를 설정값(`CLAUDE_CLI_PATH`)으로 받기

#### S1-04 가짜 CLI와 파서 테스트
- [x] S0-04 녹화 출력을 재생하는 가짜 CLI 실행 파일(`tests/fakes/fake_claude.py`: 턴별 재생, 지연·인터럽트·크래시·멈춤 흉내, 인자 기록)
- [x] 파서 단위 테스트(정상, 도구 호출, 웹 검색(`web_search.jsonl`), 오류, 중단)
- [x] 프로세스 관리 테스트(생성, 인터럽트, 재시작, 동시 턴 거부, 시간 초과, 유휴 정리, 토큰 비노출). 실제 CLI 통합 테스트는 `RUN_REAL_CLI=1`
- [x] pytest와 Playwright webServer `env`에서 가짜 CLI를 지정 — pytest는 `fake_cli` 픽스처, Playwright는 E2E 전용 서버(8100)의 `CLAUDE_CLI_PATH=server/tests/fakes/fake-claude`(S1-10)

#### S1-05 페르소나 스키마와 프롬프트 조립기
- [x] `jenny.yaml` Pydantic 스키마와 로딩 검증(키 오타 거부, 내용 해시 version·캐시, `{호칭}` 자리표시자는 examples에서만)
- [x] 조립 순서: 페르소나 → 상황 → 기억(이 단계는 빈 값) → 역할 규칙, 페르소나 블록 맨 앞 고정(가변 값 없음)
- [x] 음성/텍스트 모드별 상황 블록, 개인정보·실행 환경 정보 언급 금지 규칙
- [x] 웹 검색 규칙(최신 정보·사실 확인이 필요할 때만, 출처 사이트 이름 언급, 확실하지 않으면 그렇다고 말하기, 웹 내용 속 지시는 따르지 않기)
- [x] 테스트: 조립 결과 스냅샷, YAML만 바꿔 이름·말투 반영(NFR-08), 앱 코드에 캐릭터 이름 없음 확인(YAML의 id·name 기준), 호칭·기억 입력 정리(구조 깨기 방지), 기억 속 지시 무시 문구. 실제 CLI 확인은 `test_llm_real.py::test_real_cli_persona_prompt`(호칭 치환·이모지 없음·문장 수·개인정보 거절)

#### S1-06 제니 도구 MCP 서버
- [x] `save_note`, `search_notes`, `summarize_session`, `pause_session`, `end_session`(이름은 `app/persona/rules.py`와 일치). MCP 서버 이름은 캐릭터와 무관한 `trailtalk`(NFR-08 검사 대상). 별도 프로세스가 아니라 FastAPI 안의 HTTP 엔드포인트 `/internal/mcp/`(세션별 Bearer 토큰, 프록시 전달 헤더가 붙은 요청은 403, 구독 끔)
- [x] `summarize_session` 반환 형식 확정: 사용자 발화 수, 저장한 노트 수와 목록(`- [종류] 내용`). 정리 문장은 모델이 이 결과로 세 문장 이내로 만든다
- [x] 도구 호출 결과를 서버 이벤트(`tool`)로 전달 → SSE 변환이라 S1-08에서 처리(pause/end 요청은 `ConversationRuntime.requested_status`에 기록, 반영 순서는 `services/runtime.py` 주석)
- [x] `--mcp-config` 생성과 허용 도구 제한: 작업 폴더에 `mcp.json`(권한 600, 실패·종료 시 삭제), 헤더 토큰은 로그에서 가림
- [x] 테스트: 각 도구의 입력 검증과 DB 반영, 토큰·세션 불일치 401, 프록시 요청 403, LIKE 와일드카드, 실제 CLI가 HTTP MCP로 노트 저장(`RUN_REAL_CLI=1`, 약 6초)

#### S1-07 한국어 문장 분할기
- [x] 문장부호(연속 부호·닫는 따옴표·붙은 이모지·마크다운 기호 포함)·줄바꿈 기준 분할, 소수점·버전·URL·이메일·번호 목록·줄임말·띄어 쓴 범위 `~` 예외, 짧은 조각 병합, 문장 끝 이모지는 앞 문장에 붙임, 긴 입력도 선형 시간
- [x] 스트리밍 입력(부분 텍스트 누적) 대응: 다음 글자를 봐야 아는 경계는 판단을 미룸
- [x] 테스트: 경계 사례 표 + 한 글자씩 넣어도 같은 결과(스트리밍 불변성), 실제 녹화 답변으로 확인. 마크다운 기호 정리는 3단계 TTS 전처리에서

#### S1-08 세션·턴·프로필 API
- [x] `POST /api/sessions`(인사말): 숨은 첫 메시지(`rules.GREETING_INSTRUCTION`)로 받은 인사말을 assistant 턴 seq 0으로 저장. 실패하면 세션을 남기지 않음. 대화 모드는 `conversation_session.mode`(마이그레이션 `0002`)에 두고, 프롬프트는 세션 시작 시각·모드·프로필로 만들어 `--resume` 때도 같게 함
- [x] 턴 시작 시 `TurnStarted.cli_session_id`를 `conversation_session.cli_session_id`에 저장(프로세스 복구용)
- [x] 세션 종료 시 CLI 프로세스 닫기와 CLI 세션 파일 정리: `~/.claude/projects/*/<cli_session_id>.jsonl` 정확한 파일만 지우고 빈 폴더도 지움
- [x] `POST /api/sessions/{id}/turns`(텍스트 입력, SSE 응답): 시작 전 오류(404·409·422)는 JSON. 도구 이벤트 → `tool`(S1-06에서 넘어옴), 도구 앞 말은 도구 시작 때 문장으로 내보냄. pause/end 도구 요청을 턴 끝에 반영
- [x] `POST /api/sessions/{id}/end`(요약은 2단계): 멱등. CLI 닫기 → 런타임 폐기 순서
- [x] `GET/PUT /api/profile`: 보낸 필드만 갱신, 호칭 1~20자 한 줄, 관심사 10개·각 30자, 기본 페르소나를 `persona` 테이블에 동기화
- [x] 테스트: 가짜 CLI로 턴 스트리밍 전체 흐름(인사말, 3턴, 도구·웹 검색 변환, 404/409/422, 쉬기·종료 요청, CLI 죽음 → 오류 이벤트 → `--resume` 복구, 인사말 실패, 기록 파일 정리, OpenAPI), 프로필, 턴 중 다른 쓰기·턴 중 종료·동시 턴·오류 문구 비노출, 실제 uvicorn에서 연결 끊김(pytest 31개). 리뷰 반영: 턴 동안 트랜잭션을 열어 두지 않음, 종료와 턴 경합 시 ended 보존(조건부 UPDATE), 끊김 취소가 DB 작업을 끊어 죽은 커넥션이 풀에 남던 버그 수정(DB 구간 취소 보호, `pool_pre_ping`). 실제 CLI로 서버를 띄워 확인: 인사말 2.7초, 첫 sentence 2.8초(도구 없음), `save_note`가 사용자 턴에 연결됨, 연결 끊기 후 다음 턴 복구
- 참고: 도구를 쓴 턴은 CLI가 도구 뒤 답변(thinking 뒤 text)을 한꺼번에 내보내 첫 문장이 늦다(실측 도구 끝 후 약 4.7초). CLI 단독 실행에서도 같고 `MAX_THINKING_TOKENS=0`으로 꺼지지 않는다. 3단계 음성 지연(S3) 때 다시 본다

#### S1-09 SSE 이벤트 스키마 초안
- [x] `turn`(첫 이벤트, 끼어들기용 `turn_id`), `sentence`, `tool`, `done`, `error` 이벤트 모델(이 단계는 텍스트만, 모든 필드 required), 도구 이름을 클라이언트용으로 변환(`public_tool_name`)
- [x] `tool` 이벤트에 웹 검색 시작·종료 포함(스키마. 실제 변환은 S1-08): 시작은 `content_block_start`의 `tool_use`(입력이 비어 있음) 시점에 도구 이름만 담아 바로 보내고, 검색어·URL은 `assistant` 이벤트에서 입력이 완성된 뒤, 종료는 `user` 이벤트의 `tool_result`에서 보낸다
- [x] 이벤트 직렬화와 OpenAPI 문서화(components `StreamEvent`, 판별자 `type`)
- [x] `docs/client-contract.md` 2절에 초안 반영

#### S1-10 웹 텍스트 대화 화면
- [x] OpenAPI 타입 생성 스크립트(openapi-typescript): `npm run gen:api`(서버 `python -m app.openapi` → `src/api/schema.d.ts`). openapi-typescript 7은 TypeScript 5만 피어로 받아 `overrides`로 프로젝트 TypeScript 6을 쓰게 함
- [x] `fetch` + 스트림 파서로 SSE 수신(POST라 `EventSource` 대신): 파서 `src/core/sse.ts`, 클라이언트 `src/api/conversation.ts`(시작 전 오류는 `ApiError`, done 없이 끊기면 `stream_closed`)
- [x] 대화 화면: 텍스트 입력(한글 조합 중 Enter 무시), 문장 단위로 말풍선 채우기, 도구 알림 표시("검색 중…", "출처: 사이트", "메모 저장: …"), 쉬기·끝내기. 상태는 순수 TS 리듀서 `src/core/conversation.ts`. 캐릭터 이름은 시작 응답의 `persona.name`(서버에 추가)
- [x] Vitest: SSE 파서(조각 경계·CRLF·U+2028), 리듀서·도구 알림, API 클라이언트(UTF-8 조각 경계·오류), 화면(작성 당시 45개, 2026-10-15 재검증 후 73개)
- [x] Playwright: 가짜 CLI로 텍스트 대화(인사말 → 웹 검색 → 페이지 읽기 → 메모 저장 → 끝내기), 스크린샷 `web/test-results/conversation*.png`
- [x] 리뷰 반영: 리듀서가 모르는 이벤트를 무시, 깨진 이벤트·처리 예외 때 스트림 취소(서버 턴 정리), 탭을 옮겨도 대화 화면 유지(언마운트 안 함), Safari 한글 IME(keyCode 229), 전송 실패 시 입력 복구, 바닥 근처일 때만 자동 스크롤, SSE BOM, 시작 응답의 페르소나를 인사말을 만든 페르소나로, `gen:api -- --check`
- 참고(후속): 답변의 마크다운(`**굵게**`, 링크)이 그대로 보인다(3단계 TTS 전처리와 함께 서버에서 정리). 도구 알림의 출처 호스트 추출·중복 제거는 지금 클라이언트(`toolNotice`)가 한다. 3단계 summary 스키마 확정(S3-15) 때 서버가 `sources`를 주게 옮긴다. `web/src/core`의 브라우저 API 비의존은 아직 린트로 막지 않는다(tsconfig lib에 DOM)

#### S1-11 페르소나 톤 평가
- [x] 고정 질문 20개와 톤 체크리스트(말투, 길이, 금지 표현, 질문 1개 규칙): `server/tests/persona_eval/questions.yaml`, 기계적 검사 `checks.py`(문장 수는 서버 문장 분할기 기준, 이모지·마크다운·개인정보, 단위 테스트), 말투·질문 수·안전은 채점 체크리스트 7개
- [x] 답변 생성 → `claude -p --model haiku` 채점 스크립트: `RUN_REAL_CLI=1 uv run python -m tests.persona_eval.run_eval`(질문마다 앱과 같은 실행 인자로 새 CLI 세션, 단 MCP 도구 없이, 음성 모드, 채점은 `--json-schema` 구조화 출력, 동시 3개, 약 2분, 같은 날 리포트는 `-2`·`-3`…으로 보존)
- [x] 결과 리포트 출력과 기준(18/20) 판정: 5회차 **20/20 통과**(9 → 15 → 18 → 17 → 20, 이후 프롬프트 보강 뒤 6회차 19, 7회차 20 — 회차 기록은 [최신 리포트](eval/persona-2026-10-15-7.md)). 평가기 오판을 고치고 프롬프트를 보강함(음성 문장 예산, 알 수 없는 주변 상황 단정 금지, YAML에 반말 어미 금지·답 구성). 3회차 18은 관대한 채점을 포함해 4회차에서 기준을 바로잡음(17). 사용자 결정으로 음성 문장 상한 4 → 5(설계서 반영), 채점 맥락에 CLI 계정 이메일 첨부 사실 추가

**완료 기준**

| 기준 | 목표값 | 측정값 | 결과 |
|---|---|---|---|
| 톤 평가 통과(NFR-07) | 20개 중 18개 이상 | 20/20 (2026-10-15 5회차, 음성 상한 5문장). 측정 뒤 웹 검색 규칙 2문장만 바뀜 | 통과 |
| 텍스트 턴 첫 `sentence` 이벤트 지연 | 2초 이내(상주 프로세스 기준, 10회 중앙값) | 중앙값 1.29초(최소 0.95, 최대 1.37), 일상 대화 10턴, 실제 CLI sonnet, 2026-10-15 | 통과 |
| "이거 저장해줘" → `save_note` 호출, 웹에 `tool` 표시 | 동작 | 실제 CLI + Playwright: 3.6초, "메모 저장: …" 알림, 노트가 사용자 턴에 연결돼 저장 | 통과 |
| 최신 정보 질문 → 웹 검색 후 출처와 함께 답변, 일상 대화에는 검색 안 함(FR-20) | 동작 | 검색 질문 4회 모두 `web_search` + 출처 알림·사이트 이름 언급(13~27초), 일상 대화 10턴 검색 0회. 검색 도구 안내를 무시했다고 말하던 문제를 규칙 보강으로 해결 | 통과 |
| `jenny.yaml`만 바꿔 이름·말투 반영(NFR-08) | 코드 수정 없음 | 자동 테스트 `test_persona_yaml_change_needs_no_code_change`(이름·말투가 응답·프롬프트에 반영), 코드 내 이름 검사 통과 | 통과 |
| pytest가 실제 CLI 없이 통과 | 통과 | 243 통과, 실제 CLI 테스트 3개 건너뜀 | 통과 |
| Playwright 텍스트 대화 1턴(가짜 CLI) | 통과 | E2E 2개 통과(인사말 → 웹 검색 → 페이지 읽기 → 메모 저장 → 끝내기), Vitest 52 | 통과 |

**마일스톤 종료 체크리스트**
- [x] 유닛 테스트와 Playwright 실제 구동 검증 통과
- [x] 실제 Claude CLI로 수동 통합 테스트 1회(`./run.sh` + Playwright: 메모 저장·웹 검색·끝내기, 지연 10턴, 웹 검색 3회 재확인)
- [x] `CLAUDE.md`·`client-contract.md`가 실제 코드와 일치
- [x] 구독 사용량 확인: 1단계 동안 실제 CLI 호출은 대략 sonnet 150회·haiku 110회(톤 평가 5회차가 대부분). 계정 한도 화면은 서버에서 볼 수 없어 사용자가 확인
- [x] 서브에이전트 diff 리뷰 반영
- [x] 커밋·push
- [x] 사용자 확인(2026-10-15)
- [x] 대시보드·추적표·변경 이력 갱신

## 5. 2단계 — 대화 기록

**목표**: 모든 턴을 즉시 저장하고, 세션이 끝나면 일지를 자동으로 만들며, 다음 세션에서 제니가 지난 아이디어를 기억한다.

- 대상 요구사항: FR-10, FR-11, FR-12, FR-13, FR-14
- 선행 조건: 1단계 완료

**작업 목록**

| ID | 작업 | 상태 | 산출물 | 커밋 |
|---|---|---|---|---|
| S2-01 | 턴 즉시 저장 | 완료 | `server/app/services/conversation.py` | `5a7c136` |
| S2-02 | 세션 종료 추출 작업 | 완료 | `server/app/jobs/extract.py` | `0d11b0d` |
| S2-03 | 노트 중복 제거 | 완료 | `server/app/jobs/dedupe.py` | `9a93b51` |
| S2-04 | 마무리 멘트 | 완료 | `server/app/api/sessions.py` | `1a42c1a` |
| S2-05 | 기억 블록 | 완료 | `server/app/persona/memory.py` | `8213178` |
| S2-06 | 무발화 타임아웃 | 완료 | `server/app/jobs/idle.py` | `3ab4c1f` |
| S2-07 | 일지·노트 API | 완료 | `server/app/api/journal.py` | `601fc30` |
| S2-08 | 웹 일지 화면 | 완료 | `web/src/screens/` | `22f7c04` |
| S2-09 | 추출 품질 평가 세트 | 완료 | `server/tests/extract_eval/` | `3cf4966` |

#### S2-01 턴 즉시 저장
- [x] 사용자 입력 수신 시 커밋
- [x] 제니 문장 완성 시마다 커밋(트랜잭션 단위 최소화). `sentence`를 보내기 전에 한 줄 쿼리로 커밋하고, 끝나기 전에는 `interrupted`로 둔다(첫 문장 표시 지연 변화 없음: 중앙값 68→69ms, 가짜 CLI)
- [x] 테스트: 스트리밍 중 서버 종료 후에도 직전 턴까지 남는지(`tests/test_server_kill.py`: uvicorn 프로세스 SIGKILL 후 DB 확인, 재기동 후 `--resume`으로 이어짐. 연결 끊김·CLI 크래시도 `test_sessions.py`)

#### S2-02 세션 종료 추출 작업
- [x] 전문 → `claude -p --model haiku --output-format json` 호출(`claude_cli.run_oneshot`, 전문은 stdin, `--json-schema`로 구조화 출력)
- [x] Pydantic 스키마 검증(제목, 요약 3줄, 아이디어·할 일·메모·태그), 실패 시 1회 재시도
- [x] 세션 요약·제목·태그 저장(`extract_status` pending→done/failed, 마이그레이션 0004. 끝내는 순간 pending으로 표시해 서버가 꺼져도 다시 정리)
- [x] 테스트: 가짜 CLI 응답으로 정상·스키마 오류·재시도(`tests/test_extract.py`: 두 번 실패, 시간 초과 kill, 인사만 한 세션, 도구 종료, 앱 종료 시 pending 유지)

#### S2-03 노트 중복 제거
- [x] `save_note`로 저장된 노트와 추출 결과 비교(정규화 문자열 + 유사도). NFKC·소문자·공백·문장부호 제거 후 같음, 짧은 쪽(8자 이상) 포함, 유사도 0.8 이상(6자 이상). 숫자나 부정 표현이 다르면 다른 항목(리뷰 반영). 종류가 달라도 비교한다
- [x] 새 항목만 저장(추출 결과 안의 중복도 거름)
- 보완(2단계 검증): 실제 대화에서 save_note 노트(괄호 맥락)와 추출 결과가 중복 저장됐다. 추출 지시에 저장한 노트를 종류와 함께 알려 거르게 하고(주 대책), 문자열 비교는 같은 종류의 저장 노트에 한해 괄호 설명을 뺀 글과 완전히 같은지도 본다(`matches_saved`, 숫자·부정이 같고 후보에 괄호가 없을 때만, 유사도·포함은 쓰지 않음). 공통 앞부분이 긴 다른 일을 지우는 느슨한 규칙(2-gram)은 리뷰에서 오탐이 확인돼 넣지 않았다. 남은 한계: 기존 유사도 규칙(0.8)도 '월요일/화요일 회의 자료 준비', '공지 올리기/내리기'처럼 한 낱말만 다른 항목을 같다고 볼 수 있다(실제 일지에서 확인되면 보완)
- [x] 테스트: 같은 내용·표현만 다른 내용·다른 내용(`tests/test_dedupe.py`, 추출 연동은 `test_extract.py`)

#### S2-04 마무리 멘트
- [x] 저장 개수 기반 마무리 멘트 생성("오늘 아이디어 3개, 할 일 1개 저장했어요!"). 문구는 페르소나 YAML `closing`(`{저장}` 자리표시자), 개수는 세션 노트
- [x] `end` 응답에 포함(`SessionClosed`: 정리를 최대 `extract_wait_s` 45초 기다림, `journal_status`). 웹은 정리 중 안내 → 마무리 멘트 말풍선, 끝내기 도구로 끝났을 때도 end를 불러 받는다

#### S2-05 기억 블록
- [x] 최근 7일 일지 요약(최신 3개), 열린 아이디어(별표 먼저 5개)·할 일(5개), 관심사 조회. 기억이 있으면 첫인사에서 지난 아이디어·할 일을 꺼내 이어 갈지 묻는다(인사말 지시도 함께 수정. 실제 CLI 1회 확인: 어제 아이디어와 할 일을 먼저 언급)
- [x] 토큰 예산 안에서 잘라 조립(글자 수 `memory_budget_chars` 1200을 토큰 대용으로, 요약→아이디어→할 일→관심사 순, 넘치는 항목은 건너뜀)
- [x] 테스트: 예산 초과 시 우선순위대로 잘리는지(`tests/test_memory.py`, 기억이 바뀌면 미리 띄운 CLI 교체, 기억 있는 프롬프트 스냅샷). 단발 호출 작업 폴더를 고정해 `~/.claude/projects`에 빈 폴더가 쌓이지 않게 함(S2-02 보완)

#### S2-06 무발화 타임아웃
- [x] 30분 무발화 세션 자동 종료(클라이언트 타이머의 안전망). 끝내지 않고 떠난 세션의 런타임(MCP 토큰)·CLI 기록 파일도 이때 정리한다(2026-10-15 재검증에서 확인). 마지막 턴(없으면 시작 시각) 기준, 쉬는 중 포함, 답변 중이면 건너뜀. 감시 주기 60초, 앱 시작 때 즉시 1회
- [x] 종료 시 추출 작업 실행(`conversation.end_session` 경로 그대로)
- [x] 서버 시작 때 `extract_status=pending`으로 남은 세션을 다시 정리(S2-02 리뷰에서 추가. `failed`는 자동 재시도하지 않는다)
- [x] 테스트: 시간 경과 시뮬레이션(`tests/test_idle.py`, `sweep_idle(now=…)`). Playwright: 무발화 3초로 띄운 서버에서 종료·일지 정리·화면 끝남 전환 확인

#### S2-07 일지·노트 API
- [x] `GET /api/journal`(날짜 범위: 현지 날짜, 기본 최근 30일, 항목에 현지 `date`·요약 줄 목록·종류별 개수. 사용자 발화 없는 대화 제외)
- [x] `GET /api/journal/{session_id}`(요약, 노트, 전문)
- [x] `PATCH /api/notes/{id}`(별표, 완료, 내용)
- [x] 테스트: 각 엔드포인트(`tests/test_journal.py`: 현지 자정 경계, 범위 오류, 검증)

#### S2-08 웹 일지 화면
- [x] 일지 목록(날짜별, 서버가 준 현지 `date`로 묶음, 정리 중·실패·대화 중 표시)
- [x] 일지 상세(요약, 아이디어 별표, 할 일 체크, 메모, 전문 펼치기. 먼저 바꾸고 저장 실패 시 되돌림. 화자 이름은 서버 `persona_name`)
- [x] Vitest: 화면 상태(`JournalListScreen`·`JournalDetailScreen`·`core/journal` 테스트)
- [x] Playwright: 목록 → 상세, 별표·완료 표시 저장(`e2e/journal.spec.ts`, 새로고침 뒤 유지 확인)
- [x] 상단 탭 접근성(tablist·tabpanel·화살표 키 이동, 1단계 재검증에서 미룸): aria-controls·roving tabindex·화살표/Home/End
- 참고: 일지 상세의 `persona_name`은 현재 프로필의 페르소나다. 세션에는 페르소나 ID가 없어 페르소나를 바꾸면 지난 전문의 화자 이름도 바뀐다. 페르소나 전환을 지원할 때(5단계 설정) 세션에 persona_id를 저장한다

#### S2-09 추출 품질 평가 세트
- [x] 대화 전문 10개와 사람이 만든 정답(아이디어·할 일)(`server/tests/extract_eval/cases.yaml`: 거절한 제안, 아이디어 없는 대화, 시간 든 할 일, 웹 검색, 부정, 말 끊김, 메모 섞임 포함. 정답은 개발 중 작성, 사용자 검토 필요)
- [x] 비교 스크립트와 재현율 리포트(`run_eval.py`: 앱과 같은 프롬프트·스키마로 추출, 채점 모델(sonnet)이 같은 종류끼리 정답 포함·근거 없는 항목 판정. 첫 측정(1회차, 회차 기록은 `docs/eval/extract-2026-10-15-5.md`): 재현율 26/26, 근거 없는 항목 0/26(엄격히 2/26). 마일스톤 실제 대화 확인에서 찾은 중복 노트·진행 기록 메모를 고친 뒤 대화 12개(저장 노트 사례 2개 추가)로 다시 잼. 최종 `extract-2026-10-15-5.md`: 재현율 27/28(96%, 회차별 96~100%), 근거 없음 0, 저장 노트와 중복 0, 진행 기록 메모 0)

**완료 기준**

| 기준 | 목표값 | 측정값 | 결과 |
|---|---|---|---|
| 웹 대화가 일지로 정리 | 5회 모두 | 5/5(실제 CLI, Playwright 대화 5회, 모두 `done`). 확인 중 찾은 중복 노트·진행 기록 메모는 `e386dfb`에서 고친 뒤 대화 2회로 재확인(중복 0) | 통과 |
| 다음 세션에서 제니가 지난 아이디어를 먼저 언급 | 동작 | 실제 CLI 세션 2~6과 수정 후 재확인 모두 첫인사에서 지난 아이디어·할 일을 먼저 꺼냄 | 통과 |
| 세션 도중 서버 강제 종료 시 직전 턴까지 보존 | 유실 0건 | 유실 0건(실제 CLI: 답변 첫 문장 표시 뒤 SIGKILL, 화면 문장 모두 DB에 `interrupted`로 남고 재기동 후 `--resume`으로 이어짐. 가짜 CLI 테스트 `test_server_kill.py`·Playwright도 동일) | 통과 |
| 추출 재현율(아이디어·할 일) | 80% 이상(첫 측정 후 조정) | 27/28(96%, 회차별 96~100%). 근거 없음 0/27, 저장 노트와 중복 0/2, 진행 기록 메모 0/10(`extract-2026-10-15-5.md`) | 통과(평가 세트가 쉬워 실제 일지로 재측정 필요) |
| Playwright 일지 목록 → 상세, 별표·완료 저장 | 통과 | `e2e/journal.spec.ts` 통과(새로고침 뒤에도 유지) | 통과 |

**마일스톤 종료 체크리스트**
- [x] 유닛 테스트와 Playwright 실제 구동 검증 통과(pytest 348, Vitest 94, E2E 3)
- [x] 실제 Claude CLI로 수동 통합 테스트 1회(대화 5회 + 강제 종료, 수정 뒤 대화 2회씩 2번 재확인)
- [x] `CLAUDE.md`·`client-contract.md`가 실제 코드와 일치
- [x] 구독 사용량 확인(2단계 전체 대략 sonnet 90회·haiku 90회. 대부분 추출 평가 6회차와 통합 확인)
- [x] 서브에이전트 diff 리뷰 반영(작업마다)
- [x] 커밋·push
- [x] 사용자 확인(2026-10-16, 점검 1·2차 수정 반영 뒤)
- [x] 대시보드·추적표·변경 이력 갱신

## 6. 3단계 — 웹 음성 대화

**목표**: 화면을 켠 상태에서 웹 앱으로 핸즈프리에 가까운 음성 대화를 하고, 실제 산책·등산에서 지연과 인식률을 측정한다. 클라이언트 규약을 확정한다.

- 대상 요구사항: FR-01(화면 버튼), FR-02, FR-03, FR-04, FR-06, NFR-01, NFR-03, NFR-04
- 선행 조건: 2단계 완료, 결정 D1(서버 위치)·D2(Whisper 운영)·D3(TTS 서비스), ffmpeg 설치

**작업 목록 — 서버**

| ID | 작업 | 상태 | 산출물 | 커밋 |
|---|---|---|---|---|
| S3-01 | STT(Whisper) | 완료 | `server/app/voice/stt.py`, `server/app/voice/audio.py` | `f89057b` |
| S3-02 | TTS | 완료 | `server/app/voice/tts.py` | `f89057b`, `ef035e2` |
| S3-03 | 음성 턴 스트리밍 | 완료 | `server/app/api/sessions.py`, `server/app/services/conversation.py`, `server/app/voice/speech.py` | `bafcea9` |
| S3-04 | 끼어들기 API | 완료 | `server/app/api/sessions.py`, `server/app/services/conversation.py` | `22f4e5e` |
| S3-05 | 음성 원본 보관 옵션 | 완료 | `server/app/jobs/audio.py`, `server/app/services/conversation.py` | `d8d5876` |
| S3-06 | 클라이언트 설정값 제공 | 완료 | `server/app/api/profile.py`, `server/app/client_config.py` | `2b643a9` |
| S3-07 | 지연 측정 로그 | 완료 | `server/app/api/latency.py`, `server/app/db/models.py`(`TurnLatency`), `web/src/screens/voiceController.ts` | `dce5350` |

**작업 목록 — 웹 클라이언트**

| ID | 작업 | 상태 | 산출물 | 커밋 |
|---|---|---|---|---|
| S3-08 | 세션 상태 머신 | 완료 | `web/src/core/sessionMachine.ts` | `9202e04` |
| S3-09 | 상태 전이 표 픽스처 | 완료 | `shared/fixtures/transitions.json` | `9202e04` |
| S3-10 | AudioInput(VAD·녹음·인코딩) | 완료 | `web/src/platform/audioInput.ts`, `web/src/platform/encodeAudio.ts`, `web/src/core/audio.ts` | `20cd16a` |
| S3-11 | AudioOutput(이어 재생) | 완료 | `web/src/platform/audioOutput.ts` | `8c04f44` |
| S3-12 | LocalQueue(오프라인 큐) | 완료 | `web/src/core/localQueue.ts`, `web/src/platform/localQueue.ts`, `web/src/screens/voiceController.ts`, `server/app/api/sessions.py` | `30b8576` |
| S3-13 | 대화 화면 음성 모드 | 완료 | `web/src/screens/ConversationScreen.tsx`, `web/src/screens/voiceController.ts`, `web/src/screens/VoiceControls.tsx` | `0465493` |
| S3-14 | PWA·정적 서빙·HTTPS 터널 | 완료 | `web/vite.config.ts`, `run.sh --phone`, `stop.sh`, `docs/phone.md` | `0c1af0c`, `dc127a0`, `615f01b` |
| S3-15 | 클라이언트 규약 확정 | 완료 | `docs/client-contract.md`, `server/app/api/events.py`, `server/app/llm/parser.py` | `033b8aa` |
| S3-16 | 음성 흐름 E2E | 완료 | `web/e2e/voice.spec.ts`, `web/e2e/fixtures/` | `fad7711` |
| S3-17 | 일지 정렬·아이디어별 보기(사용자 요청 추가) | 진행 중 | `server/app/jobs/extract.py`, `server/app/jobs/topics_backfill.py`, `web/src/core/journal.ts`, `web/src/screens/JournalListScreen.tsx` | |
| S3-18 | 웹 설정 화면(S5-01 웹 부분 앞당김, 사용자 요청 추가) | 완료 | `web/src/screens/SettingsScreen.tsx`, `server/app/api/profile.py`, `server/app/services/profile.py` | `c96fcca` |
| S3-19 | 일지 목록에서 대화 제목 수정·삭제(사용자 요청 추가) | 완료 | `web/src/screens/JournalListScreen.tsx`, `server/app/api/journal.py`, `server/app/services/conversation.py` | `ffad91e` |
| S3-20 | 대화 화면 모바일 최적화·자동 스크롤·음성 구슬 그래픽(사용자 요청 추가) | 완료 | `web/src/screens/ConversationScreen.tsx`, `web/src/screens/VoiceControls.tsx`, `web/src/index.css` | `4b617c6` |
| S3-21 | 음성 대화 중 글 입력(사용자 요청 추가) | 완료 | `web/src/screens/voiceController.ts`, `web/src/screens/ConversationScreen.tsx` | `223bddc` |
| S3-23 | 일지 인용: 요약·메모에 출처 번호, 인용 목록(사용자 요청 추가, S3-22 롤백 뒤 기존 형식 유지) | 완료 | `server/app/jobs/extract.py`, `server/app/jobs/page_title.py`, `web/src/screens/JournalDetailScreen.tsx` | `9716543` |
| S3-24 | 일지 표시 개선: 결론·알게 된 것·확인할 것(사용자 요청 추가) | 완료 | `server/app/persona/rules.py`, `server/app/jobs/extract.py`, `web/src/screens/JournalDetailScreen.tsx` | `6a72b59` |
| S3-25 | 일지 목록 여러 개 선택·한 번에 삭제(사용자 요청 추가) | 완료 | `web/src/screens/JournalListScreen.tsx`, `web/src/index.css` | `07ccb8d` |
| S3-26 | 끝난 대화 이어서 하기(사용자 요청 추가) | 완료 | `server/app/services/conversation.py`, `server/app/api/sessions.py`, `server/app/persona/prompt.py`, `web/src/screens/JournalDetailScreen.tsx`, `web/src/screens/ConversationScreen.tsx` | `d91f13b`, `4c87241` |
| S3-27 | 이어서 하기 프롬프트 줄이기: 일지 정리 재사용(사용자 요청 추가) | 완료 | `server/app/persona/prompt.py`, `server/app/services/conversation.py` |  `18a9145` |
| S3-28 | 지난 대화 전문 검색 도구 search_conversations(사용자 요청 추가) | 완료 | `server/app/mcp/server.py`, `server/app/persona/rules.py`, `web/src/core/conversation.ts` | `39a8f33` |
| S3-29 | 일지 상세에서 삭제(사용자 요청 추가) | 완료 | `web/src/screens/JournalDetailScreen.tsx`, `web/src/App.tsx` | `c02b920` |
| S3-30 | 지워진 대화 안내(사용자 요청 추가) | 완료 | `web/src/screens/JournalDetailScreen.tsx` | `d177d00` |
| S3-31 | 대화 모델 선택: 설정 화면·말로 바꾸기(사용자 요청 추가) | 완료 | `server/app/llm/manager.py`, `server/app/mcp/server.py`, `server/app/api/profile.py`, `web/src/screens/SettingsScreen.tsx` | |

#### S3-01 STT(Whisper)
- [x] `SttProvider` 인터페이스
- [x] 결정 D2에 따라 OpenAI Whisper API 또는 faster-whisper 구현(OpenAI `gpt-transcribe`, `languages=ko`. 설정 `STT_MODEL`로 변경 가능)
- [x] Opus 업로드를 ffmpeg로 디코딩(WAV 대체 경로 수용). webm·wav·mp3·m4a는 그대로 보내고 그 밖(ogg/opus 등)만 16kHz 모노 webm/opus로 변환(WAV보다 업로드 약 10배 작음), 120초 상한
- [x] 테스트: 모의 응답, 오류·시간 초과
- [x] 실제 API 확인(`RUN_REAL_OPENAI=1 uv run pytest tests/test_voice_real.py`). 2026-10-16 크레딧 충전 뒤 통과: webm·ogg 업로드 모두 원문과 같게 인식. multipart `languages` 필드는 API가 실제로 읽는다(틀린 코드 `xx`는 400, `ko`는 200). 7초 발화 인식 응답은 앱 경로(`gpt-transcribe`, webm) 약 1.3초, 다른 모델·형식 1.5~3초

#### S3-02 TTS
- [x] `TtsProvider` 인터페이스
- [x] 결정 D3의 클라우드 TTS 구현, 문장별 MP3(`gpt-4o-mini-tts`). 마크다운·링크·URL·이모지는 읽기 전에 지움(`speech_text`)
- [x] 보이스·속도·피치는 `jenny.yaml`에서 읽기. OpenAI TTS에 피치가 없어 `pitch`를 지우고 말투 지시 `instructions`로 대신함
- [x] 문장 분할기가 인용 뒤에서 문장을 나누는 문제(`"좋아요." 라고 했어요.`가 두 문장이 됨, 1단계 재검증에서 미룸)
- [x] 테스트: 모의 응답
- [x] 보이스 선택: `uv run python -m tests.voice_samples`로 6종 샘플을 만들어 사용자가 듣고 고름 → `nova`(2026-10-16, `jenny.yaml`)

#### S3-03 음성 턴 스트리밍
- [x] 오디오 업로드 → `transcript` 이벤트(`POST /api/sessions/{id}/turns/audio`, 본문은 오디오 바이트. SSE 전에 인식해 오류·`no_speech`(422)는 JSON. 직전 캐릭터 답변을 인식 힌트로)
- [x] 문장마다 TTS 후 `sentence`(텍스트 + base64 MP3). 음성 세션만, 실패한 문장은 `audio: null`. 인사말 `greeting.audio`·마무리 `closing_audio`도 추가
- [x] 다음 문장 TTS를 병렬로 미리 합성(합성은 띄워 두고 CLI를 계속 읽어, 소리가 된 문장부터 순서대로 보냄. 동시 3개)
- [x] 웹 검색 시작(`tool` 이벤트) 시 "잠깐 찾아볼게요" 안내 음성을 먼저 내보내 7~10초 침묵 줄이기. 프롬프트가 이미 시키므로, 소리 있는 말 없이 검색을 시작할 때만 `tool.start`의 `notice`(페르소나 `voice.search_notice`, 캐시)
- [x] 테스트: 이벤트 순서와 문장 번호(`test_voice_turn.py`, 가짜 음성 백엔드 `VOICE_BACKEND=fake`). Playwright로 브라우저 업로드·MP3 디코드 확인
- 남은 한계: CLI가 오류(시간 초과·비정상 종료)로 끝나면 합성 대기 중이던 문장은 보내지 않는다(보낸 문장까지 저장은 유지). 2026-10-16 가짜 CLI + 실제 OpenAI 음성으로 확인(Playwright, 브라우저 업로드·MP3 디코드): 인식 약 1.3초, `transcript`→`turn`→검색 안내 음성→문장 12개 모두 소리, 인사말·마무리 소리 정상. 이 녹화(`web_search`)는 지금 출처 규칙 이전 답변이라 `Sources:`·링크 줄까지 읽는다(전처리로 사이트 이름만 남음). 실제 CLI 음성 답변에서 출처 목록이 나오지 않는지는 마일스톤 끝 실제 확인 때 본다

#### S3-04 끼어들기 API
- [x] `POST /api/sessions/{id}/turns/{turn_id}/cancel` `{last_played}` → 204(마지막으로 재생한 문장 번호 수신, 오류 `turn_not_found`)
- [x] 들려준 문장까지만 기록, `interrupted=true` 저장. 턴 락 안에서 자른다(바로 뒤 턴의 안내 누락·끝내기 일지가 원문을 읽는 경합 방지). 10초 안에 멈추지 않는 턴은 자르지 않는다
- [x] 끝난 턴의 cancel: 멱등으로 받아 `last_played`로 자른다. 인사말(seq 0)은 문장 번호 없이 재생되므로 자르지 않는다
- [x] CLI 인터럽트(기존 `LlmSession.interrupt`). 다음 턴 CLI 입력에만 "어디까지 들었는지" 앱 안내를 붙인다(직전 답변일 때 한 번, 기록에는 없음)
- [x] 테스트: 중단 후 다음 턴 정상 진행(`test_cancel.py` 12개). 웹은 끼어들 때 cancel API + 말풍선도 들려준 문장까지
- 확인: Playwright 가짜 마이크로 가짜 음성·실제 OpenAI 음성 모두 끼어들기 → 일지·말풍선이 들려준 문장까지(둘째 문장 재생 중 → 첫 문장만)
- 남은 것: 연결 끊기와 cancel이 겹치면 인터럽트가 두 번 간다(가짜 CLI로만 확인, 마일스톤 끝 실제 CLI 점검 때 확인). 끝내기 요청이 락 대기에서 cancel보다 앞서면 일지 정리가 자르기 전 원문을 읽을 수 있다(웹은 cancel을 먼저 보내 보통 문제 없음)

#### S3-05 음성 원본 보관 옵션
- [x] `keep_audio` 설정에 따라 원본 저장(음성 턴 녹음을 `audio_dir/<세션>/<사용자 턴>.<확장자>`, 0600/0700, 사용자 턴 `audio_path`). 실패해도 턴은 계속, 경로를 못 남기면 파일 삭제
- [x] 30일 지난 파일 삭제 작업(`app/jobs/audio.py`, 무발화 감시 루프가 매 주기 실행, `AUDIO_RETENTION_DAYS`). 지우지 못한 파일은 다시 시도
- 확인: Playwright 가짜 마이크로 켜면 webm 28.8KB 저장·디코드 정상, 끄면 미저장. 테스트 11개
- 참고: 켜고 끄는 화면은 웹 설정 화면(S3-18), 안드로이드는 S5-01

#### S3-06 클라이언트 설정값 제공
- [x] `/api/profile` 응답에 VAD 임계값, 무음 1.2초, 소음 0.3초 무시, 재생 중 임계값 상향치 포함(`client` 필드, 읽기 전용. 재생 중 상향은 불리언 대신 `playback_*` 임계값 수치)
- [x] 기본값은 `shared/client-defaults.json`에서 읽기(서버 시작 때 검증, 틀리면 시작하지 않음. `idle_timeout_minutes`는 서버 `IDLE_TIMEOUT_S`로 덮어씀)
- 참고: VAD 수치(0.5/0.35, 재생 중 0.8/0.65)는 시작값이다. 실제 산책 측정에서 조정한다

#### S3-07 지연 측정 로그
- [x] STT, 첫 토큰, 첫 문장 TTS 완료 시각 기록(`turn_latency`, 마이그레이션 0005: 업로드·인식(변환 포함)·첫 글자·첫 문장·끝). 웹이 말 끝 → 요청, 요청 → 첫 소리, 첫 소리가 검색 안내였는지를 보고(`POST …/latency`)
- [x] 턴별 지연 요약 조회(측정값 기록용): `GET /api/latency`(`total_ms` 중앙값·p90, 답변 문장으로 시작한 턴만의 `total_ms_reply`, 단계별 중앙값)
- 확인: 가짜 음성 총 1.3초(그중 무음 대기 1.2초). 실제 OpenAI 음성·가짜 CLI 1턴 총 5.8초(말 끝 → 요청 1.3초(무음 대기 1.2초 포함), 인식 2.9초, 첫 소리는 검색 안내). 실제 CLI·산책 측정은 마일스톤 끝

#### S3-08 세션 상태 머신
- [x] 상태: 대기·듣기·처리 중·말하기·쉬기·오프라인 보관·정리(코드 이름 `idle`·`listening`·`processing`·`speaking`·`paused`·`offline`·`closing`)
- [x] 브라우저 API 없는 순수 함수(이벤트 → 다음 상태 + 부수효과 명령). 이벤트·명령 목록과 플랫폼이 지킬 약속은 규약 4절
- [x] Vitest: 전이 표 픽스처 기반 테스트(사례 22개, 모든 상태×이벤트 조합 예외 없음, 모르는 이벤트 무시)
- 참고: 쉬는 중에도 30분 무발화면 끝낸다(사용자 결정 2026-10-16, 서버와 같음). 텍스트 모드 쉬기 문구에 안내 추가
- 참고: 인사말은 시작 응답으로 오므로 플랫폼이 재생을 시작하며 `session_started {turnId}`를 보낸다. 오프라인 큐의 세션 소속·끝내기 전 비우기는 S3-12에서 정한다

#### S3-09 상태 전이 표 픽스처
- [x] 입력 이벤트 → 기대 상태 표를 JSON으로 작성(사례마다 단계별 이벤트, 기대 상태·명령 목록(순서 포함)·선택 context)
- [x] 4단계 Kotlin 테스트가 같은 파일을 읽도록 형식 고정(`version: 1`, 이벤트·명령은 `type` 구분 객체, 값 없음은 null)

#### S3-10 AudioInput(VAD·녹음·인코딩)
- [x] `getUserMedia`(에코 캔슬·노이즈 억제·자동 게인). 권한은 모델을 불러오기 전에 받는다. HTTPS가 아니면 `mic_unavailable`
- [x] `@ricky0123/vad-web` 0.0.31(Silero v5), 서버 설정값 적용. 모델·worklet·onnxruntime wasm은 `/vad/`에서 직접 서빙(약 16MB, CDN 없음). `speech_start`는 `min_speech_ms`가 이어진 뒤(`onSpeechRealStart`)
- [x] 16kHz 모노 → Opus(WebCodecs `AudioEncoder`, mediabunny 1.61.0로 webm), 미지원 시 WAV. 9.3초 발화 28.8KB(WAV 298KB), 서버 인식 응답 0.87초(WAV 1.57초)
- [x] 재생 중 VAD 임계값 상향(`setOptions`)
- [x] 음성 턴 업로드 `sendAudioTurn`(`web/src/api/conversation.ts`)
- 확인: Playwright 가짜 마이크(유나 목소리 wav)로 발화 감지 → Opus → 실제 OpenAI 인식 원문 일치, `stop` 뒤 15초 이벤트 없음. E2E `e2e/audioInput.spec.ts`(Opus 인코딩·디코드, `/vad/` 서빙)
- 발견·수정: mediabunny `new Quality(24000)`은 비트레이트가 아니라 품질 배수라 조용히 WAV로 떨어졌다(실제 구동에서 발견, `{bitrate}`로 수정)
- 남은 것: iOS Safari는 사용자 동작 안에서 오디오를 열어야 하므로 S3-14 폰 확인 때 본다(안드로이드 A35만 확인, iOS는 미확인)(화면 연결·오류 표시는 S3-13에서 끝남)

#### S3-11 AudioOutput(이어 재생)
- [x] Web Audio API로 문장 MP3를 순서대로 이어 재생(넣는 즉시 병렬 디코드, 소리 없음·디코드/재생 실패는 길이 0)
- [x] 재생한 문장 번호 추적(`sentence_played`·`playback_idle`), 즉시 정지(이벤트 없음)
- [x] 자동 재생 제한·오디오 중단에도 대기열이 멈추지 않음(다시 켜기 0.5초, 끝 알림 없으면 길이 + 2초)
- 확인: 실제 Chromium에서 MP3 3개 + 소리 없는 문장의 이벤트 순서·간격, 재생 중 정지

#### S3-12 LocalQueue(오프라인 큐)
- [x] IndexedDB에 발화 보관, 실패 횟수 기록(넣기 실패 시 메모리, 읽기·지우기는 합쳐 봄, 30일 기한)
- [x] 온라인 복구 시 순서대로 전송: 사용자 결정(2026-10-16)으로 **보통 턴처럼 차례로 보내 캐릭터가 대답**한다. 상태 머신에 큐 전송을 넣음(`sendQueued`·`queue_sent`·`queue_send_failed`·`connected`·`sendingQueued`, 전이 표 사례 갱신·추가). 복구 감지는 `online` 이벤트 + 끊긴 동안 30초마다 health 확인
- [x] `speechSynthesis`로 오프라인 안내 문구 재생(6초 상한, 끝내면 멈춤)
- [x] 대답할 수 없는 말(서버가 대화를 끝냄·새로 고침·5번 실패)은 `POST /api/sessions/{id}/turns/audio/record`로 기록만 남김(끝난 대화면 일지 다시 정리, 정리 도중 들어오면 다시 돌기)
- 확인: Playwright `setOffline`으로 끊긴 동안 3번 말함 → 보관 3개·안내 → 복구 1.3초 만에 차례로 대답, 일지 사용자 3·대답 3(유실 0). 끊긴 채 끝내기 → 복구 뒤 기록만 남김
- 남은 것(드묾): 포기 표시 저장이 계속 실패하면 같은 말을 되풀이해 보냄, 정리 다시 돌기 5번을 다 쓰면 앱 재시작 때까지 pending

#### S3-13 대화 화면 음성 모드
- [x] 큰 버튼(한 번 = 시작/끼어들기, 0.7초 길게 = 종료), 상태 표시. "대화 끝내기"·정리 중 "그만 기다리기" 보조 버튼. 시작 화면에서 음성/글 선택(고른 방식으로 미리 준비)
- [x] 알림음(`shared/sounds/` listen·saved·offline, ffmpeg 사인파)
- [x] Screen Wake Lock, Media Session 보조(이어폰 버튼 실동작은 S3-14 실기기에서 확인)
- [x] 명령 실행 컨트롤러 `voiceController.ts`: 음성 턴 SSE → 머신 이벤트·말풍선, 끼어들기는 요청 연결 끊기(cancel API는 S3-04), 마이크 오류는 대화를 마치고 이유 표시, 서버 VAD 설정 적용. 네트워크 오류는 S3-12 전까지 오류로 알리고 다시 듣는다(발화 유실)
- [x] 음성 모듈(압축 약 150KB)을 지연 로딩해 첫 화면 JS를 그대로 유지(압축 87KB), 불러오기 전에는 음성 시작 버튼을 막음
- 확인: Playwright 가짜 마이크로 개발 서버·빌드본(FastAPI 서빙) 모두 시작→인사말→듣기→발화→답변 재생→끼어들기→길게 눌러 종료. 실제 OpenAI 음성으로 3턴(인식 원문 일치, 실제 MP3 이어 재생)
- 발견·수정: 새 DB에서 `/api/profile` 동시 호출 시 persona UNIQUE 500(서버 `sync_persona` 세이브포인트), 처리 중 탭이 검색 안내 음성을 멈추지 않음(상태 머신·전이 표 수정)

#### S3-14 PWA·정적 서빙·HTTPS 터널
- [x] vite-plugin-pwa 1.3.0 설정(앱 셸 precache, `/vad/`는 처음 쓸 때 CacheFirst, `/api`·`/internal` 제외, 자동 새로 고침 없음), 앱 아이콘·manifest
- [x] FastAPI 정적 서빙 확인(sw.js·webmanifest·wasm 형식, 오프라인 다시 열기)
- [x] 결정 D1(집 Mac + Tailscale Serve, `./run.sh --phone`, `docs/phone.md`)에 따른 서버 배치와 HTTPS 터널. 확인(10-17, Mac에서 ts.net 주소): 서비스 워커·오프라인 다시 열기·음성 턴 2회·vad 캐시, `/internal/mcp/` 403 실측. Serve가 붙이는 헤더는 X-Forwarded-For/Host/Proto·Tailscale-User-*. 앱 도구 MCP 경로 `/internal/*`는 터널·리버스 프록시에서 막는다(앱도 전달 헤더가 붙은 MCP 요청은 403). 서버 포트가 8000이 아니면 `INTERNAL_BASE_URL`을 맞춘다(틀리면 CLI가 도구 없이 대화한다)
- [x] 폰 브라우저에서 마이크 권한 확인(2026-10-17 사용자, Galaxy A35 Chrome·Tailscale로 음성 대화 정상). 홈 화면 추가·이어폰 버튼(Media Session)은 따로 확인하지 않음 — 실제 산책 때 본다

#### S3-15 클라이언트 규약 확정
- [x] API, SSE 이벤트 JSON 스키마(도구별 `summary`를 `kind`로 구분하는 타입으로 고정: `web_search`·`web_fetch`·`result`, 알 수 없으면 null), 오디오 형식. 출처 호스트 추출을 웹에서 서버로 옮김(`sources`·`host`)
- [x] 상태 머신·전이 표(version 1, 사례 27개), 설정값, 알림음·안내 문구가 코드·`shared/` 파일과 맞는지 확인
- [x] `docs/client-contract.md` 확정본(초안 표시 정리, 바꾸는 규칙, 폰 접속·PWA, 낡은 경로·확인 결과 갱신)

#### S3-16 음성 흐름 E2E
- [x] Playwright 가짜 마이크(녹음 파일 주입) 설정: 프로젝트 `voice`, `web/e2e/fixtures/utterance.wav`(say -v Yuna + 무음, 약 24초 주기, `make-utterance.sh`)
- [x] 발화 → 답변 → 끼어들기 → 오프라인 복구 흐름 + 끝내기(`web/e2e/voice.spec.ts`, 약 35초). 전체 E2E 7개 3회 연속 통과

#### S3-17 일지 정렬·아이디어별 보기
사용자 요청(2026-10-17)으로 더한 작업이다. 같은 아이디어를 여러 날 이야기하면 일지가 흩어져 보인다. 문자열 중복 판정과 태그로는 표현이 다른 같은 아이디어를 묶지 못했다.
- [x] 서버: 대화에 아이디어 주제(`topics`)를 붙인다(일지 정리 때 기존 주제 목록에서 고르게 함, 마이그레이션 0006, 목록 API `topics`)
- [ ] 서버: 기존 일지 한 번 분류(`python -m app.jobs.topics_backfill`, 실제 CLI 1회)
  - 스크립트는 만들었다(NULL=미분류, 한 번에 200개). 사용자 DB 실행은 승인 후 한다
- [ ] 웹: 일지 목록 보기 전환(날짜별·아이디어별)과 순서 전환(최신순·오래된순), 주제 없는 대화는 "기타"

#### S3-18 웹 설정 화면
사용자 요청(2026-10-17)으로 S5-01의 웹 부분을 앞당겼다(안드로이드 설정 화면은 5단계 S5-01). 폰으로 산책을 시작하면 호칭·관심사·음성 원본 보관을 화면에서 바꿀 일이 생긴다. 보이스는 저장만 되고 합성에 쓰이지 않았고, 말 속도는 저장 칸이 없었다.
- [x] 서버: 말 속도 칸(`speaking_rate`, 마이그레이션 0007), 보이스 검증(OpenAI 보이스 13종), `GET /api/voices`·보이스 미리 듣기, 프로필 보이스·속도를 음성 합성에 적용(턴·인사말·마무리, 턴마다 읽어 대화 중 변경도 다음 답변부터)
- [x] 웹: 설정 화면(호칭, 관심사 칩, 보이스·미리 듣기, 말 속도 느리게·보통·빠르게, 음성 원본 보관). 바뀐 필드만 저장(`web/src/core/settings.ts`)
- [x] 실제 OpenAI로 속도 차이 확인(같은 문장, 기본 6.67초): 0.85+지시 8.93초(+34%), 1.2+지시 6.26초, 1.2+강한 지시 6.02초, 1.35+강한 지시 5.28초(-21%) → "빠르게"는 1.35와 강한 지시로 정함
- 확인: Playwright(가짜 CLI·음성, 빌드본)로 설정 저장·새로 고침 뒤 유지·미리 듣기(audio/mpeg)

#### S3-19 일지 목록에서 대화 제목 수정·삭제
사용자 요청(2026-10-17)으로 더한 작업이다. 자동으로 붙은 제목을 고칠 수 없고 쓸모없는 대화를 지울 방법이 없었다.
- [x] 서버: `PATCH /api/journal/{id}`(제목, 1~200자), `DELETE /api/journal/{id}`(노트·전문·지연 기록·녹음 파일까지, 진행 중이면 409 `session_active`, 쉬는 중이면 CLI 정리, 돌던 일지 정리 취소). 고친 제목은 다시 정리해도 유지(`title_edited`, 마이그레이션 0008)
- [x] 웹(모바일 우선): 제목(연필 표시)을 누르면 그 자리에서 고치고 포커스가 떠나면 저장(Enter 저장·Esc 취소, 실패 시 되돌림), 카드의 나머지를 누르면 상세. 오른쪽 쓰레기통은 확인 창 뒤 삭제, 진행 중 대화는 누르면 지울 수 없는 이유를 글로 안내. 터치 영역 44px, 입력 16px
- 삭제는 턴·오프라인 기록과 같은 잠금을 쥐고 한다(턴 중이면 409 `turn_in_progress`). 돌던 정리를 멈추고 결과 쓰기가 끝난 뒤 지운다
- 확인: Playwright E2E(폰 화면: 제목 수정 → 새로고침 뒤 유지 → 상세 열기 → 쓰레기통 삭제 → 새로고침 뒤 없음)

#### S3-20 대화 화면 모바일 최적화·자동 스크롤·음성 구슬 그래픽
사용자 요청(2026-10-17)으로 더한 작업이다. 음성 대화에서 하단 패널(약 300px)이 마지막 말풍선을 가렸다(`scroll-margin-bottom` 160px 고정).
- [x] 자동 스크롤: 페이지 맨 아래로 내림(고정 패널이 제자리에 놓여 가리지 않음). 패널 높이 변화(ResizeObserver)·키보드(visualViewport)에도 다시 내림, 위로 올려 읽는 중이면 그대로
- [x] 모바일 레이아웃: 시작·끝 화면 꽉 찬 폭 버튼(52px), 메신저형 한 줄 입력창(최대 약 5줄로 늘어남, 16px)+둥근 보내기 버튼, 작은 끝내기 버튼
- [x] 음성 구슬: 그라데이션 구슬+광채+물결 고리, 상태별 CSS 애니메이션(듣기 숨쉬기·물결, 생각 회전, 말하기 출렁임, 쉬기·끊김 회색), 움직임 줄이기 설정 존중
- 확인: Playwright 폰 화면(Pixel 7) 캡처, E2E에 "마지막 말풍선이 하단 패널 위에 보임"(글·음성·탭 복귀) 추가

#### S3-21 음성 대화 중 글 입력
사용자 요청(2026-10-17)으로 더한 작업이다. 시끄러운 곳이나 고유명사·링크처럼 말로 하기 어려운 내용을 음성 대화 중에도 글로 보낸다. 서버 변경 없음(음성 대화면 글 턴에도 답변 음성을 만든다).
- [x] 컨트롤러 `sendText`: 글을 말 한 번처럼 `speech_end`로 머신에 넣고 글 턴 API로 보낸다(머신·전이 표 그대로). 말하는 중이면 끼어든 뒤, 쉬는 중이면 다시 들은 뒤. 처리 중·오프라인이면 받지 않음, 실패하면 보관하지 않고 글을 입력창에 돌려줌
- [x] 화면: 음성 패널에 메신저형 입력줄(글 대화와 같은 입력줄), 보낼 수 없을 때 이유 안내. 규약 4절에 규칙 추가(안드로이드도 같은 규칙)
- 확인: 컨트롤러 단위 테스트 4개, E2E `typing.voice.spec.ts`(글 전송 → 답변 → 다시 듣기), Playwright 폰 화면 캡처

#### S3-23 일지 인용(출처 번호·인용 목록)
사용자 요청(2026-10-17)으로 더한 작업이다. S3-22(전면 개편)를 롤백한 뒤, 기존 형식(요약 1~3줄 + 노트)은 그대로 두고 검색으로 알게 된 요약 줄·메모 끝에 근거 출처 번호 [1][2]를, 맨 아래 "인용:"에 [번호] 기사 제목 URL을 붙인다.
- [x] 출처 저장: 대화 중 웹 검색 링크·읽은 페이지를 답변 턴에 저장(`turn.sources`, 마이그레이션 0011)
- [x] 추출: 요약·메모를 {text, sources}로 받고, 서버가 번호를 실제 출처에 맞춰 검증해 출처 URL로 저장(`summary_cites`, `citations`, `note.cites`)하고, 번호는 조회할 때 남은 요약·메모 기준으로 매김(다시 정리·중복 메모로 번호가 어긋나거나 고아 인용이 생기지 않게). 요약 줄 평문은 그대로(목록·기억 블록 영향 없음)
- [x] 인용 제목 보완: 검색 결과 제목이 도메인뿐이면 정리할 때 그 페이지의 og:title·<title>을 읽음(인용된 것만, 공인 주소·기본 포트만, 리다이렉트 단계마다 검사, html.parser, 테스트·E2E는 끔. 남은 위험: DNS 리바인딩)
- [x] 웹: 일지 상세의 요약·메모 끝에 [n], 노트 아래 "인용:" 목록(제목 링크·URL)
- 확인: 단위 테스트, E2E(가짜 CLI 녹화), 실제 CLI 검색 대화 1회(검색 내용 문장에만 번호, 실제 기사 제목·URL), 추출 평가 재현율 28/28(100%, 직전 96%, [extract-2026-10-17](eval/extract-2026-10-17.md) 1회차)

#### S3-24 일지 표시 개선(결론·알게 된 것·확인할 것)
사용자 요청(2026-10-17)으로 더한 작업이다. 실제 일지(등산·IT 뉴스)에서 첫 줄이 검색 과정, 같은 사실이 요약·메모에 반복, 확인된 것과 미정이 섞임, 출처가 문장에 섞이는 문제가 보였다.
- [x] 정리: 결론 1줄 → 알게 된 것(대상별 "대상: 내용", 출처 번호) → 확인할 것(미정·못 찾음·원문 확인 필요). 사실은 한 곳에만, 검색 과정·대화 설명·출처 이름 금지, 메모는 사용자가 알려 준 것만. 아이디어·할 일은 결론과 겹쳐도 빼지 않음
- [x] 저장: 요약 줄 = 결론 + 알게 된 것(목록·기억 블록 그대로), `conversation_session.checks`(마이그레이션 0012, NULL = 예전 형식). 예전 형식 일지도 다시 정리 가능('다시 정리' 요청으로 시작한 정리만 노트를 다시 넣지 않음, 늦게 온 턴으로 다시 도는 정리는 노트를 뽑음), 다시 정리 때 읽어 둔 기사 제목을 도메인으로 덮지 않음
- [x] 웹: 결론 굵게 → 알게 된 것 → 확인할 것 → 노트 → 인용 → #태그(맨 아래), 목록 미리보기 2줄, 예전 형식 다시 정리 버튼
- 확인: 추출 평가 6회차(재현율 28/28, 근거 없음 0/30, 결론 진행 기록 0/13, 사실 되풀이 1/12, [extract-2026-10-17](eval/extract-2026-10-17.md) 회차 표), 실제 CLI 뉴스 검색 대화 2회
- 남은 문제(다음 작업 후보): 사용자가 "정리해 둬"라고 하면 대화 중 save_note로 긴 메모 한 덩어리(검색 과정 포함)가 저장되고, 정리 단계는 겹치지 않게 그 사실을 알게 된 것에 다시 쓰지 않아 결론에 과정이 섞임. 뉴스 모음 페이지는 주소와 페이지 제목이 달라 인용 제목이 엉뚱할 수 있음

#### S3-25 일지 목록 여러 개 선택·한 번에 삭제
사용자 요청(2026-10-18)으로 더한 작업이다. 일지를 하나씩 쓰레기통·확인창으로 지우기 번거로웠다. 서버 변경 없음(항목별 `DELETE /api/journal/{id}`를 차례로 부른다. 대화별 잠금·정리 취소·409가 이미 항목 단위라 일괄 API를 두지 않음).
- [x] 선택 모드: 목록 제목 줄의 "선택" → 카드 전체가 체크박스 label(어디를 눌러도 선택, 상세 열기·제목 수정·쓰레기통은 숨김). 진행 중인 대화는 고를 수 없고 누르면 이유 안내
- [x] 아래 고정 막대: N개 선택 · 전체 선택/해제(진행 중 제외) · 삭제 (N) · 취소. 확인 뒤 차례로 지우며 "지우는 중… k/N", 지운 항목은 바로 빠짐, 404는 지운 것으로, 실패한 항목은 선택된 채 남기고 알림, 다 지우면 모드 닫힘. 지우는 동안 정리 중 폴링 응답이 지운 항목을 되살리지 않음
- [x] 처리 중(제목 저장 중)인 항목은 말없이 빠지지 않고 실패로 남김, 삭제 버튼 연속 클릭 가드, 진행 중 대화의 비활성 체크박스 자리를 눌러도 안내(서브에이전트 리뷰 반영)
- 확인: Vitest 3개(선택·전체 선택·차례 삭제·부분 실패, 전체 252), E2E(대화 2개 골라 지우기, 새로고침 뒤 없음, 전체 10개 4회 통과), Playwright 폰 화면(Pixel 7, 가짜 CLI 8300): 버튼 44px, 가로 스크롤 없음, 진행 중 대화 안내, 1개만 지우고 새로고침 뒤 반영

#### S3-26 끝난 대화 이어서 하기
사용자 요청(2026-10-18)으로 더한 작업이다. 일지 상세의 '대화 전문 보기' 아래에서 끝난 대화를 같은 세션으로 다시 열어 글·음성으로 이어서 말한다(사용자 결정: 같은 일지에 이어 붙임, 글·음성 둘 다). 끝낼 때 CLI 기록 파일을 지우므로 `--resume` 대신 저장된 전문을 새 프롬프트에 넣는다.
- [x] 마일스톤 1(서버): `POST /api/sessions/{id}/reopen {mode}`. 프롬프트 "이어서 하는 대화" 블록(전문 뒤에서부터 2만 자, 기억에서 자기 요약 제외), 재개 인사말(`REOPEN_GREETING_INSTRUCTION`, `turn.greeting`, 끼어들어도 안 잘림), 턴 잠금 아래 상태 재확인·돌던 정리 멈춤·상태와 프롬프트 한 번에 커밋, 실패하면 끝난 상태·정리 상태 복원. 다시 끝내면 정리를 다시 함(노트 유지·새 노트만, 고친 제목 유지), 마무리 개수는 다시 연 뒤 노트만(`reopened_at`, 마이그레이션 0013). 끝내기는 잠금을 쥐고 상태를 다시 읽어 그사이 다시 연 대화의 CLI를 닫지 않음, 정리를 기다리던 끝내기 응답은 다른 쪽이 정리를 멈춰도 깨지지 않음, 무발화 감시는 다시 연 시각도 활동으로 봄
- [x] 마일스톤 2(웹): 일지 상세 전문 아래 "글로 이어서"·"음성으로 이어서"(끝난 대화만, 48px), 대화 화면 핸들 `continueWith`(이전 말풍선 + 재개 인사말, 글은 입력창 포커스, 음성은 상태 머신 변경 없이 시작 명령에서 다시 열기 API), 다른 대화가 진행·시작·끝내는 중이면 안내, 같은 대화면 화면만 옮김, 음성 준비 중 안내
- 확인(마일스톤 1): pytest 631(재개 12개 포함), 가짜 CLI 서버(8300)로 시작 → 끝내기 → 음성으로 다시 열기 → 다시 열기 409 → 다시 끝내기(정리 재실행, 노트 중복 없음) 확인
- 확인(마일스톤 2): Vitest 258, E2E 12개 3회 연속(글로 이어서 → 한 턴 → 다시 끝내기 → 같은 일지에 쌓임, 음성으로 이어서 → 듣기), Playwright 폰 화면(Pixel 7) 캡처. 실제 CLI 1회(2026-10-18, CLI 호출 약 7회): 재개 인사가 직전 이야기("누구한테 제일 반가울지 얘기하던 중")를 짚고, 다음 답이 앞 맥락을 이어받음, 다시 정리한 요약이 새 대화까지 담고 노트 중복 없음, 날짜 유지
- 남은 한계: 내용을 크게 고친 노트는 다시 정리할 때 원래 표현으로 되살아날 수 있음(정리 지시의 `<저장한 노트>`에 맡김, 기존 한계와 같음). 일지 다시 정리·오프라인 기록이 다시 열기와 겹치면 진행 중인 일지가 잠깐 '정리 중'으로 보일 수 있음(다시 끝내면 정상)

#### S3-27 이어서 하기 프롬프트 줄이기(일지 정리 재사용)
사용자 요청(2026-10-18)으로 더한 작업이다. S3-26은 다시 열 때 전문을 최대 2만 자까지 프롬프트에 넣어, 이어서 하는 동안 매 턴 다시 읽혔다. 끝낼 때 만든 일지 정리를 요약으로 재사용한다(LLM 추가 호출 없음).
- [x] 정리를 마친(DONE) 일지이고 전문이 4천 자를 넘으면 `<정리>`(제목·요약·확인할 것·노트, 완료 표시) + 최근 원문 4천 자(`RECENT_LIMIT`), 앞은 "(앞부분은 위 정리로 대신함)". 전문이 그 안에 들어가면 정리 없이 전문만(붙이면 오히려 김). 정리 중·실패·정리 전이면 전처럼 전문 2만 자. 최근 원문은 한도를 넘어도 마지막 두 줄은 남기고(너무 긴 줄은 뒷부분), 노트는 최근 20개·긴 내용을 잘라도 완료 표시 유지(서브에이전트 리뷰 반영)
- 확인: pytest 639, 스냅샷 `prompt_jenny_text_reopen_summary.txt`. 측정(사용자 80자·답변 220자 40회 주고받은 대화): 이어서 블록 12,835자 → 4,744자, 프롬프트 전체 15,052자 → 6,961자. 실제 CLI(2026-10-18, 호출 약 9회, 검증용으로 최근 원문 한도를 600자로 낮춰 실행): 재개 인사가 직전 이야기를 짚고, 정리에만 남은 앞부분(장터 이름·공동 운영자·남은 책 기부·첫 장터 날짜)을 물으면 정확히 답함. 이 확인 중 요약(줄바꿈으로 이은 글)을 글자 단위로 쪼개 넣던 버그를 찾아 고치고 테스트를 강화함
- 남은 한계: 정리에 들어가지 않은 앞부분의 세부는 기억하지 못함. 끝내고 정리가 끝나기 전에 다시 열면 전문 갈래로 감

#### S3-28 지난 대화 전문 검색 도구(search_conversations)
사용자 요청(2026-10-18)으로 더한 작업이다. "지난번에 이런 이야기 했잖아"라고 물을 때 그 내용이 프롬프트(기억 요약·이어서 하기 정리)와 노트에 없으면 찾을 방법이 없었다. 평소에는 요약만 들고(S3-27), 필요할 때만 원문을 찾는다.
- [x] MCP 도구 `search_conversations(keyword)`: 모든 대화(기간 제한 없음)의 주고받은 말에서 낱말(최대 3개) AND, 최신순 8건, 날짜·제목·(지금 대화)·앞뒤 말, 결과 4천 자 상한, 기록 속 지시 무시 머리말. 지금 대화는 이번 질문보다 앞선 말만(방금 질문·답이 결과를 차지하지 않게), 읽기 전용(대화 턴 도중 DB 쓰기 잠금 없음), DB 오류는 고정 문구
- [x] 역할 규칙: 기억·기록에 없는 지난 이야기를 꺼내면 이 도구로 찾고, 핵심 낱말 1~2개, 못 찾으면 다른 낱말로 한 번 더, 그래도 없으면 지어내지 않음. 음성은 말없이 찾기 시작하면 안내 음성. 웹 도구 알림 "지난 대화에서 '…' 찾는 중…"
- 확인: pytest 644, Vitest 261, E2E 12. 실제 CLI(2026-10-18, 호출 약 9회): 새 대화에서 지난 대화의 사소한 내용("파란 우산 할아버지", 반포대교)을 물으면 도구로 찾아 정확히 답함, 없는 이야기(스카이다이빙)는 대화·노트·다른 낱말로 찾아본 뒤 못 찾았다고 답함(지어내지 않음)
- 남은 한계: 키워드 검색이라 표현이 다르면(동의어·다른 어미) 못 찾을 수 있음. 지운 대화는 찾지 못함. 대화가 아주 많이 쌓이면 전문 검색 색인(FTS5) 검토

#### S3-29 일지 상세에서 삭제
사용자 요청(2026-10-18)으로 더한 작업이다. 삭제가 목록에서만 돼서, 상세에서 읽다가 지우려면 목록으로 돌아가 찾아야 했다. 서버 변경 없음.
- [x] 상세 맨 아래 꽉 찬 "이 대화 삭제"(48px, 빨간 테두리 보조 버튼). 목록과 같은 확인 문구, 지우는 중 표시, 성공·404면 목록 탭으로(지운 항목 빠짐). 진행 중인 대화는 이유만 안내, 실패(409 등)는 문구를 보이고 머무름. 지우는 동안 이어서·다시 정리 버튼을 막고, 그사이 화면을 떠났으면 응답이 와도 목록으로 옮기지 않음(서브에이전트 리뷰 반영)
- 확인: Vitest 264, E2E 13(대화 → 일지 보기 → 삭제 → 목록, 새로고침 뒤에도 없음), Playwright 폰 화면(Pixel 7, 가짜 CLI 8300) 캡처
- 남은 문제: 대화 화면이 지운 대화를 '끝남'으로 들고 있으면 그 화면의 "일지 보기"가 없는 일지를 연다(목록 삭제에도 있던 문제) → S3-30에서 안내로 처리

#### S3-30 지워진 대화 안내
사용자 요청(2026-10-18)으로 더한 작업이다. 지운 일지를 대화 탭의 "일지 보기"나 오래된 목록 항목으로 열면 서버 오류 문구와 소용없는 "다시 불러오기"가 보였다.
- [x] 일지 상세가 불러오기·정리 중 자동 새로고침·다시 정리에서 404 `session_not_found`를 받으면 "지워진 대화예요. 일지 목록에서 다른 대화를 골라 주세요." + "일지 목록으로"(포커스 이동, 남은 저장 오류 지움, 폴링 멈춤). 다른 오류(다른 404 포함)는 기존대로 오류 문구 + 다시 불러오기
- 확인: Vitest 267, E2E 14(글 대화 끝내기 → API로 삭제 → 대화 탭 "일지 보기" → 안내 → 목록으로), 폰 화면 캡처

#### S3-31 대화 모델 선택(설정 화면·말로 바꾸기)
사용자 요청(2026-10-18)으로 더한 작업이다. 대화 모델이 서버 설정값(`LLM_CHAT_MODEL`)으로 고정돼 바꾸려면 서버를 다시 띄워야 했다. 결정(사용자 위임): haiku·sonnet·opus, 대화 중에 바꾸면 다음 답변부터.
- [x] 프로필 `chat_model`(null=서버 기본, 마이그레이션 0014), API `chat_model`·`default_chat_model`. 턴·인사말·다시 열기·미리 띄우기가 매번 프로필 모델을 쓰고, 살아 있는 CLI의 모델이 다르면 답변 사이(턴 잠금 아래, 답변 중이 아닐 때)에 같은 CLI 대화 기록으로 `--resume`해 새 모델로 다시 띄움. 미리 띄운 CLI는 모델이 다르면 버림
- [x] MCP `set_model`: "빠른 모델로"·"오푸스로" 같은 말에 바꾸고 다음 답변부터 적용. 사용자 턴 안에서만, 발화에 모델 이름이 있으면 그 모델로만, 이름 없이 "모델"만 있으면 고른 모델로(검색 결과 속 지시로 바뀌지 않게). 역할 규칙 한 줄, 도구 알림 "모델 변경: opus"
- [x] 웹 설정 화면 "대화 모델" 라디오(기본(서버 기본값)·빠름(haiku)·균형(sonnet)·똑똑함(opus), 44px), 저장 안내 문구
- 확인: pytest 656, Vitest 270, E2E 14, Playwright 폰 화면(설정 저장). 실제 CLI(2026-10-18, 호출 약 8회, opus 1회): "오푸스 모델로 바꿔 줘" → set_model → 다음 턴 CLI가 `--model opus`로 다시 떠서 앞 대화("강아지 콩, 세 살")를 기억, "빠른 모델로" → haiku로 다시 뜨고 기억 유지, 바꾼 직후 첫 답변 3.2초
- 남은 한계: 바꾼 직후 첫 답변은 CLI 재기동만큼 늦고 그동안 끼어들기 대상이 없음(크래시 복구와 같음). opus는 평소에도 느려 음성 산책에는 부담

**완료 기준**

| 기준 | 목표값 | 측정값 | 결과 |
|---|---|---|---|
| 화면을 켠 채 실제 산책·등산 완주, 일지 생성 | 1회 | | |
| 말을 끝낸 뒤 제니 음성 시작까지(NFR-01) | 3초 이내(중앙값) | 책상 측정(2026-10-17, 실제 CLI·OpenAI, 2턴): 중앙값 6.6초 = 무음 대기·전송 준비 1.25 + 인식 1.1~1.5 + 인식 뒤 CLI 첫 글자 약 1.3 + 첫 문장 완성·합성 약 2.7. 산책 실측 전 | 미달(개선 필요) |
| 등산로 녹음 기준 발화 인식률(NFR-03) | 목표 90%, 측정값 기록 | | |
| 비행기 모드 3턴 이상 후 복구 시 기록 유실(NFR-04) | 0건 | 시뮬레이션 0건(Playwright 오프라인 3턴, S3-12). 폰 실측 전 | |
| 제니 목소리로 인한 끼어들기 오작동 | 횟수 기록 | | |
| 음성 답변 길이(상한 5문장, S1-11에서 4→5 조정)가 걸으며 듣기에 길지 않은지 | 체감 기록 | | |
| Playwright 음성 흐름 E2E | 통과 | 발화·답변·끼어들기(들려준 문장까지 자름)·오프라인 보관 복구·끝내기, 전체 E2E 7개 3회 연속 통과(음성 약 35초) | 통과 |

- NFR-01 측정 방법: 산책 뒤 `GET /api/latency`의 `summary.total_ms.median`(검색 턴 제외는 `total_ms_reply`). 말 끝은 VAD가 끝을 알아챈 때에서 무음 대기(1.2초)를 뺀 시각이라, 무음 대기도 3초 안에 들어간다(S3-07).

**마일스톤 종료 체크리스트**
- [x] 유닛 테스트와 Playwright 실제 구동 검증 통과(pytest 565, Vitest 234, E2E 7, S3-17 병합 전 기준 — 병합 뒤 다시 돌린다)
- [ ] 폰 브라우저 실제 산책 테스트(폰 음성 대화 연결은 S3-14에서 확인)
- [x] 실제 Claude CLI로 수동 통합 테스트 1회(2026-10-17): 음성 인사말·발화 2턴·끼어들기(연결 끊김+cancel 겹침, 경고 없음)·끝내기·일지 정리, 음성 세션 검색 답변(출처는 사이트 이름으로만, 링크 없음)
- [ ] `CLAUDE.md`·`client-contract.md`가 실제 코드와 일치(client-contract는 S3-15 확정본, S3-17 병합 뒤 둘 다 다시 대조)
- [ ] 구독 사용량 확인
- [ ] 서브에이전트 diff 리뷰 반영
- [ ] 커밋·push
- [ ] 사용자 확인, 결정 D4·D7 확정
- [ ] 대시보드·추적표·변경 이력 갱신

## 7. 4단계 — 안드로이드 포팅

**목표**: 같은 서버와 규약으로 안드로이드 네이티브 앱을 만들어, 화면을 끄고 이어폰만으로 등산 중 대화를 끝낸다.

- 대상 요구사항: FR-01(이어폰 버튼), FR-05, NFR-02, NFR-05
- 선행 조건: 3단계 완료, 결정 D7(포팅 시작 기준) 충족, `client-contract.md` 확정

**작업 목록**

| ID | 작업 | 상태 | 산출물 | 커밋 |
|---|---|---|---|---|
| S4-01 | 안드로이드 프로젝트와 API 클라이언트 | 대기 | `android/` | |
| S4-02 | 세션 상태 머신 포팅 | 대기 | `SessionMachine.kt` | |
| S4-03 | AudioInput | 대기 | `android/` | |
| S4-04 | AudioOutput | 대기 | `android/` | |
| S4-05 | LocalQueue | 대기 | `android/` | |
| S4-06 | Foreground Service | 대기 | `android/` | |
| S4-07 | 이어폰 버튼(MediaSession) | 대기 | `android/` | |
| S4-08 | Compose 화면 4개 | 대기 | `android/` | |
| S4-09 | 실기기 테스트 | 대기 | 측정 기록 | |

#### S4-01 안드로이드 프로젝트와 API 클라이언트
- [ ] Kotlin + Compose, minSdk 28 프로젝트
- [ ] OpenAPI → Kotlin 클라이언트 생성(openapi-generator)
- [ ] OkHttp SSE 파서

#### S4-02 세션 상태 머신 포팅
- [ ] `sessionMachine.ts` → `SessionMachine.kt`
- [ ] `shared/fixtures/transitions.json`으로 JUnit 테스트

#### S4-03 AudioInput
- [ ] `AudioRecord(VOICE_COMMUNICATION)` 16kHz 모노
- [ ] Silero VAD(ONNX Runtime Android), 웹과 같은 모델·설정값
- [ ] Opus 인코딩

#### S4-04 AudioOutput
- [ ] ExoPlayer로 문장 MP3 이어 재생
- [ ] 재생 문장 번호 추적, 즉시 정지

#### S4-05 LocalQueue
- [ ] 파일 큐 + WorkManager 재전송
- [ ] 기본 TTS로 오프라인 안내

#### S4-06 Foreground Service
- [ ] Foreground Service(microphone) + 상단 알림
- [ ] 화면 꺼짐·다른 앱 사용 중 세션 유지 확인

#### S4-07 이어폰 버튼(MediaSession)
- [ ] 블루투스 이어폰 미디어 버튼 한 번/길게 처리
- [ ] 화면 버튼과 같은 동작

#### S4-08 Compose 화면 4개
- [ ] 대화, 일지 목록, 일지 상세, 설정(웹과 같은 이름)

#### S4-09 실기기 테스트
- [ ] 등산 1회 화면 조작 0회 완주
- [ ] 1시간 세션 배터리 측정
- [ ] 웹과 같은 항목의 음성 측정(지연, 인식률, 끼어들기 오작동)

**완료 기준**

| 기준 | 목표값 | 측정값 | 결과 |
|---|---|---|---|
| 실제 등산 화면 조작 없이 완주, 일지 생성(NFR-02) | 1회 | | |
| 1시간 세션 앱 배터리 소모(NFR-05) | 10% 이내 | | |
| 웹과 같은 전이 표 테스트(JUnit) | 모두 통과 | | |

**마일스톤 종료 체크리스트**
- [ ] 유닛 테스트와 `./gradlew installDebug` 실기기 검증
- [ ] `CLAUDE.md`·`client-contract.md`가 실제 코드와 일치
- [ ] 서브에이전트 diff 리뷰 반영
- [ ] 커밋·push
- [ ] 사용자 확인
- [ ] 대시보드·추적표·변경 이력 갱신

## 8. 5단계 — 다듬기와 확장

**목표**: P2 기능(설정, 검색, 내보내기, 브리핑, 일지 MCP)을 추가하고 보이스를 다듬는다.

- 대상 요구사항: FR-15, FR-16, FR-17, FR-18, FR-19
- 선행 조건: 4단계 완료, 결정 D5(브리핑 관심사)

**작업 목록**

| ID | 작업 | 상태 | 산출물 | 커밋 |
|---|---|---|---|---|
| S5-01 | 설정 화면 | 대기 | 안드로이드 설정 화면(웹은 S3-18로 앞당김) | |
| S5-02 | 검색 | 대기 | FTS5 인덱스, 검색 UI | |
| S5-03 | 내보내기·공유 | 대기 | `export.md` API, 공유 기능 | |
| S5-04 | 보이스 튜닝 | 대기 | `jenny.yaml` 보이스 값 | |
| S5-05 | 주간 브리핑 | 대기 | `server/app/jobs/briefing.py` | |
| S5-06 | 일지 조회 MCP 서버 | 대기 | `server/app/mcp/` | |

#### S5-01 설정 화면
- [ ] 호칭, 관심사, 보이스, 말 속도, 음성 원본 보관
- [ ] 웹·안드로이드 모두 반영

#### S5-02 검색
- [ ] SQLite FTS5 검색 인덱스
- [ ] `GET /api/journal?q=` 검색
- [ ] 검색 UI

#### S5-03 내보내기·공유
- [ ] `GET /api/journal/{session_id}/export.md`
- [ ] 웹 Share API, 안드로이드 공유 인텐트

#### S5-04 보이스 튜닝
- [ ] TTS 파라미터 조정
- [ ] 톤 평가(S1-11) 재실행

#### S5-05 주간 브리핑
- [ ] 월요일 05:00 스케줄러
- [ ] WebSearch·WebFetch만 허용한 CLI 실행, 출처 없는 항목 제거
- [ ] 60초 대본·오디오 생성
- [ ] 월요일 첫 세션 인사 뒤 제안

#### S5-06 일지 조회 MCP 서버
- [ ] Claude Code에서 쓰는 읽기 전용 MCP 서버
- [ ] 일지 목록·상세·검색 도구

**완료 기준**

| 기준 | 목표값 | 측정값 | 결과 |
|---|---|---|---|
| P2 기능(FR-15~FR-19) 동작 | 모두 | | |
| 보이스 튜닝 후 톤 평가 | 20개 중 18개 이상 | | |

**마일스톤 종료 체크리스트**
- [ ] 유닛 테스트와 Playwright·실기기 검증 통과
- [ ] 실제 Claude CLI로 수동 통합 테스트 1회
- [ ] `CLAUDE.md`·`client-contract.md`가 실제 코드와 일치
- [ ] 구독 사용량 확인
- [ ] 서브에이전트 diff 리뷰 반영
- [ ] 커밋·push
- [ ] 사용자 확인
- [ ] 대시보드·추적표·변경 이력 갱신

## 9. 요구사항 추적표

| 요구사항 | 구현 작업 | 검증 단계 | 상태 |
|---|---|---|---|
| FR-01 | S3-13(화면 버튼), S4-07(이어폰 버튼) | 3, 4 | 진행 중 |
| FR-02 | S3-08, S3-10, S4-03 | 3, 4 | 진행 중 |
| FR-03 | S3-04, S3-11, S4-04 | 3, 4 | 진행 중 |
| FR-04 | S1-06, S3-08 | 1, 3 | 진행 중 |
| FR-05 | S4-06 | 4 | 대기 |
| FR-06 | S3-01, S3-02, S3-03 | 3 | 진행 중 |
| FR-07 | S1-05 | 1 | 완료 |
| FR-08 | S1-10, S4-08 | 1, 4 | 진행 중 |
| FR-09 | S1-05(역할 규칙) | 1 | 완료 |
| FR-10 | S1-06(`summarize_session`) | 1 | 완료 |
| FR-11 | S2-05 | 2 | 완료 |
| FR-12 | S2-01, S3-05 | 2, 3 | 진행 중 |
| FR-13 | S2-02, S2-03, S2-04, S2-06 | 2 | 완료 |
| FR-14 | S2-07, S2-08 | 2 | 완료 |
| FR-15 | S5-02 | 5 | 대기 |
| FR-16 | S5-03 | 5 | 대기 |
| FR-17 | S5-01 | 5 | 대기 |
| FR-18 | S5-05 | 5 | 대기 |
| FR-19 | S5-06 | 5 | 대기 |
| FR-20 | S1-03, S1-04, S1-05, S1-09, S1-10, S3-03 | 1, 3 | 진행 중 |
| NFR-01 | S3-03, S3-07 | 3 | 대기 |
| NFR-02 | S4-06, S4-07 | 4 | 대기 |
| NFR-03 | S3-01, S3-10, S4-03 | 3, 4 | 진행 중 |
| NFR-04 | S2-01, S3-12, S4-05 | 2, 3, 4 | 진행 중 |
| NFR-05 | S4-09 | 4 | 대기 |
| NFR-06 | S0-05, S3-14 | 0, 3 | 진행 중 |
| NFR-07 | S1-11, S5-04 | 1, 5 | 진행 중 |
| NFR-08 | S1-05 | 1 | 완료 |

## 10. 결정 사항

설계서 6장의 결정 사항을, 해당 작업이 막히기 전에 정해야 하는 시점에 배치했다.

| ID | 결정 사항 | 필요 시점 | 상태 | 비고 | 결정 내용 |
|---|---|---|---|---|---|
| D1 | 서버 위치: 집 PC vs 클라우드 VM | 3단계 시작 전(S3-14) | 결정 | 집 Mac + Tailscale Serve(tailnet 안에서만 HTTPS, 공개 안 함). 서버 API에 인증이 없어 공개 터널은 쓰지 않는다. 자주 끊기면 VM으로 옮긴다 | 2026-10-17 |
| D2 | Whisper 운영: OpenAI API vs faster-whisper | 3단계 시작 전(S3-01) | 결정 | `SttProvider`로 두 구현 모두 수용 가능 | OpenAI 음성 인식 API(2026-10-16). 서버 PC가 Intel CPU라 로컬 큰 모델로는 3초 목표가 어렵다 |
| D3 | TTS 보이스 서비스(샘플 청취) | 3단계 1주차(S3-02) | 결정 | 2단계 중 샘플 청취 | OpenAI TTS(2026-10-16, 인식과 같은 키). 보이스는 6종 샘플 청취로 `nova` 선택(2026-10-16) |
| D4 | 제니가 먼저 말을 걸지 여부 | 3단계 종료 시 | 대기 | 산책 테스트 경험을 보고 결정 | |
| D5 | 브리핑 관심사 초기 목록 | 5단계 시작 전 | 대기 | | |
| D6 | 서비스화 시점·멀티 사용자 | 5단계 이후 | 대기 | `ClaudeApiBackend` 전환 여부와 연결 | |
| D7 | 안드로이드 포팅 시작 기준 | 3단계 종료 시 | 대기 | 제안: 응답 지연 중앙값 3초 이내, 인식률 85% 이상 | |

## 11. 리스크

| 리스크 | 확인 시점 | 대응 준비 |
|---|---|---|
| CLI 상주 프로세스·인터럽트 불안정 | 0단계 S0-04 — 확인 완료, 안정 | 턴마다 `--resume` 실행 방식으로 대체 |
| 인터럽트 후 모델이 사용자가 듣지 못한 부분까지 기억 | 3단계 S3-04 | 다음 턴 입력에 "사용자가 들은 문장 번호" 메모 추가 검토 |
| CLI가 계정 이메일·실행 환경 정보(작업 폴더·OS·날짜)를 맥락에 자동 첨부(키체인·토큰 모두) | 0단계 S0-04 — 확인 | 본인용은 허용, 프롬프트에 언급 금지 규칙. 서비스화(D6) 시 API 키 + `--bare` |
| CLI 업데이트로 stream-json 형식 변경 | 상시 | CLI 버전 고정, 녹화 샘플 기반 파서 테스트 |
| 구독 사용량 한도 | 상시 | 요약·평가 호출은 haiku, 단계 종료 시 사용량 확인 |
| 웹 검색 턴 지연(7~10초)과 검색 결과 오류 | 1단계 측정, 3단계 음성 | 검색 시작 시 안내 음성, 필요할 때만 검색, 출처 언급 |
| 웹 내용 인젝션·내부망 접근(WebFetch) | 1단계 S1-05·S1-06 | 웹 내용 속 지시 무시 규칙, 검색 직후 쓰기 도구 호출 검증, 서버 바인딩·방화벽 |
| 브라우저 Opus 인코딩 호환성 | 3단계 S3-10 | WAV 업로드 대체 경로 |
| 바람·숨소리 VAD 오작동, 제니 목소리 오인 | 3단계 실측 | 임계값 조정, 재생 중 임계값 상향, 푸시투토크 모드 |
| 웹 화면 꺼짐으로 세션 중단 | 3단계 | Wake Lock, 백그라운드는 4단계로 넘김 |

## 12. 변경 이력

| 날짜 | 내용 | 커밋 |
|---|---|---|
| 2026-10-12 | 0단계 골격 생성(S0-01~S0-03) | `813d01e` |
| 2026-10-12 | 문서 정비: 실제 저장소 상태와 문서 일치 | `eb4d8cf` |
| 2026-10-12 | 계획서를 단계별 세부 계획·진행 추적 구조로 재설계, 문서 파일명 영문화 | `a15d7a8`, `685b7b2` |
| 2026-10-12 | CLAUDE.md에 문서 부분 읽기 규칙 추가 | `2965270` |
| 2026-10-12 | S0-04 Claude CLI 검증 스파이크, S0-05 서버용 토큰(0단계 작업 완료) | `1306053` |
| 2026-10-12 | 대화 중 웹 검색(FR-20, P1) 추가: 검증, 설계서·계획서 반영 | `a9b2970` |
| 2026-10-12 | 0단계 마일스톤 종료(사용자 확인) | `76c2f53` |
| 2026-10-12 | S1-01 공통 오류 응답·로깅·DB 세션 의존성 | `93f315d` |
| 2026-10-12 | S1-02 DB 모델과 마이그레이션 | `0169050` |
| 2026-10-12 | S1-03 Claude CLI 백엔드, S1-04 가짜 CLI·파서 테스트(Playwright 항목 제외) | `19fb1ed` |
| 2026-10-12 | S1-05 페르소나 스키마와 프롬프트 조립기 | `9e7ff4e` |
| 2026-10-14 | S1-07 한국어 문장 분할기 | `010bf5b` |
| 2026-10-14 | S1-09 SSE 이벤트 스키마 초안 | `231fdb4` |
| 2026-10-14 | S1-06 앱 도구 MCP 서버(FastAPI 내부 HTTP 엔드포인트) | `03bf1c8` |
| 2026-10-14 | S1-08 세션·턴·프로필 API | `e4e9a7d` |
| 2026-10-14 | S1-10 웹 텍스트 대화 화면, S1-04 Playwright 가짜 CLI | `aec44df` |
| 2026-10-15 | `run.sh` 앱 실행 스크립트 | `e5bc80e` |
| 2026-10-15 | S1-11 페르소나 톤 평가 도구·프롬프트 보강(4회차 17/20, 기준 미달) | `d867e14` |
| 2026-10-15 | S1-11 완료: 음성 문장 상한 5, 채점 맥락 보완, 5회차 20/20 | `ea609ec` |
| 2026-10-15 | 1단계 완료 기준 측정(모두 통과), 웹 검색 규칙 보강, NFR-08 자동 테스트 | `fd6de20` |
| 2026-10-15 | 대화 시작 전 CLI 미리 띄우기(`POST /api/sessions/prepare`, 인사말 중앙값 2.65→1.76초), 자기 규칙 설명 금지(톤 19/20). 검토 후 미적용: 대화 모델 haiku(첫 문장 1.29→1.36초로 효과 없음), `--effort low`(효과 불일치) | `1191245` |
| 2026-10-15 | 1단계 재검증(실제 CLI 흐름·코드 감사) 수정: 세션 프롬프트 고정(마이그레이션 `0003`), 미리 띄우기 오류 문구, MCP 토큰 비교, 쉬기·끝내기 요청 보존, 재전송 중복·끝난 세션·빈 말풍선·서버 중단 문구 등 웹 버그, 질문 반복 금지 규칙 | `f9d7fd6` |
| 2026-10-15 | 불필요한 문서 정리: 작업 인계 문서(`docs/handoff.md`, 배포 메모는 S3-14로 옮김), 톤 평가 중간 회차 리포트 1~6(회차 기록은 최신 리포트에 요약) | `4dac567` |
| 2026-10-15 | 1단계 마일스톤 종료(사용자 확인) | `02b52b7` |
| 2026-10-15 | 새 세션용 인계 문서(`docs/handoff.md`) | `c15422e` |
| 2026-10-15 | S2-01 턴 즉시 저장: 답변을 문장마다 커밋, 서버 강제 종료 내성 | `5a7c136` |
| 2026-10-15 | S2-02 세션 종료 추출(haiku 단발 호출, `extract_status` 마이그레이션 `0004`) | `0d11b0d` |
| 2026-10-15 | S2-03 노트 중복 제거 | `9a93b51` |
| 2026-10-15 | S2-04 마무리 멘트(끝내기 응답 `SessionClosed`, 페르소나 YAML `closing`) | `1a42c1a` |
| 2026-10-15 | S2-05 기억 블록, 단발 호출 작업 폴더 고정(`~/.claude/projects` 빈 폴더 누수) | `8213178` |
| 2026-10-15 | S2-06 무발화 타임아웃, 시작 때 남은 일지 정리 재개 | `3ab4c1f` |
| 2026-10-15 | S2-07 일지·노트 API | `601fc30`, `d3b33b2` |
| 2026-10-15 | S2-08 웹 일지 화면, 상단 탭 접근성 | `22f7c04` |
| 2026-10-15 | S2-09 추출 품질 평가 세트 | `3cf4966` |
| 2026-10-15 | 2단계 실제 CLI 확인에서 찾은 일지 품질 수정(중복 노트·진행 기록 메모), 추출 평가 12개로 확장 | `e386dfb` |
| 2026-10-15 | 2단계 완료 기준 측정(모두 통과), 마일스톤 종료 문서 갱신(사용자 확인 대기) | `0ea67b2` |
| 2026-10-15 | 2단계 점검 수정: 관심사만 있을 때 첫인사 안내 제외(지어낼 위험), 저장 알림을 종류별로 | `91bba8e` |
| 2026-10-15 | 2단계 점검 개선: 끝난 대화에서 일지 보기, 정리 중인 일지 자동 새로고침 | `1a87e71` |
| 2026-10-15 | 2단계 점검 개선: 정리 실패 일지 다시 정리(`POST /api/journal/{id}/retry`), 아이디어 완료 토글 | `9657174` |
| 2026-10-16 | 2단계 점검 2차 수정: 다른 곳에서 끝낸 대화의 턴 오류를 `session_ended`로, 일지 정리 결과의 줄바꿈·태그 `#` 정리, 무발화 종료 시각을 마지막 활동 시각으로 | `a5719a3` |
| 2026-10-16 | 2단계 점검 2차 개선: 끝내기 때 일지 정리 중 안내, 진행 중 대화의 일지 상세 안내 | `ec34790` |
| 2026-10-16 | 2단계 마일스톤 종료(사용자 확인), 3단계 시작. 결정 D2 OpenAI 음성 인식 API, D3 OpenAI TTS | `8d65aa0` |
| 2026-10-16 | S3-08 세션 상태 머신·S3-09 상태 전이 표 완료. 쉬기 중 30분 무발화 종료 유지(사용자 결정) | `9202e04` |
| 2026-10-16 | S3-06 클라이언트 설정값: VAD 임계값 키 추가, `/api/profile`의 `client`로 제공, 규약 5절 | `2b643a9` |
| 2026-10-16 | S3-01 STT·S3-02 TTS 코드 완료(OpenAI provider, ffmpeg 변환, TTS 전처리, 인용 조사 분할 수정, 페르소나 `pitch`→`instructions`). 실제 호출 확인·보이스 선택은 크레딧 충전 뒤 | `f89057b` |
| 2026-10-16 | S3-01·S3-02 점검 수정: 빈 `OPENAI_API_KEY=`가 실제 키를 가리던 문제, `FFMPEG_PATH`의 `~`, TTS 전처리(목록 기호·범위 `~`), `tts-1`에 `instructions` 미전송, ogg 등 변환을 webm/opus로(업로드 약 1/10), 규약 7절 음성 오류 코드 | `42278ac` |
| 2026-10-16 | S3-03 음성 턴 스트리밍: 오디오 업로드 API, 문장별 MP3, 검색 안내 음성, 인사말·마무리 소리, 가짜 음성 백엔드 | `bafcea9` |
| 2026-10-16 | S3-01·S3-02 완료: OpenAI 크레딧 충전 뒤 실제 인식·합성 확인(`languages` 필드 확인), 보이스 `nova` 확정, S3-03 음성 턴 실제 OpenAI 확인 | `ef035e2` |
| 2026-10-16 | S3-10 AudioInput 완료: vad-web(Silero v5)·WebCodecs Opus(webm)·WAV 대체, VAD 자산 자체 서빙, `sendAudioTurn` | `20cd16a` |
| 2026-10-16 | S3-11 AudioOutput(`8c04f44`)·S3-13 대화 화면 음성 모드 완료: PC 브라우저에서 큰 버튼으로 음성 대화, 알림음, Wake Lock, 음성 모듈 지연 로딩. 서버 프로필 동시 호출 500 수정, 처리 중 탭 재생 정지(전이 표) | `0465493` |
| 2026-10-16 | S3-04 끼어들기 API 완료: 들려준 문장까지만 기록(진행 중이면 CLI 인터럽트, 끝난 턴도, 인사말 제외), 다음 턴 CLI에 들은 위치 안내, 웹 말풍선도 자름 | `22f4e5e` |
| 2026-10-16 | S3-05 음성 원본 보관 완료: keep_audio면 음성 턴 녹음 저장(본인만 읽기), 30일 뒤 삭제 작업 | `d8d5876` |
| 2026-10-16 | S3-07 지연 측정 로그 완료: 음성 턴 단계 시간·웹 보고(말 끝 → 첫 소리)·요약 API. 실제 음성 첫 측정 5.8초(인식 2.9초, 가짜 CLI) | `dce5350` |
| 2026-10-16 | S3-12 오프라인 큐 완료: 복구 때 캐릭터가 차례로 대답(사용자 결정), 대답할 수 없는 말은 기록만 남김, 상태 머신·전이 표 변경, 시뮬레이션 유실 0건 | `30b8576` |
| 2026-10-16 | 3단계 중간 전체 점검: 음성 세션에서 CLI 오류로 끝난 턴의 합성 대기 문장·끝 조각 유실 수정, 글 대화 답변 중 끝내기 허용, 답변을 기다리는 중 이어서 한 말을 큐에 넣어 답변 뒤 전송(상태 머신·전이 표 변경) | `bcd3eb8` |
| 2026-10-17 | 대화 중 호칭 바꾸기(사용자 요청 추가, 작업 ID 없음): MCP `set_nickname`이 프로필 호칭을 바꾼다(이번 사용자 발화에 나온 호칭만 받음), 프롬프트 규칙, 웹 알림. 실제 CLI로 저장·다음 대화 인사말 확인 | `18310b3` |
| 2026-10-17 | S3-14 완료: 결정 D1(집 Mac + Tailscale Serve), PWA, `./run.sh --phone`·`./stop.sh`, 폰(A35)에서 음성 대화 확인(사용자) | `0c1af0c` |
| 2026-10-17 | S3-18 웹 설정 화면 완료(S5-01 웹 부분 앞당김): 호칭·관심사·보이스(미리 듣기)·말 속도·음성 원본 보관, 프로필 보이스·속도를 음성 합성에 적용, 실제 TTS 속도 측정 | `c96fcca` |
| 2026-10-17 | S3-15 클라이언트 규약 확정: 도구 `summary`를 `kind` 타입으로 고정, 출처 호스트를 서버로, `docs/client-contract.md` 확정본 | `033b8aa` |
| 2026-10-17 | S3-16 음성 흐름 E2E 완료: Playwright 가짜 마이크(`voice` 프로젝트)로 발화·답변·끼어들기·오프라인 복구·끝내기 | `fad7711` |
| 2026-10-17 | 문서 정리(토큰 절약): 인계 문서를 현재 상태·검증 방법·배운 것만 남기게 재작성(32KB→11KB), 추출 평가 이전 회차 리포트 4개 삭제(회차 표는 최신 리포트), 규약은 필요한 절만 읽기, README 현재화 | `837ad43` |
| 2026-10-17 | S3-19 일지 목록에서 대화 제목 수정·삭제(사용자 요청 추가): 제목을 눌러 고치고 포커스가 떠나면 저장(다시 정리해도 유지), 쓰레기통은 확인 뒤 삭제(턴 잠금·정리 취소), 모바일 우선 UI | `ffad91e` |
| 2026-10-17 | S3-20 대화 화면 모바일 최적화(꽉 찬 폭 버튼, 메신저형 입력창), 마지막 말풍선이 하단 패널에 가리지 않게 자동 스크롤, 음성 버튼을 그라데이션 구슬 애니메이션으로 | `4b617c6` |
| 2026-10-17 | S3-21 음성 대화 중 글 입력: 글을 말 한 번처럼 머신에 넣어 글 턴으로 전송(끼어들기 뒤 취소 완료 대기·바쁨 재시도), 실패 시 보관하지 않고 입력창에 돌려줌 | `223bddc` |
| 2026-10-17 | S3-22 일지 정리 형식 개편(`5f30452`)을 사용자 요청으로 롤백: 기존 형식(요약 1~3줄 + 노트)으로 복귀. 0009는 남기고 0010으로 report·turn.sources 컬럼 제거 | `fc02d9a` |
| 2026-10-17 | S3-23 일지 인용: 기존 형식에 검색 내용 출처 번호 [1][2]와 인용 목록(기사 제목 URL), 출처 URL 저장·조회 때 번호 매김, 인용 제목 보완, 추출 평가 100% | `9716543` |
| 2026-10-17 | S3-24 일지 표시 개선: 결론·알게 된 것·확인할 것, 사실은 한 곳에만, 예전 형식 다시 정리, 추출 평가 채점 확대(6회차 재현율 100%) | `6a72b59` |
| 2026-10-18 | S3-25 일지 목록 여러 개 선택·한 번에 삭제(서버 변경 없음, 항목별 DELETE 차례 호출) | `07ccb8d` |
| 2026-10-18 | S3-26 끝난 대화 이어서 하기: 다시 열기 API(전문을 프롬프트에 넣어 새 CLI, 재개 인사말, 다시 끝내면 같은 일지 재정리), 일지 상세 글·음성으로 이어서 | `d91f13b`, `4c87241` |
| 2026-10-18 | S3-27 이어서 하기 프롬프트 줄이기: 정리를 마친 긴 대화는 일지 정리 + 최근 원문 4천 자(이어서 블록 약 1/3) | `18a9145` |
| 2026-10-18 | S3-28 지난 대화 전문 검색 도구 search_conversations(모든 대화, 필요할 때만 원문 검색) | `39a8f33` |
| 2026-10-18 | S3-29 일지 상세에서 삭제(맨 아래 버튼, 확인 뒤 목록으로) | `c02b920` |
| 2026-10-18 | S3-30 지워진 대화 안내(일지 상세 404 → '지워진 대화예요' + 목록으로) | `d177d00` |
