# TrailTalk

- 요구사항·설계서: [docs/requirements-design.md](docs/requirements-design.md)
- 구현 계획서: [docs/implementation-plan.md](docs/implementation-plan.md) — 작업은 계획서의 작업 ID(예: `S1-03`) 단위로 진행한다
- 클라이언트 규약: [docs/client-contract.md](docs/client-contract.md)

위 문서는 자동으로 불러오지 않는다(`@` import 금지). 필요한 절만 읽는다: 계획서는 진행 대시보드(2장)와 해당 작업이 속한 단계 절, 설계서는 관련 장만 `grep -n "^#"`으로 위치를 찾아 범위를 지정해 읽는다. 클라이언트 규약은 짧으므로 전체를 읽는다.

새 세션은 [docs/handoff.md](docs/handoff.md)(현재 상태·다음 작업·주의점)를 먼저 읽는다.

## 작업 규칙

- 자동 커밋/푸시 허용 — 이 저장소에서는 매번 묻지 않고 커밋+푸시한다 (커밋 전 서브에이전트 diff 리뷰는 전역 규칙대로 수행)
- 페르소나 분리(NFR-08): 캐릭터 이름·성격·말투·보이스는 `server/personas/*.yaml`에만 두고 코드에 넣지 않는다(`test_no_character_name_hardcoded_in_app_code`가 확인). 시스템 프롬프트는 `server/app/persona/prompt.py`의 `build_system_prompt`로만 만들고, 캐릭터와 무관한 앱 동작 규칙은 `server/app/persona/rules.py`에 둔다. 프롬프트를 바꾸면 `UPDATE_SNAPSHOTS=1`로 스냅샷을 갱신하고 차이를 검토한다.
- 클라이언트는 얇게: 문장 분할·요약·중복 제거처럼 서버가 할 수 있는 일은 클라이언트에 넣지 않는다.
- `web/src/core/`는 UI·브라우저 API에 의존하지 않는 순수 TypeScript로 작성한다(안드로이드 Kotlin 포팅 대상).
- 서버 API는 모두 `/api` 아래에 둔다. 엔드포인트 목록은 설계서 4.6 표를 따른다.
- 서버 오류는 `AppError(code, message, status)`로 던진다. 응답 형식은 `server/app/errors.py`와 `docs/client-contract.md` 7절을 따른다.
- DB는 비동기 SQLAlchemy다. 엔드포인트는 `db: DbSession`(`server/app/db/session.py`)으로 세션을 받고, commit은 명시적으로 한다. 앱은 `create_app(settings)`로 만들며 테스트는 `server/tests/conftest.py`의 `client` 픽스처(임시 SQLite)를 쓴다. 라우터는 `create_app` 안에서 웹 정적 마운트보다 먼저 등록한다(뒤에 붙이면 가려진다).
- LLM은 `app.state.llm`(`LlmSessionManager`, `server/app/llm/manager.py`)으로만 쓴다. 이벤트 형식은 `server/app/llm/events.py`. CLI 실행 인자·환경은 `server/app/llm/claude_cli.py`의 `build_command`/`build_oneshot_command`/`build_env`가 유일한 출처다. 대화가 아닌 단발 호출(세션 종료 추출 등)은 `run_oneshot`(stdin 프롬프트, `--json-schema`, 시간 초과 kill)으로 한다. `session.send()`는 반드시 `contextlib.aclosing(...)`으로 감싸 끝까지 읽거나 닫는다(버리면 매니저가 멈춘 턴으로 강제 정리). 자식 CLI 환경은 허용 목록(`ENV_ALLOWLIST`)만 넘긴다. 테스트는 녹화 재생 가짜 CLI(`fake_cli` 픽스처)를 쓴다. 단발 호출 출력은 `FAKE_CLAUDE_ONESHOT` 파일로 정한다(`tests/fakes/fake_claude.py`).
- 모델(`server/app/db/models.py`)을 바꾸면 같은 커밋에 Alembic 마이그레이션을 만든다. 앱은 시작할 때 head까지 자동 적용한다. 테스트 `test_migrations_match_models`가 모델과 마이그레이션의 차이를 잡는다. 열거값(StrEnum) 변경은 autogenerate가 못 잡으므로 batch로 CHECK 제약을 직접 교체한다(`test_enum_check_constraints_match_models`가 확인). JSON 목록 컬럼은 `MutableList`라 제자리 수정도 저장된다.
- 진행 상태는 구현 계획서에서 관리한다: 작업 시작·완료 시 작업 상태·체크박스·커밋 해시를, 마일스톤 종료 시 완료 기준 측정값·진행 대시보드·추적표·변경 이력을 갱신한다(계획서 1장 갱신 규칙).

