# TrailTalk

등산·산책 중 이어폰만으로 캐릭터 '제니'와 대화하며 브레인스토밍하고, 대화를 자동으로 일지로 정리하는 앱.

- 요구사항·설계서: [docs/requirements-design.md](docs/requirements-design.md)
- 구현 계획서: [docs/implementation-plan.md](docs/implementation-plan.md)
- 클라이언트 규약(초안): [docs/client-contract.md](docs/client-contract.md)

## 진행 상황

0단계(준비·기술 검증) 진행 중이다. 단계별 상태와 현재 작업은 구현 계획서의 [진행 대시보드](docs/implementation-plan.md#2-진행-대시보드)에서 확인한다.

## 필요 도구

- [uv](https://docs.astral.sh/uv/) (Python 3.12는 uv가 자동으로 받는다)
- Node.js 22.22.2 이상(22.x) 또는 24.15 이상 (테스트 의존성 jsdom·vitest 기준)
- ffmpeg (3단계 음성 대화부터 필요)
- Claude Code CLI 2.1.296 기준. 서버용 토큰은 `claude setup-token`으로 발급해 `.env`에 넣는다. 출력 형식이 바뀌지 않도록 자동 업데이트를 끈다(`DISABLE_AUTOUPDATER=1`). 검증 결과는 [docs/spikes/claude-cli.md](docs/spikes/claude-cli.md)

## 실행

아래 명령은 모두 저장소 루트에서 실행한다.

```bash
cp .env.example .env

# 한 번에 실행: 서버와 웹을 함께 띄우고 브라우저를 연다(Ctrl+C로 종료)
./run.sh            # 실제 Claude CLI(구독 사용량 사용)
./run.sh --fake     # 가짜 CLI(녹화 재생)로 화면만 확인
```

따로 띄우려면:

```bash
# 서버 (http://127.0.0.1:8000)
(cd server && uv sync && uv run uvicorn app.main:app --reload)

# 웹 개발 서버 (http://127.0.0.1:5173, /api는 서버로 프록시) — 다른 터미널에서
(cd web && npm install && npm run dev)
```

`npm run build`로 만든 `web/dist`가 있으면 서버가 `/`에서 웹 앱을 함께 서빙한다.

서버는 시작할 때 DB 마이그레이션을 자동으로 적용한다. 모델을 바꾼 뒤에는 `(cd server && uv run alembic revision --autogenerate -m "설명")`으로 마이그레이션을 만들고 내용을 검토한다.

## 테스트

```bash
(cd server && uv run pytest && uv run ruff check . && uv run ruff format --check .)
(cd web && npm run test && npm run lint && npm run build)

# 실제 구동 확인: 서버와 웹을 자동으로 띄워 Playwright로 검사
(cd web && npx playwright install chromium && npm run e2e)
```
