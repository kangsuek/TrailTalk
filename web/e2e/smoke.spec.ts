import { expect, test } from '@playwright/test'

test('서버에 연결되고 4개 화면을 전환한다', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('status')).toHaveText('서버 연결됨')

  for (const name of ['대화', '일지 목록', '일지 상세', '설정']) {
    await page.getByRole('tab', { name }).click()
    await expect(page.getByRole('heading', { level: 2, name })).toBeVisible()
  }

  await page.getByRole('tab', { name: '대화' }).click()
  await page.screenshot({ path: 'test-results/smoke.png', fullPage: true })
})