## 폴더 구조

```
server/            FastAPI (Python 3.12, uv)
  app/api/         라우터 (/api/*)
  app/voice/       STT, TTS, 문장 분할
  app/persona/     프롬프트 조립기
  app/llm/         Claude CLI 프로세스 관리, stream-json 파서
  app/mcp/         제니 도구 MCP 서버
  app/jobs/        세션 종료 추출·중복 제거·마무리 멘트, 무발화 타임아웃, 브리핑(5단계)
  app/services/    대화 처리(conversation: 세션·턴 SSE), 대화별 런타임(runtime: MCP 토큰·턴 락), 프로필
  app/openapi.py   OpenAPI 내보내기(웹 타입 생성 gen:api)
  app/db/          SQLAlchemy 모델
  personas/        캐릭터 YAML
  tests/           pytest. fakes/(가짜 CLI), fixtures/claude_cli/(녹화), persona_eval/(톤 평가), extract_eval/(추출 평가). 평가는 실제 CLI
web/               React + TypeScript + Vite
  src/core/        세션 상태 머신, 오프라인 큐 (브라우저 API 비의존)
  src/platform/    AudioInput, AudioOutput, LocalQueue 브라우저 구현
  src/screens/     ConversationScreen, JournalListScreen, JournalDetailScreen, SettingsScreen
  src/api/         서버 API 클라이언트
  e2e/             Playwright
android/           4단계에서 구현(지금은 README만)
shared/            효과음, 상태 전이 표, 클라이언트 설정 기본값
docs/              설계서, 계획서, 규약, 인계(handoff.md), 검증 기록(spikes/), 톤·추출 평가 리포트(eval/)
```

## 명령

저장소 루트 기준이다. `npm run e2e`는 개발 서버와 별개로 가짜 Claude CLI(`server/tests/fakes/fake-claude`, 녹화 `web_search`)를 쓰는 E2E 전용 서버(8100, 빈 임시 DB `web/.e2e/`)와 웹(5199)을 매번 새로 띄운다. 서버 API를 바꾸면 `npm run gen:api`로 `web/src/api/schema.d.ts`를 다시 만들어 함께 커밋한다(`npm run gen:api -- --check`는 어긋났는지만 확인).

```bash
# 앱 실행(서버 8000 + 웹 5173, 브라우저 열기, Ctrl+C로 종료)
./run.sh                 # 실제 Claude CLI(구독 사용량 사용)
./run.sh --fake          # 가짜 CLI 녹화 재생, 임시 DB(.run-fake/). 화면 확인용
./run.sh --phone         # 폰에서 쓰기: 빌드본을 서버(8000)가 서빙 + Tailscale Serve HTTPS(docs/phone.md)

# 서버
(cd server && uv run uvicorn app.main:app --reload)    # http://127.0.0.1:8000
(cd server && uv run pytest && uv run ruff check . && uv run ruff format --check .)
(cd server && uv run alembic revision --autogenerate -m "설명")   # 모델 변경 후 마이그레이션 생성(검토 필수)
(cd server && uv run alembic upgrade head)                      # 수동 적용(앱 시작 때도 자동 적용)
(cd server && RUN_REAL_CLI=1 uv run pytest tests/test_llm_real.py -q)  # 실제 Claude CLI 통합 테스트(구독 사용량 소모)
(cd server && RUN_REAL_CLI=1 uv run python -m tests.extract_eval.run_eval)  # 일지 추출 평가(haiku·sonnet 각 12회) → docs/eval/extract-<날짜>.md

# 웹
(cd web && npm run dev)                                # http://127.0.0.1:5173, /api → 8000 프록시
(cd web && npm run test && npm run lint && npm run build)
(cd web && npm run e2e)                                # Playwright: 가짜 CLI 서버·웹 자동 기동 후 실제 구동 검증
(cd web && npm run gen:api)                            # 서버 OpenAPI → src/api/schema.d.ts (-- --check: 차이만 확인)
```
