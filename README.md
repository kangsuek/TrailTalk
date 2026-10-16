# TrailTalk

등산·산책 중 이어폰만으로 캐릭터 '제니'와 대화하며 브레인스토밍하고, 대화를 자동으로 일지로 정리하는 앱.

- 요구사항·설계서: [docs/requirements-design.md](docs/requirements-design.md)
- 구현 계획서(진행 상황은 [2장 대시보드](docs/implementation-plan.md#2-진행-대시보드)): [docs/implementation-plan.md](docs/implementation-plan.md)
- 클라이언트 규약: [docs/client-contract.md](docs/client-contract.md)
- 폰에서 쓰기(Tailscale): [docs/phone.md](docs/phone.md)

## 필요 도구

- [uv](https://docs.astral.sh/uv/)(Python 3.12는 uv가 받는다), Node.js 22.22.2 이상(22.x) 또는 24.15 이상, ffmpeg(음성 대화)
- Claude Code CLI 2.1.296 기준. 서버용 토큰은 `claude setup-token`으로 발급해 `.env`에 넣고 자동 업데이트를 끈다(`DISABLE_AUTOUPDATER=1`). 검증 결과: [docs/spikes/claude-cli.md](docs/spikes/claude-cli.md)
- 음성 인식·합성은 OpenAI API 키(`.env`의 `OPENAI_API_KEY`)

## 실행·테스트

저장소 루트에서 `cp .env.example .env` 뒤:

```bash
./run.sh            # 서버(8000)+웹(5173), 실제 Claude CLI(구독 사용량)
./run.sh --fake     # 가짜 CLI·가짜 음성으로 화면만 확인
./run.sh --phone    # 폰에서 쓰기(빌드본 + Tailscale HTTPS). --no-open: 브라우저를 열지 않음
./stop.sh           # 다른 터미널에서 끄기

(cd server && uv run pytest && uv run ruff check . && uv run ruff format --check .)
(cd web && npm run test && npm run lint && npm run build)
(cd web && npx playwright install chromium && npm run e2e)   # 실제 구동 검증
```

그 밖의 명령(마이그레이션, 실제 CLI 테스트, 평가, API 타입 생성)은 [CLAUDE.md](CLAUDE.md)의 명령 절에 있다.
