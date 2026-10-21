import { expect, test } from '@playwright/test'

// 파일 첨부(FR-22): 가짜 CLI는 첨부 내용을 읽지 못하지만, 업로드·가공·저장·표시·삭제는 실제 서버가 한다
// 1x1 PNG를 40x30 크기로 바꾸지 않고 그대로 쓴다(서버가 재인코딩한다)
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
)

test('첨부: 붙이고 보내면 말풍선·일지에 남고, 거절되면 되돌리고, 대화를 지우면 파일도 사라진다', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '글로 대화' }).click()
  const log = page.getByRole('log', { name: '대화 내용' })
  await expect(log.locator('.message.assistant').first()).toBeVisible()
  const attach = page.getByTestId('attach-input')

  // 지원하지 않는 형식은 붙이기 전에 막는다
  await attach.setInputFiles({ name: 'run.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ') })
  await expect(page.getByText(/지원하지 않는 형식/)).toBeVisible()
  await expect(page.getByRole('list', { name: '붙인 파일' })).toHaveCount(0)

  await attach.setInputFiles([
    { name: '지도.png', mimeType: 'image/png', buffer: PNG },
    { name: '메모.txt', mimeType: 'text/plain', buffer: Buffer.from('쓰레기통 위치 메모') },
  ])
  const tray = page.getByRole('list', { name: '붙인 파일' })
  await expect(tray.getByText('지도.png')).toBeVisible()
  await expect(tray.getByText('메모.txt')).toBeVisible()
  await expect(page.getByText('파일과 함께 보낼 질문을 적어 주세요.')).toBeVisible()
  await expect(page.getByRole('button', { name: '보내기' })).toBeDisabled()
  // 터치 대상은 44px 이상
  for (const name of ['지도.png 빼기', '파일 붙이기']) {
    const box = await page.getByRole('button', { name }).boundingBox()
    expect(box!.width).toBeGreaterThanOrEqual(44)
    expect(box!.height).toBeGreaterThanOrEqual(44)
  }
  await page.screenshot({ path: 'test-results/attachment-tray.png' })

  // 서버가 거절하면 말풍선을 빼고 글과 첨부를 되돌린다
  await page.route('**/turns/files', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'attachment_invalid', message: '이미지를 열지 못했어요.' } }),
    }),
  )
  const input = page.getByRole('textbox', { name: '메시지' })
  await input.fill('이 지도 어때?')
  await page.getByRole('button', { name: '보내기' }).click()
  await expect(page.getByRole('alert')).toContainText('이미지를 열지 못했어요.')
  await expect(input).toHaveValue('이 지도 어때?')
  await expect(tray.getByText('지도.png')).toBeVisible()
  await expect(log.getByText('이 지도 어때?')).toHaveCount(0)
  await page.unroute('**/turns/files')

  // 다시 보내면 실제 서버가 받아 가공·저장하고 답한다
  const sent = page.waitForResponse((r) => r.url().endsWith('/turns/files'))
  await page.getByRole('button', { name: '보내기' }).click()
  expect((await sent).status()).toBe(200)
  await expect(log.locator('.message.assistant')).toHaveCount(2)
  const bubble = log.locator('.message.user').last()
  await expect(bubble.getByAltText('지도.png')).toBeVisible()
  await expect(bubble.getByText('메모.txt')).toBeVisible() // 방금 보낸 파일은 서버 ID를 몰라 이름만 보인다
  await expect(bubble.getByText('이 지도 어때?')).toBeVisible()
  await expect(page.getByRole('list', { name: '붙인 파일' })).toHaveCount(0)
  await page.screenshot({ path: 'test-results/attachment-bubble.png' })

  // 끝내면 일지 전문에도 첨부가 남고, 서버가 준 주소로 이미지·텍스트를 받을 수 있다
  const ended = page.waitForResponse((r) => r.url().endsWith('/end'))
  await page.getByRole('button', { name: '대화 끝내기' }).click()
  const closed = await (await ended).json()
  const sessionId: string = closed.session.id
  const detail = page.waitForResponse((r) => r.url().endsWith(`/api/journal/${sessionId}`))
  await page.getByRole('button', { name: '일지 보기' }).click()
  const body = await (await detail).json()
  const attachments = body.turns.flatMap((t: { attachments: { id: string; name: string; mime: string }[] }) => t.attachments)
  expect(attachments.map((a: { name: string }) => a.name).sort()).toEqual(['메모.txt', '지도.png'])
  await page.getByText(/대화 전문 보기/).click()
  const transcript = page.locator('.journal-transcript')
  const thumb = transcript.getByAltText('지도.png')
  await expect(thumb).toBeVisible()
  await expect.poll(() => thumb.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
  const text = attachments.find((a: { name: string }) => a.name === '메모.txt')
  const textResponse = await page.request.get(`/api/attachments/${text.id}`)
  expect(await textResponse.text()).toBe('쓰레기통 위치 메모')
  expect(textResponse.headers()['x-content-type-options']).toBe('nosniff')
  await page.screenshot({ path: 'test-results/attachment-journal.png', fullPage: true })

  // 대화를 지우면 첨부 행과 파일도 사라진다
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '이 대화 삭제' }).click()
  await expect.poll(async () => (await page.request.get(`/api/attachments/${text.id}`)).status()).toBe(404)
})
