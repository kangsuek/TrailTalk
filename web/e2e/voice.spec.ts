import { expect, test, type Page } from '@playwright/test'

// 음성 대화 흐름(S3-16): 발화 → 답변 → 끼어들기 → 오프라인 보관과 복구 → 끝내기.
// 가짜 마이크(e2e/fixtures/utterance.wav)는 약 24초마다 한 번 말하고, 서버는 가짜 음성 인식(FAKE_STT_TEXT)과
// 문장마다 0.3초 무음 MP3 합성을 쓴다. 가짜 CLI 녹화(web_search.jsonl) 순서: 인사말 → 웹 검색 → 페이지 읽기 → 메모 저장.
// 오프라인 단계는 Chromium의 오프라인 흉내가 이미 열린 Vite HMR 웹소켓을 끊지 않는 데 기댄다(끊기면 페이지가 새로
// 고쳐져 상태가 사라진다). 브라우저·Playwright를 올린 뒤 이 단계에서만 실패하면 이것부터 의심한다.
const HEARD = '오늘 산책하면서 생각난 아이디어가 있어' // 서버 FAKE_STT_TEXT 기본값

/** 음성 상태 머신 상태(VoiceControls의 data-state)가 될 때까지 기다린다. 문구가 바뀌어도 깨지지 않게 한다 */
const voiceState = (page: Page, state: string, timeout = 20_000) =>
  page.locator(`.voice-controls[data-state="${state}"]`).waitFor({ timeout })

test('음성 대화: 발화·답변·끼어들기·오프라인 복구·끝내기', async ({ page, context }) => {
  test.setTimeout(150_000)
  // 기기 TTS(오프라인 안내)는 운영체제마다 길이가 달라(곧바로 끝나거나 소리를 낸다) 2초 뒤 끝나는 것으로 고정한다
  await page.addInitScript(() => {
    speechSynthesis.speak = (utterance: SpeechSynthesisUtterance) => {
      setTimeout(() => utterance.onend?.(new Event('end') as SpeechSynthesisEvent), 2000)
    }
  })
  await page.goto('/')
  await expect(page.locator('.server-status')).toHaveText('서버 연결됨')
  const log = page.getByRole('log', { name: '대화 내용' })
  const userBubbles = log.locator('.message.user')

  // 1. 시작: 인사말을 들려준 뒤 듣는다
  await page.getByRole('button', { name: '음성으로 대화' }).click()
  await expect(log.getByText('날씨 좋은 날엔 산책이 최고죠!')).toBeVisible()
  await voiceState(page, 'listening')

  // 2. 발화 → 검색 답변을 들려주는 중(문장 수 × 0.3초뿐이라 상태를 바로 잡아 누른다)
  const cancel = page.waitForRequest((r) => r.url().includes('/cancel') && r.method() === 'POST', {
    timeout: 60_000,
  })
  await voiceState(page, 'speaking', 40_000) // 첫 발화를 놓쳐도 다음 주기(24초)가 들어온다
  // 3. 말하는 중에 누르면 끼어들기: 재생을 멈추고 들려준 문장까지만 남긴 뒤 다시 듣는다
  await page.locator('.voice-button').click()
  const request = await cancel
  const lastPlayed = (request.postDataJSON() as { last_played: number }).last_played
  await voiceState(page, 'listening')
  await expect(userBubbles.filter({ hasText: HEARD })).toHaveCount(1)
  await expect(log.getByText(/^출처: /).first()).toBeVisible()
  // 말풍선도 들려준 문장(last_played번까지)만 남는다
  await expect(log.locator('.message.assistant').nth(1).locator('.sentence')).toHaveCount(lastPlayed + 1)

  // 4. 연결이 끊긴 동안 한 말은 기기에 보관했다가, 연결되면 보내 대답을 받는다
  await context.setOffline(true)
  await voiceState(page, 'offline', 40_000)
  await expect(page.getByTestId('queued')).toHaveText(/보관한 말 1개/)
  await voiceState(page, 'listening') // 오프라인 안내 뒤 다시 듣는다
  await context.setOffline(false)
  await expect(userBubbles.filter({ hasText: HEARD })).toHaveCount(2, { timeout: 40_000 })
  await expect(page.getByTestId('queued')).toBeHidden()
  await expect(log.getByText('출처: docs.astral.sh')).toBeVisible() // 녹화의 둘째 답변(페이지 읽기)
  await page.screenshot({ path: test.info().outputPath('voice.png'), fullPage: true })

  // 5. 끝내기: 일지를 정리하고 마무리 멘트를 보인다
  await page.getByRole('button', { name: '대화 끝내기', exact: true }).click()
  await expect(page.getByText('대화가 끝났어요.')).toBeVisible({ timeout: 60_000 })
  await expect(log.getByText(/저장했어요|다음 산책/).last()).toBeVisible()
})
