import { expect, test } from '@playwright/test'

// 이어서 하기(S3-26): 끝난 글 대화를 일지 상세에서 음성으로 이어서 하면 이전 말풍선이 보인 채 재개 인사말을 듣고 듣기로 간다
test('일지 상세: 끝난 대화를 음성으로 이어서 하기', async ({ page }) => {
  test.setTimeout(90_000)
  await page.goto('/')
  await expect(page.locator('.server-status')).toHaveText('서버 연결됨')
  await page.getByRole('button', { name: '글로 대화' }).click()
  const log = page.getByRole('log', { name: '대화 내용' })
  await expect(log.locator('.message.assistant').first()).toBeVisible()
  await page.getByRole('textbox', { name: '메시지' }).fill('글로 먼저 물어볼게요')
  await page.getByRole('button', { name: '보내기' }).click()
  await expect(log.locator('.message.assistant')).toHaveCount(2)
  await page.getByRole('button', { name: '대화 끝내기' }).click()
  await page.getByRole('button', { name: '일지 보기' }).click()

  const reopened = page.waitForRequest((r) => r.url().endsWith('/reopen'))
  await page.getByRole('button', { name: '음성으로 이어서' }).click()
  expect((await reopened).postDataJSON()).toEqual({ mode: 'voice' })
  await expect(page.getByRole('tab', { name: '대화', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(log.locator('.message.user').filter({ hasText: '글로 먼저 물어볼게요' })).toHaveCount(1)
  await expect(log.locator('.message.assistant')).toHaveCount(3)
  await page.locator('.voice-controls[data-state="listening"]').waitFor({ timeout: 20_000 })
  await page.screenshot({ path: 'test-results/voice-continued.png' })

  await page.getByRole('button', { name: '대화 끝내기', exact: true }).click()
  await expect(page.locator('.voice-controls')).toHaveCount(0, { timeout: 30_000 })
})
