# 작업 인계 (2026-10-14)

새 세션은 이 문서부터 읽는다. 작업 규칙과 명령은 [CLAUDE.md](../CLAUDE.md)에 있고, 진행 상태의 기준은 [구현 계획서](implementation-plan.md)의 진행 대시보드(2장)다.

## 1. 지금 어디까지 왔나

- **0단계 완료.** 저장소 골격, Claude CLI 검증 스파이크([spikes/claude-cli.md](spikes/claude-cli.md)), 서버용 토큰
- **1단계(제니 텍스트 대화) 작업 11/11 완료, 완료 기준 모두 통과(2026-10-15 측정). 사용자 확인 대기.** 완료한 작업과 커밋은 아래와 같다.

| 작업 | 내용 | 커밋 |
|---|---|---|
| S1-01 | 공통 오류 응답·요청 로그·비동기 DB 세션 | `93f315d` |
| S1-02 | DB 모델·Alembic 마이그레이션 | `0169050` |
| S1-03 | Claude CLI 백엔드(상주 프로세스, 인터럽트, 복구, 정리) | `19fb1ed` |
| S1-04 | 가짜 CLI·파서 테스트. **Playwright 항목만 남음**(S1-10에서) | `19fb1ed` |
| S1-05 | 페르소나 스키마·시스템 프롬프트 조립기 | `9e7ff4e` |
| S1-07 | 한국어 문장 분할기 | `010bf5b` |
| S1-09 | SSE 이벤트 스키마(`turn`·`sentence`·`tool`·`done`·`error`) | `231fdb4` |
| S1-06 | 앱 도구 MCP 서버(FastAPI 내부 `/internal/mcp/`) | `03bf1c8` |
| S1-08 | 세션·턴·프로필 API(`app/api/sessions.py`·`profile.py`, `app/services/conversation.py`) | `e4e9a7d` |
| S1-10 | 웹 텍스트 대화 화면(`web/src/core/sse.ts`·`conversation.ts`, `screens/ConversationScreen.tsx`), S1-04 Playwright 가짜 CLI | `aec44df` |
| S1-11 | 페르소나 톤 평가 20/20(5회차, 음성 상한 5문장). 도구 `server/tests/persona_eval/`, 리포트 `docs/eval/` | `d867e14`, `ea609ec` |

- **다음 작업: 1단계 마감 사용자 확인 → 2단계(대화 기록).** 측정값은 계획서 4장 완료 기준 표에 있다(첫 sentence 중앙값 1.29초, 톤 20/20 등). 확인을 받으면 대시보드에 1단계 완료와 마일스톤 커밋을 적는다. 앱은 `./run.sh`(실제 CLI) 또는 `./run.sh --fake`로 띄운다.
- E2E(`npm run e2e`)는 가짜 CLI 전용 서버(8100)·웹(5199)을 띄운다. 서버 API를 바꾸면 `npm run gen:api`로 웹 타입을 다시 만든다.
- 1단계 남은 작업 전체 계획은 사용자 승인을 받았다. 요약은 아래 4절에 있고, 원본은 `~/.claude/plans/scalable-discovering-emerson.md`다.

## 2. MCP·대화 서버 구조(S1-06, S1-08)

**설계:** MCP는 별도 프로세스가 아니라 FastAPI 안의 HTTP 엔드포인트 `/internal/mcp/`다(`app/mcp/server.py`).
- Claude CLI는 세션마다 받은 `mcp.json`(`mcp_client_config`)으로 접속한다. 헤더는 `Authorization: Bearer <세션 토큰>`, `X-TrailTalk-Session: <세션 ID>`.
- 대화별 메모리 상태는 `app/services/runtime.py`의 `ConversationRuntime`·`RuntimeRegistry`(`app.state.runtimes`).
- 구독(`subscriptions/listen`)을 끈 이유: 켜 두면 CLI가 연결을 열어 둬 uvicorn 종료가 멈춘다. 끈 뒤 실제 CLI 테스트는 약 6초에 정상 종료한다.

