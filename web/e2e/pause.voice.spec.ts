import { expect, test } from '@playwright/test'

// 듣는 중 일시 중단 버튼: 마이크를 끄고 쉬며(말을 보내지 않는다), 큰 버튼으로 다시 듣는다.
// 가짜 마이크(utterance.wav)는 마이크를 켠 뒤 약 1초부터 말하므로 듣기가 되자마자 누른다
test('듣는 중 일시 중단하고 큰 버튼으로 다시 듣기', async ({ page }) => {
  test.setTimeout(90_000)
  const audioTurns: string[] = []
  page.on('request', (r) => {
    if (r.url().includes('/turns/audio') && r.method() === 'POST') audioTurns.push(r.url())
  })
  await page.goto('/')
  await expect(page.locator('.server-status')).toHaveText('서버 연결됨')
  const log = page.getByRole('log', { name: '대화 내용' })

  await page.getByRole('button', { name: '음성으로 대화' }).click()
  await expect(log.getByText('날씨 좋은 날엔 산책이 최고죠!')).toBeVisible()
  await page.locator('.voice-controls[data-state="listening"]').waitFor({ timeout: 20_000 })
  await expect(page.locator('.voice-status')).toHaveText('듣고 있어요')
  await page.screenshot({ path: 'test-results/pause-listening.png' })
  // 폰에서 누르기 쉽게 터치 영역은 44px 이상
  const box = await page.getByRole('button', { name: '일시 중단', exact: true }).boundingBox()
  expect(box?.height).toBeGreaterThanOrEqual(44)

  await page.getByRole('button', { name: '일시 중단', exact: true }).click()
  await expect(page.locator('.voice-controls[data-state="paused"]')).toBeVisible()
  await expect(page.locator('.voice-status')).toHaveText('쉬는 중')
  await expect(page.getByRole('button', { name: '일시 중단', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '대화 끝내기', exact: true })).toBeVisible()
  await page.screenshot({ path: 'test-results/pause-paused.png' })

  // 쉬는 동안에는 가짜 마이크가 말해도 보내지 않는다
  await page.waitForTimeout(8_000)
  expect(audioTurns).toEqual([])
  await expect(page.locator('.voice-controls[data-state="paused"]')).toBeVisible()

  // 큰 버튼 한 번으로 다시 듣는다
  await page.locator('button.voice-button').click()
  await expect(page.locator('.voice-controls[data-state="listening"]')).toBeVisible()
  await expect(page.getByRole('button', { name: '일시 중단', exact: true })).toBeVisible()
})
