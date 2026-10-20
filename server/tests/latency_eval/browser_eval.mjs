// 브라우저 구동 지연 측정(V2-M0-06): 마이크에 발화를 주입해 음성 대화를 N턴 돌린다.
// 말 끝 → 첫 소리는 앱이 서버로 보고하므로(GET /api/latency), 이 스크립트는 구동만 한다.
// 환경: EVAL_BASE_URL, EVAL_WEB_DIR(web 폴더), EVAL_TURNS, EVAL_UTTERANCES(JSON 파일: {"pcm_b64": [..]}, 16kHz int16)
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import path from 'node:path'

const require = createRequire(path.join(process.env.EVAL_WEB_DIR, 'package.json'))
const { chromium, devices } = require('@playwright/test')
const base = process.env.EVAL_BASE_URL
const turns = Number(process.env.EVAL_TURNS ?? 10)
const { pcm_b64: utterances } = JSON.parse(readFileSync(process.env.EVAL_UTTERANCES, 'utf8'))

const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] })
const context = await browser.newContext({ ...devices['Pixel 7'], permissions: ['microphone'], serviceWorkers: 'block' })
const page = await context.newPage()
await page.addInitScript(() => {
  let ctx
  let dest
  const open = () => {
    ctx ??= new AudioContext({ sampleRate: 16000 })
    dest ??= ctx.createMediaStreamDestination()
    return { ctx, dest }
  }
  navigator.mediaDevices.getUserMedia = async () => new MediaStream(open().dest.stream.getAudioTracks())
  window.__speak = async (b64) => {
    const { ctx, dest } = open()
    await ctx.resume()
    const raw = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
    const pcm = new Int16Array(raw.buffer)
    const buffer = ctx.createBuffer(1, pcm.length, 16000)
    buffer.copyToChannel(Float32Array.from(pcm, (v) => v / 32768), 0)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(dest)
    source.start()
  }
})

const state = (name, timeout) => page.locator(`.voice-controls[data-state="${name}"]`).waitFor({ timeout })
const done = []
let error = null
try {
  await page.goto(base)
  await page.getByRole('button', { name: '음성으로 대화' }).click()
  await state('listening', 60_000)
  for (let i = 0; i < turns; i++) {
    await page.evaluate((b64) => window.__speak(b64), utterances[i % utterances.length])
    await state('processing', 30_000) // 무음 대기 뒤 전송
    await state('listening', 180_000) // 답변을 다 듣고 다시 듣는다
    done.push(i + 1)
    await page.waitForTimeout(1000)
  }
} catch (e) {
  error = String(e).split('\n')[0]
}
await browser.close()
console.log(JSON.stringify({ completed: done.length, error }))
process.exit(error ? 1 : 0)