**턴 처리 규칙**(S1-08에서 구현함, `runtime.py` 모듈 주석에도 있다)
- 사용자 턴을 **커밋한 뒤** `current_user_turn_id`를 설정하고 `send()`를 시작한다(`note.turn_id` 외래 키). 턴이 끝나면 None으로 되돌린다.
- 턴 시작 때 `requested_status`를 비우고, 턴이 끝나면 `pop_requested_status()`로 읽어 DB 상태와 `done` 이벤트에 반영한다.
- 세션 종료 시 `llm.close(id)` → `runtimes.discard(id)` 순서. 살아 있는 CLI는 처음 받은 토큰을 계속 쓰므로 CLI를 닫기 전에 토큰을 바꾸면 도구 호출이 모두 401이 된다. 테스트로 고정한다.
- 도구 이벤트 → SSE `tool` 변환은 `services/conversation.py`의 `stream_turn`.

**S1-08에서 알게 된 것**
- 클라이언트가 턴 도중 연결을 끊으면 S1-03 설계대로 CLI 프로세스를 즉시 죽이고, 다음 턴에서 `--resume`으로 맥락을 잇는다(실측: 끊은 뒤 다음 턴 첫 문장 3.0초).
- 도구를 쓴 턴은 CLI가 도구 뒤 답변을 thinking이 끝난 뒤 한꺼번에 내보낸다(첫 문장이 도구 끝 후 약 4.7초 늦음). CLI 단독 실행에서도 같고 `MAX_THINKING_TOKENS=0`으로 안 꺼진다. 3단계 음성 지연 때 다시 본다.
- 실제 CLI 수동 확인 방법: 임시 DB·포트로 `DATABASE_URL=... CLI_WORK_DIR=... INTERNAL_BASE_URL=http://127.0.0.1:<포트> uv run uvicorn app.main:app --port <포트>`를 띄우고 httpx로 `/api/sessions`·`/turns`를 호출한다. 끝나면 `~/.claude/projects/`에 남은 임시 작업 폴더 이름의 폴더를 지운다.

**배포 때 할 일(5장)**
- `/internal/*`는 터널·리버스 프록시에서 막는다. 앱도 전달 헤더(`X-Forwarded-For`, `CF-Connecting-IP`, `Forwarded`, `X-Real-IP`)가 붙은 MCP 요청을 403으로 거부한다.
- 서버 포트가 8000이 아니면 `INTERNAL_BASE_URL`을 맞춘다. 틀리면 CLI가 도구 없이 대화한다.

## 3. 지켜야 할 규칙 (요약)

- 전역 규칙(`~/.claude/CLAUDE.md`)
  - 모든 응답과 중간 진행 메시지는 한글
  - 구현 전 Plan Mode로 계획 승인
  - 마일스톤 단위 진행과 사용자 확인
  - 커밋 전 서브에이전트 리뷰
  - Playwright로 실제 구동 검증
- 프로젝트 규칙(`CLAUDE.md`)
  - 캐릭터 정보는 YAML에만 둔다(앱 코드에 "제니"가 들어가면 테스트가 실패하므로 주석·docstring도 조심).
  - LLM은 `app.state.llm`으로만 쓰고 `send()`는 `aclosing`으로 감싼다.
  - 모델을 바꾸면 마이그레이션을 같이 만든다.
  - 프롬프트를 바꾸면 `UPDATE_SNAPSHOTS=1`로 스냅샷을 갱신한다.
- 실제 CLI 테스트는 구독 사용량을 쓰므로, 필요할 때만 `RUN_REAL_CLI=1`로 돌리고 보고 때 사용량을 알린다.

## 4. 남은 1단계 계획 요약 (승인됨)

