/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { basename } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'
import { VAD_ASSETS, VAD_DIR } from './vadAssets.ts'

const CONTENT_TYPES: Record<string, string> = {
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.wasm': 'application/wasm',
  '.onnx': 'application/octet-stream',
}

function vadAssets(): Plugin {
  const byName = new Map(VAD_ASSETS.map((path) => [basename(path), path]))
  return {
    name: 'vad-assets',
    configureServer(server) {
      // 앱은 BASE_URL + VAD_DIR(버전 폴더)을 요청한다(src/platform/audioInput.ts)
      server.middlewares.use(`${server.config.base}${VAD_DIR}`, (req, res, next) => {
        const path = byName.get((req.url ?? '').split('?')[0].replace(/^\//, ''))
        if (!path) return next()
        res.setHeader('Content-Type', CONTENT_TYPES[path.slice(path.lastIndexOf('.'))])
        res.end(readFileSync(path))
      })
    },
    generateBundle() {
      for (const [name, path] of byName) {
        this.emitFile({ type: 'asset', fileName: `${VAD_DIR}${name}`, source: readFileSync(path) })
      }
    },
  }
}

// PWA(계획서 S3-14): 앱 셸을 미리 저장해 산에서 연결이 끊긴 채 다시 열어도 화면이 뜨게 한다.
// - 새 버전은 자동으로 새로 고치지 않는다(대화 중 페이지가 다시 열리면 안 된다). 화면이 "새 버전 적용" 버튼을 보이고
//   대화 중이 아닐 때 눌러 바꾼다(src/screens/UpdateBanner.tsx)
// - 음성 감지 자산(/vad/<버전>/, onnxruntime wasm 약 14MB)은 미리 받지 않고 처음 쓸 때 저장한다(그 뒤 오프라인에서도
//   쓴다). 버전이 바뀌면 주소가 바뀌고, 옛 항목은 개수 한도(maxEntries)로 밀려난다
// - /api·/internal은 서비스 워커가 다루지 않는다(항상 네트워크)
const pwa = VitePWA({
  registerType: 'prompt',
  injectRegister: false, // 앱이 useRegisterSW로 등록한다(업데이트 알림)
  manifest: {
    name: 'TrailTalk',
    short_name: 'TrailTalk',
    description: '걸으면서 떠오르는 생각을 말로 나누는 산책 대화',
    lang: 'ko',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    theme_color: '#2f7d4f',
    background_color: '#ffffff',
    icons: [
      { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: 'icon-512.png', sizes: '512x512', type: 'image/png' },
      { src: 'icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  },
  workbox: {
    globPatterns: ['**/*.{js,css,html,svg,png,mp3}'],
    globIgnores: ['vad/**'],
    navigateFallback: 'index.html',
    navigateFallbackDenylist: [/^\/api(\/|$)/, /^\/internal(\/|$)/, /^\/(docs|redoc)/, /^\/openapi\.json/],
    runtimeCaching: [
      {
        urlPattern: ({ url }) => url.pathname.startsWith('/vad/'),
        handler: 'CacheFirst',
        options: { cacheName: 'vad-assets', expiration: { maxEntries: 10 } },
      },
    ],
  },
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), vadAssets(), pwa],
  define: { __VAD_DIR__: JSON.stringify(VAD_DIR) },
  // 음성 모듈은 나중에 불러오므로, 처음 쓸 때 개발 서버가 의존성을 다시 묶으며 페이지를 새로 고치지 않게 한다
  optimizeDeps: { include: ['@ricky0123/vad-web', 'mediabunny'] },
  // 음성 모듈 청크(platform, 화면이 열린 뒤 따로 불러온다)가 약 550KB다
  build: { chunkSizeWarningLimit: 600 },
  server: {
    // 개발 중 /api 요청은 FastAPI(uvicorn, 기본 8000번)로 넘긴다.
    // E2E는 가짜 CLI를 쓰는 전용 서버로 넘기도록 VITE_API_TARGET을 준다(playwright.config.ts).
    proxy: { '/api': process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
