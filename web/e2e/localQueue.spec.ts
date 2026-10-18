/// <reference lib="dom" />
import { expect, test } from '@playwright/test'

// 오프라인 큐(S3-12)의 브라우저 저장소. 새로 고쳐도 남아야 한다(서버 대화는 부르지 않는다)

test('IndexedDB 큐에 녹음을 보관하고 새로 고친 뒤에도 꺼낸다', async ({ page }) => {
  // 새로 고칠 때 앱이 다른 대화의 남은 말로 보고 기록하려 하므로(그러면 지운다) 기록 요청을 막는다
  await page.route('**/turns/audio/record', (route) => route.abort())
  await page.goto('/')
  const modulePath = '/src/platform/localQueue.ts' // 개발 서버가 서빙하는 소스 경로
  await page.evaluate(async (path) => {
    const { createLocalQueue } = await import(path)
    const queue = createLocalQueue()
    // 기준 시각은 한 번만 잡는다(넣는 사이 시간이 흘러 e2e-1이 더 늦어지지 않게)
    const now = Date.now()
    for (const id of ['e2e-2', 'e2e-1']) {
      await queue.add({
        id,
        sessionId: 'e2e-session',
        mimeType: 'audio/webm',
        bytes: new Uint8Array([id === 'e2e-1' ? 1 : 2]),
        createdAt: now + (id === 'e2e-1' ? 0 : 1), // 30일 기한 안(지나면 앱이 지운다)
        attempts: 0,
      })
    }
  }, modulePath)

  await page.reload()
  const result = await page.evaluate(async (path) => {
    const { createLocalQueue } = await import(path)
    const queue = createLocalQueue()
    const first = await queue.oldest('e2e-session')
    const count = await queue.count('e2e-session')
    await queue.remove('e2e-1')
    await queue.remove('e2e-2')
    return { id: first?.id, byte: first?.bytes[0], count, after: await queue.count('e2e-session') }
  }, modulePath)
  expect(result).toEqual({ id: 'e2e-1', byte: 1, count: 2, after: 0 })
})