- **S1-08 세션·턴·프로필 API** (`app/api/sessions.py`, `profile.py`, `app/services/conversation.py`)
  - **`POST /api/sessions`** `{mode}`: 세션을 만들고 프롬프트를 조립한다. CLI를 `mcp_config`와 함께 연다(`RuntimeRegistry.ensure` → `mcp_client_config`). 숨은 지시로 인사말을 받아 JSON으로 반환하고 assistant 턴 seq 0으로 저장한다.
  - **`POST /api/sessions/{id}/turns`** `{text}` → SSE
    - 시작 전 오류(404/409)는 JSON으로 준다.
    - 사용자 턴을 즉시 저장하고 `runtime.current_user_turn_id`를 설정한다.
    - 첫 이벤트로 `turn`(assistant 턴 ID 미리 생성)을 보낸다.
    - `TextDelta`는 문장 분할기를 거쳐 `sentence`가 된다. 도구 이벤트는 `public_tool_name`으로 이름을 바꿔 `tool`(start/call/end)로 보낸다.
    - `TurnStarted`면 `cli_session_id`를 DB에 저장한다.
    - 턴이 끝나면 assistant 턴을 저장하고, `runtime.requested_status`(pause/end)를 반영해 `done`을 보낸다. LLM 오류는 `error` 이벤트로 보낸다.
  - **`POST /api/sessions/{id}/end`**: `ended`로 바꾸고 CLI를 닫는다. 런타임(토큰)을 폐기하고 `~/.claude/projects/*/<cli_session_id>.jsonl` 정확한 파일만 삭제한다.
  - **`GET/PUT /api/profile`**: 단일 행. 기본 페르소나를 `persona` 테이블에 동기화한다. 호칭은 1~20자이고 줄바꿈 불가.
  - 테스트는 가짜 CLI(`fake_cli` 픽스처, 녹화 `server/tests/fixtures/claude_cli/*.jsonl`)로 한다. SSE 파싱은 `split("\n")`으로 한다(`splitlines` 금지, U+2028 문제).
- **S1-10 웹 텍스트 대화 화면**
  - `npm run gen:api`: 서버 OpenAPI → openapi-typescript
  - `web/src/core/sse.ts`: 순수 TS SSE 파서
  - `ConversationScreen`: 시작, 말풍선 문장 단위, "검색 중…"·"메모 저장" 알림, 끝내기
  - Vitest를 작성한다.
  - Playwright: 가짜 CLI를 쓰는 E2E 전용 서버를 8100번 포트로 띄운다(`CLAUDE_CLI_PATH`, `FAKE_CLAUDE_FIXTURE`, `CLI_ENV_PASSTHROUGH`, 임시 DB). Vite 프록시 대상은 `VITE_API_TARGET`으로 정한다.
- **S1-11 페르소나 톤 평가:** `server/tests/persona_eval/`에 질문 20개를 둔다. sonnet으로 답하고 haiku와 코드 검사로 채점한다. 기준은 18/20이고 리포트는 `docs/eval/`에 남긴다.
- **1단계 마감:** 완료 기준을 측정한다(첫 sentence 2초 이내 10회 중앙값 등). 마일스톤 체크리스트를 처리하고 대시보드·추적표·변경 이력을 갱신한 뒤 사용자 확인을 받는다.

## 5. 알아 두면 좋은 사실

- **Claude CLI 2.1.296**
  - MCP 도구를 쓰려면 `ENABLE_TOOL_SEARCH=false`가 필요하다.
  - 오류 판정은 `is_error`로 한다(`subtype`은 오류여도 success일 수 있다).
  - `system/init`은 턴마다 온다.
  - 근거는 [spikes/claude-cli.md](spikes/claude-cli.md)에 있다.
- **계정 이메일:** CLI가 계정 이메일·실행 환경을 맥락에 자동으로 붙인다(키체인·토큰 모두). 프롬프트에 언급 금지 규칙이 들어 있다.
- **MCP SDK 2.3.0:** `MCPServer`(`mcp.server.mcpserver`)를 쓰고, `streamable_http_app(stateless_http=True, json_response=True)`로 마운트한다. 세션 매니저는 앱 lifespan에서 실행해야 한다.
- **로컬 개발:** 쉘에 `VIRTUAL_ENV` 경고가 뜨지만 무해하다. 테스트 출력은 `grep -v VIRTUAL`로 걸러 보면 된다.
