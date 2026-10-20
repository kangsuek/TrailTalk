import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import type { Metrics } from '../src/core/metrics.js'

// 공통 계측 훅(window.__tt_metrics)과 끼어들기 기록(V2-M0-05): 답변을 들려주는 중에 사용자가 말하면
// VAD 프레임·확정·소스 정지 표식이 남고, 끼어들기가 서버(barge_in_event)로 올라간다.
// 가짜 마이크 파일은 시각을 못 정하므로(24초 주기) getUserMedia를 덮어써 원하는 때 발화를 넣는다.
// 헤드리스에서는 에코 제거를 거치지 않는 소프트웨어 경로만 잰다(삭제된 docs/V2/spec.md 6장 한계, git 이력).
const WAV = readFileSync(new URL('./fixtures/utterance.wav', import.meta.url))
const BYTES_PER_SECOND = 16_000 * 2
// 파일은 무음 1초 + 문장 약 3초 + 무음 20초(make-utterance.sh): 문장 부분만 잘라 쓴다
const SPEECH = WAV.subarray(44 + 0.9 * BYTES_PER_SECOND, 44 + 4.3 * BYTES_PER_SECOND).toString('base64')

declare global {
  interface Window {
    __speak: (base64: string) => Promise<void>
    __tt_metrics?: Metrics
  }
}

const voiceState = (page: Page, state: string, timeout = 20_000) =>
  page.locator(`.voice-controls[data-state="${state}"]`).waitFor({ timeout })

test('말하는 중 말소리로 끼어들면 계측 표식이 남고 끼어들기 기록이 서버에 올라간다', async ({ page }) => {
  test.setTimeout(120_000)
  await page.addInitScript(() => {
    let context: AudioContext | undefined
    let destination: MediaStreamAudioDestinationNode | undefined
    const open = () => {
      context ??= new AudioContext({ sampleRate: 16_000 })
      destination ??= context.createMediaStreamDestination()
      return { context, destination }
    }
    // 마이크: 평소에는 무음, __speak를 부를 때만 발화가 흐른다
    navigator.mediaDevices.getUserMedia = async () => new MediaStream(open().destination.stream.getAudioTracks())
    window.__speak = async (base64) => {
      const { context, destination } = open()
      await context.resume()
      const raw = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
      const pcm = new Int16Array(raw.buffer)
      const buffer = context.createBuffer(1, pcm.length, 16_000)
      buffer.copyToChannel(Float32Array.from(pcm, (v) => v / 32768), 0)
      const source = context.createBufferSource()
      source.buffer = buffer
      source.connect(destination)
      source.start()
    }
  })
  await page.goto('/')
  await expect(page.locator('.server-status')).toHaveText('서버 연결됨')
  await page.getByRole('button', { name: '음성으로 대화' }).click()
  await voiceState(page, 'listening')

  // 훅은 VAD 프레임을 계속 받는다
  await expect.poll(() => page.evaluate(() => window.__tt_metrics?.frames.length ?? 0)).toBeGreaterThan(10)

  // 첫 말 → 답변이 나오는 중(말하기)에 다시 말한다
  await page.evaluate((s) => window.__speak(s), SPEECH)
  await voiceState(page, 'speaking', 40_000)
  const upload = page.waitForRequest((r) => r.url().includes('/api/barge-in-events') && r.method() === 'POST', {
    timeout: 60_000,
  })
  await page.evaluate((s) => window.__speak(s), SPEECH)
  await voiceState(page, 'listening') // 확정되면 재생을 멈추고 다시 듣는다

  // 끼어든 말이 새 답변 턴을 만들면 기록이 마무리돼 올라간다
  const request = await upload
  const body = request.postDataJSON() as { events: Record<string, unknown>[] }
  expect(body.events).toHaveLength(1)
  const event = body.events[0]
  expect(event).toMatchObject({ result: 'real', session_id: expect.any(String), turn_id: expect.any(String) })
  expect(event.next_turn_id).toEqual(expect.any(String))
  expect(event.probe_to_confirm_ms).toBeGreaterThanOrEqual(0)
  expect(event.stop_ms).toBeGreaterThanOrEqual(0)
  expect((await (await request.response())!.json()) as unknown).toEqual({ accepted: 1 })
  await expect.poll(() => page.evaluate(() => localStorage.getItem('tt.bargeInEvents'))).toBe('[]')

  // 훅: 확정(재생 모드) 뒤에 소스 정지가 오고, 정지는 확정과 같은 흐름(수십 ms 안)이다
  const marks = await page.evaluate(() => window.__tt_metrics?.marks ?? [])
  const confirmIndex = marks.findIndex((m) => m.type === 'vad_confirm' && m.data?.mode === 'playback')
  expect(confirmIndex).toBeGreaterThanOrEqual(0)
  const stop = marks.slice(confirmIndex).find((m) => m.type === 'source_stop')
  expect(stop).toBeDefined()
  expect(stop!.t - marks[confirmIndex].t).toBeLessThan(100)
  expect(marks.map((m) => m.type)).toEqual(expect.arrayContaining(['vad_raw_start', 'vad_end', 'playback_start']))
  await page.screenshot({ path: test.info().outputPath('barge-in.png') })
})
