import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'

// E2E는 개발 서버(8000·5173)를 쓰지 않고, 가짜 Claude CLI를 쓰는 전용 서버와 웹을 따로 띄운다.
// 가짜 CLI는 녹화(server/tests/fixtures/claude_cli/web_search.jsonl)를 턴마다 차례로 재생한다:
// 인사말 → 웹 검색 → 페이지 읽기 → 메모 저장 → 일반 답변.
const API_PORT = 8100
const WEB_PORT = 5199 // 개발용 vite가 5173이 차 있으면 5174로 넘어가므로 겹치지 않는 포트
const E2E_DIR = fileURLToPath(new URL('./.e2e', import.meta.url))
const FAKE_CLI = fileURLToPath(new URL('../server/tests/fakes/fake-claude', import.meta.url))
const EXTRACT_FIXTURE = fileURLToPath(
  new URL('../server/tests/fixtures/claude_cli/extract.jsonl', import.meta.url),
)
// 음성 흐름 E2E의 가짜 마이크: 약 24초마다 한국어 문장 하나를 되풀이한다(e2e/fixtures/make-utterance.sh)
const FAKE_MIC = fileURLToPath(new URL('./e2e/fixtures/utterance.wav', import.meta.url))

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: 'retain-on-failure' },
  projects: [
    { name: 'mobile-chrome', use: { ...devices['Pixel 7'] }, testIgnore: /voice\.spec\.ts/ },
    {
      // 음성 대화(S3-16): Chromium 가짜 마이크로 녹음 파일을 넣는다. 서버 음성 인식·합성은 가짜다
      name: 'voice',
      testMatch: /voice\.spec\.ts/,
      use: {
        ...devices['Pixel 7'],
        permissions: ['microphone'],
        launchOptions: {
          args: [
            '--use-fake-ui-for-media-stream',
            '--use-fake-device-for-media-stream',
            `--use-file-for-fake-audio-capture=${FAKE_MIC}`,
            '--autoplay-policy=no-user-gesture-required',
          ],
        },
      },
    },
  ],
  // 서버 하나·가짜 CLI 녹화 순서를 함께 쓰므로 테스트를 순서대로 돌린다
  workers: 1,
  webServer: [
    {
      // 실행할 때마다 빈 DB로 시작한다
      command: `rm -rf "${E2E_DIR}" && mkdir -p "${E2E_DIR}" && uv run uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: '../server',
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      env: {
        CLAUDE_CLI_PATH: FAKE_CLI,
        FAKE_CLAUDE_FIXTURE: 'web_search',
        // 세션 종료 추출(단발 호출)은 고정 결과를 낸다
        FAKE_CLAUDE_ONESHOT: EXTRACT_FIXTURE,
        CLI_ENV_PASSTHROUGH: '["FAKE_CLAUDE_*"]',
        DATABASE_URL: `sqlite+aiosqlite:///${E2E_DIR}/e2e.db`,
        CLI_WORK_DIR: `${E2E_DIR}/cli`,
        INTERNAL_BASE_URL: `http://127.0.0.1:${API_PORT}`,
        WEB_DIST_DIR: `${E2E_DIR}/no-dist`,
        // 음성 인식·합성은 가짜(app/voice/fake.py)
        VOICE_BACKEND: 'fake',
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      env: { VITE_API_TARGET: `http://127.0.0.1:${API_PORT}` },
    },
  ],
})
