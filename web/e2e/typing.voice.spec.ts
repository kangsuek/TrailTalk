import { expect, test } from '@playwright/test'
import { expectLastBubbleAboveDock } from './helpers.js'

// 음성 대화 중 글 입력(S3-21): 듣는 중에 글로 보내면 말 한 번처럼 보내고, 답변을 소리로 들려준 뒤 다시 듣는다.
// 가짜 마이크(utterance.wav)가 중간에 말해도(약 24초 주기) 그 말은 큐 뒤에 이어 보내지므로 결과 확인에는 지장이 없다
test('음성 대화 중 글로 보내기', async ({ page }) => {
  test.setTimeout(90_000)
  await page.goto('/')
  await expect(page.locator('.server-status')).toHaveText('서버 연결됨')
  const log = page.getByRole('log', { name: '대화 내용' })

  await page.getByRole('button', { name: '음성으로 대화' }).click()
  await expect(log.getByText('날씨 좋은 날엔 산책이 최고죠!')).toBeVisible()
  await page.locator('.voice-controls[data-state="listening"]').waitFor({ timeout: 20_000 })

  const typed = '말 대신 글로 물어볼게요'
  const input = page.getByRole('textbox', { name: '메시지' })
  await input.fill(typed)
  await page.screenshot({ path: 'test-results/voice-typing.png' })
  const turn = page.waitForRequest((r) => r.url().endsWith('/turns') && r.method() === 'POST')
  await page.getByRole('button', { name: '보내기' }).click()
  expect((await turn).postDataJSON()).toEqual({ text: typed })
  await expect(input).toHaveValue('')
  await expect(log.locator('.message.user').filter({ hasText: typed })).toHaveCount(1)
  // 답변(검색 답변)을 들려준 뒤 다시 듣는다
  await expect(log.locator('.message.assistant')).toHaveCount(2, { timeout: 20_000 })
  await page.locator('.voice-controls[data-state="listening"]').waitFor({ timeout: 30_000 })
  await expectLastBubbleAboveDock(page)
  await page.screenshot({ path: 'test-results/voice-typed-answer.png' })
})
