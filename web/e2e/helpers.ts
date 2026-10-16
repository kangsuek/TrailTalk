import { expect, type Page } from '@playwright/test'

/** 마지막 말풍선이 화면 아래 고정 패널(입력창·음성 버튼)에 가리지 않고 모두 보이는지 본다 */
export async function expectLastBubbleAboveDock(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(() => {
        const last = [...document.querySelectorAll('.message')].pop()?.getBoundingClientRect()
        const dock = document.querySelector('.composer, .voice-controls')?.getBoundingClientRect()
        return last && dock ? Math.round(dock.top - last.bottom) : -1
      }),
    )
    .toBeGreaterThanOrEqual(0)
}
