/// <reference lib="dom" />
import { expect, test } from '@playwright/test'

// 마이크 입력(S3-10)의 브라우저 부분. 서버 대화는 부르지 않는다(가짜 CLI 녹화 순서를 다른 테스트와 함께 쓴다).
// 가짜 마이크로 발화를 넣는 흐름은 S3-16에서 다룬다.

test('발화 오디오를 Opus(webm)로 인코딩하고 브라우저가 다시 디코드한다', async ({ page }) => {
  await page.goto('/')
  const result = await page.evaluate(async (modulePath) => {
    const { encodeUtterance } = await import(modulePath)
    const samples = new Float32Array(16000).map((_, i) => Math.sin((2 * Math.PI * 220 * i) / 16000) * 0.3)
    const audio = await encodeUtterance(samples, 16000)
    const decoded = await new OfflineAudioContext(1, 1, 16000).decodeAudioData(audio.bytes.slice().buffer)
    return { mimeType: audio.mimeType, bytes: audio.bytes.length, durationMs: audio.durationMs, decoded: decoded.duration }
  }, '/src/platform/encodeAudio.ts') // 개발 서버가 서빙하는 소스 경로
  // WAV로 떨어지면(인코더 설정 오류 등) 업로드가 10배 커진다
  expect(result.mimeType).toBe('audio/webm;codecs=opus')
  expect(result.durationMs).toBe(1000)
  expect(result.bytes).toBeLessThan(8000)
  expect(result.decoded).toBeGreaterThan(0.9)
  expect(result.decoded).toBeLessThan(1.1)
})

test('음성 감지 모델·worklet·onnxruntime 파일을 앱이 직접 서빙한다', async ({ request }) => {
  for (const [name, type] of [
    ['vad.worklet.bundle.min.js', 'text/javascript'],
    ['silero_vad_v5.onnx', 'application/octet-stream'],
    ['ort-wasm-simd-threaded.mjs', 'text/javascript'],
    ['ort-wasm-simd-threaded.wasm', 'application/wasm'],
  ]) {
    const response = await request.get(`/vad/${name}`)
    expect(response.status(), name).toBe(200)
    expect(response.headers()['content-type'], name).toBe(type)
  }
})
