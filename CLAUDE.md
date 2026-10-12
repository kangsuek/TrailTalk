# TrailTalk

- 요구사항·설계서: [docs/requirements-design.md](docs/requirements-design.md)
- 구현 계획서: [docs/implementation-plan.md](docs/implementation-plan.md) — 작업은 계획서의 작업 ID(예: `S1-03`) 단위로 진행한다
- 클라이언트 규약: [docs/client-contract.md](docs/client-contract.md)

## 작업 규칙

- 자동 커밋/푸시 허용 — 이 저장소에서는 매번 묻지 않고 커밋+푸시한다 (커밋 전 서브에이전트 diff 리뷰는 전역 규칙대로 수행)
- 페르소나 분리(NFR-08): 캐릭터 이름·성격·말투·보이스는 `server/personas/*.yaml`에만 두고 코드에 넣지 않는다.
- 클라이언트는 얇게: 문장 분할·요약·중복 제거처럼 서버가 할 수 있는 일은 클라이언트에 넣지 않는다.
- `web/src/core/`는 UI·브라우저 API에 의존하지 않는 순수 TypeScript로 작성한다(안드로이드 Kotlin 포팅 대상).
- 서버 API는 모두 `/api` 아래에 둔다. 엔드포인트 목록은 설계서 4.6 표를 따른다.
- 진행 상태는 구현 계획서에서 관리한다: 작업 시작·완료 시 작업 상태·체크박스·커밋 해시를, 마일스톤 종료 시 완료 기준 측정값·진행 대시보드·추적표·변경 이력을 갱신한다(계획서 1장 갱신 규칙).

## 폴더 구조

```
server/            FastAPI (Python 3.12, uv)
  app/api/         라우터 (/api/*)
  app/voice/       STT, TTS, 문장 분할
  app/persona/     프롬프트 조립기
  app/llm/         Claude CLI 프로세스 관리, stream-json 파서
  app/mcp/         제니 도구 MCP 서버
  app/jobs/        세션 종료 추출, 브리핑
  app/db/          SQLAlchemy 모델
  personas/        캐릭터 YAML
  tests/
web/               React + TypeScript + Vite
  src/core/        세션 상태 머신, 오프라인 큐 (브라우저 API 비의존)
  src/platform/    AudioInput, AudioOutput, LocalQueue 브라우저 구현
  src/screens/     ConversationScreen, JournalListScreen, JournalDetailScreen, SettingsScreen
  src/api/         서버 API 클라이언트
  e2e/             Playwright
android/           4단계에서 생성
shared/            효과음, 상태 전이 표, 클라이언트 설정 기본값
docs/              설계서, 계획서, 규약, 검증 기록(spikes/)
```

## 명령

저장소 루트 기준이다. `npm run e2e`는 서버(8000)와 웹(5173)을 자동으로 띄우며, 이미 떠 있으면 그 서버를 재사용한다(CI 제외).

```bash
# 서버
(cd server && uv run uvicorn app.main:app --reload)    # http://127.0.0.1:8000
(cd server && uv run pytest && uv run ruff check . && uv run ruff format --check .)

# 웹
(cd web && npm run dev)                                # http://127.0.0.1:5173, /api → 8000 프록시
(cd web && npm run test && npm run lint && npm run build)
(cd web && npm run e2e)                                # Playwright: 서버·웹 자동 기동 후 실제 구동 검증
```
