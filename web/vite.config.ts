/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { basename, dirname, join } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const require = createRequire(import.meta.url)
const vadDist = dirname(require.resolve('@ricky0123/vad-web'))
// vad-web이 쓰는 onnxruntime-web(wasm 빌드)과 같은 폴더의 wasm 파일
const ortDist = dirname(createRequire(join(vadDist, 'index.js')).resolve('onnxruntime-web/wasm'))

// 음성 감지(src/platform/audioInput.ts)가 실행 중에 불러오는 파일. CDN 대신 앱이 /vad/에서 서빙한다
const VAD_ASSETS = [
  join(vadDist, 'vad.worklet.bundle.min.js'),
  join(vadDist, 'silero_vad_v5.onnx'),
  join(ortDist, 'ort-wasm-simd-threaded.mjs'),
  join(ortDist, 'ort-wasm-simd-threaded.wasm'),
]
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
      // 앱은 BASE_URL + 'vad/'를 요청한다(src/platform/audioInput.ts)
      server.middlewares.use(`${server.config.base}vad/`, (req, res, next) => {
        const path = byName.get((req.url ?? '').split('?')[0].replace(/^\//, ''))
        if (!path) return next()
        res.setHeader('Content-Type', CONTENT_TYPES[path.slice(path.lastIndexOf('.'))])
        res.end(readFileSync(path))
      })
    },
    generateBundle() {
      for (const [name, path] of byName) {
        this.emitFile({ type: 'asset', fileName: `vad/${name}`, source: readFileSync(path) })
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), vadAssets()],
  // 음성 모듈은 나중에 불러오므로, 처음 쓸 때 개발 서버가 의존성을 다시 묶으며 페이지를 새로 고치지 않게 한다
  optimizeDeps: { include: ['@ricky0123/vad-web', 'mediabunny'] },
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
