# TrailTalk

등산·산책 중 이어폰만으로 캐릭터 '제니'와 대화하며 브레인스토밍하고, 대화를 자동으로 일지로 정리하는 앱.

- 설계서: [docs/TrailTalk_요구사항_설계서.md](docs/TrailTalk_요구사항_설계서.md)
- 구현 계획서: [docs/구현_계획서.md](docs/구현_계획서.md)

## 실행

필요 도구: [uv](https://docs.astral.sh/uv/), Node.js 20 이상.

```bash
cp .env.example .env

# 서버 (http://127.0.0.1:8000)
cd server
uv sync
uv run uvicorn app.main:app --reload

# 웹 개발 서버 (http://127.0.0.1:5173, /api는 서버로 프록시)
cd web
npm install
npm run dev
```

`npm run build`로 만든 `web/dist`가 있으면 서버가 `/`에서 웹 앱을 함께 서빙한다.

## 테스트

```bash
cd server && uv run pytest && uv run ruff check .
cd web && npm run test && npm run lint && npm run build
cd web && npx playwright install chromium && npm run e2e   # 서버와 웹을 자동으로 띄워 실제 구동 확인
```
