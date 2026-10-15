import { expect, test } from '@playwright/test'

// 가짜 CLI 녹화(web_search.jsonl) 순서: 인사말 → 웹 검색 → 페이지 읽기 → 메모 저장
test('텍스트 대화: 인사말, 문장 말풍선, 도구 알림, 끝내기', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('status')).toHaveText('서버 연결됨')

  await page.getByRole('button', { name: '대화 시작' }).click()
  const log = page.getByRole('log', { name: '대화 내용' })
  await expect(log.getByText('날씨 좋은 날엔 산책이 최고죠!')).toBeVisible()
  // 캐릭터 이름은 서버(페르소나 YAML)가 준 값을 쓴다. 코드에 이름을 두지 않으므로 비어 있지 않은지만 본다
  await expect(log.locator('.message.assistant .speaker').first()).toHaveText(/\S/)

  const input = page.getByRole('textbox', { name: '메시지' })
  const send = async (text: string) => {
    await input.fill(text)
    await page.getByRole('button', { name: '보내기' }).click()
    await expect(log.getByText(text)).toBeVisible()
  }

  await send('Claude Code 최신 버전 알려줘')
  await expect(log.getByText(/^출처: /).first()).toBeVisible()
  await expect(log.getByText('검색해 봤어요, 다니엘님! 😊')).toBeVisible()

  await send('uv 공식 문서 읽고 요약해줘')
  await expect(log.getByText('출처: docs.astral.sh')).toBeVisible()

  await send('방금 내용 메모로 저장해줘')
  await expect(log.getByText(/^메모 저장: uv: /)).toBeVisible()
  await expect(page.getByRole('button', { name: '보내기' })).toBeDisabled() // 입력창이 비었다
  await expect(log.getByText('메모로 저장했어요, 다니엘님!', { exact: false })).toBeInViewport()
  await page.screenshot({ path: 'test-results/conversation.png' })

  await page.getByRole('button', { name: '대화 끝내기' }).click()
  await expect(page.getByText('대화가 끝났어요.')).toBeVisible()
  // 마무리 멘트: 문구는 페르소나 YAML, 개수는 서버가 일지 정리(가짜 CLI 추출 픽스처) 뒤 채운다
  await expect(log.getByText(/아이디어 1개, 할 일 1개, 메모 1개/)).toBeVisible()
  await expect(input).toBeHidden()
  await page.screenshot({ path: 'test-results/conversation-ended.png', fullPage: true })
})
