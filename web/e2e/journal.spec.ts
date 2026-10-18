import { expect, test } from '@playwright/test'

// 대화를 끝내면 서버가 일지를 정리한다(가짜 CLI 추출 픽스처 extract.jsonl: 아이디어·할 일·메모 1개씩)
test('일지: 목록 → 상세, 별표·완료(할 일·아이디어) 표시가 저장된다', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '글로 대화' }).click()
  const log = page.getByRole('log', { name: '대화 내용' })
  await expect(log.locator('.message.assistant').first()).toBeVisible()
  await page.getByRole('textbox', { name: '메시지' }).fill('Claude Code 최신 버전 알려줘')
  await page.getByRole('button', { name: '보내기' }).click()
  await expect(log.locator('.message.assistant')).toHaveCount(2)
  const ended = page.waitForResponse((r) => r.url().endsWith('/end'))
  await page.getByRole('button', { name: '대화 끝내기' }).click()
  const closed = await (await ended).json()
  expect(closed.journal_status).toBe('done')
  await expect(page.getByText('대화가 끝났어요.')).toBeVisible()

  // 다른 spec이 같은 제목의 일지를 먼저 만들었을 수 있다. 최신순 첫 항목이 이 대화인지 상세 요청으로 확인한다
  const openLatest = async () => {
    await page.getByRole('tab', { name: '일지' }).click()
    const detail = page.waitForResponse((r) => r.url().endsWith(`/api/journal/${closed.session.id}`))
    await page.getByRole('button', { name: /^Claude Code 최신 버전과 uv 알아보기/ }).first().click()
    await detail
    await expect(page.getByRole('heading', { level: 3, name: 'Claude Code 최신 버전과 uv 알아보기' })).toBeVisible()
  }

  // 끝난 대화 화면의 "일지 보기"로 바로 그 대화의 일지를 연다
  const detail = page.waitForResponse((r) => r.url().endsWith(`/api/journal/${closed.session.id}`))
  await page.getByRole('button', { name: '일지 보기' }).click()
  await detail
  await expect(page.getByRole('heading', { level: 3, name: 'Claude Code 최신 버전과 uv 알아보기' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '일지' })).toHaveAttribute('aria-selected', 'true')
  // 새 형식(S3-24): 결론(굵게) → 알게 된 것 → 확인할 것 → 노트 → 인용 → #태그. 출처 번호는 녹화가 인용한 1·2·9번
  const conclusion = page.getByLabel('결론')
  await expect(conclusion.locator('strong')).toHaveText('Claude Code 최신 버전 소식을 확인하고 uv 공식 문서의 핵심을 정리했다.')
  await expect(conclusion).toContainText('[1][2]')
  const found = page.getByRole('region', { name: '알게 된 것' })
  await expect(found.getByRole('listitem')).toHaveCount(2)
  await expect(found.getByRole('listitem').last()).toContainText('uv: 파이썬 패키지와 프로젝트를 관리하는 빠른 도구다.[3]')
  await expect(page.getByRole('region', { name: '확인할 것' })).toContainText('Claude Code 공식 최신 버전 번호')
  const cited = page.getByRole('region', { name: '인용' })
  await expect(cited.getByRole('link')).toHaveCount(3)
  await expect(cited.getByRole('link').first()).toHaveAttribute('href', /^https:\/\//)

  const star = page.getByRole('button', { name: '별표: 산책하면서 개발 도구 소식을 음성으로 듣는 습관 만들기' })
  const todo = page.getByRole('checkbox', { name: 'Claude Code를 최신 버전으로 업데이트하기' })
  await expect(star).toHaveAttribute('aria-pressed', 'false')
  await expect(todo).not.toBeChecked()
  const saved = page.waitForResponse((r) => r.url().includes('/api/notes/') && r.request().method() === 'PATCH')
  await star.click()
  await saved
  const done = page.waitForResponse((r) => r.url().includes('/api/notes/') && r.request().method() === 'PATCH')
  await todo.check()
  await done
  const ideaDone = page.getByRole('button', { name: '완료: 산책하면서 개발 도구 소식을 음성으로 듣는 습관 만들기' })
  const closedIdea = page.waitForResponse((r) => r.url().includes('/api/notes/') && r.request().method() === 'PATCH')
  await ideaDone.click()
  await closedIdea

  await page.getByText(/대화 전문 보기/).click()
  await expect(page.locator('.journal-transcript').getByText('Claude Code 최신 버전 알려줘')).toBeVisible()
  await page.screenshot({ path: 'test-results/journal-detail.png', fullPage: true })

  // 새로고침해도(서버에 저장됨) 별표·완료가 남아 있다
  await page.reload()
  await openLatest()
  await expect(star).toHaveAttribute('aria-pressed', 'true')
  await expect(todo).toBeChecked()
  await expect(ideaDone).toHaveAttribute('aria-pressed', 'true')

  await page.getByRole('tab', { name: '일지' }).click()
  await expect(page.getByText(/아이디어 1 · 할 일 1 · 메모 1/).first()).toBeVisible()
  await page.screenshot({ path: 'test-results/journal-list.png', fullPage: true })
})

test('일지 목록: 제목을 눌러 고치고(포커스가 떠나면 저장, 새로고침 뒤에도 유지) 쓰레기통으로 지운다', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '글로 대화' }).click()
  const log = page.getByRole('log', { name: '대화 내용' })
  await expect(log.locator('.message.assistant').first()).toBeVisible()
  await page.getByRole('textbox', { name: '메시지' }).fill('Claude Code 최신 버전 알려줘')
  await page.getByRole('button', { name: '보내기' }).click()
  await expect(log.locator('.message.assistant')).toHaveCount(2)
  const ended = page.waitForResponse((r) => r.url().endsWith('/end'))
  await page.getByRole('button', { name: '대화 끝내기' }).click()
  const closed = await (await ended).json()

  // 최신순 첫 항목이 방금 끝낸 대화다(다른 spec이 같은 제목을 먼저 만들었을 수 있다)
  await page.getByRole('tab', { name: '일지' }).click()
  const title = `이름 바꾼 대화 ${Date.now()}`
  await page.getByRole('button', { name: '제목 수정: Claude Code 최신 버전과 uv 알아보기' }).first().click()
  await expect(page.getByRole('heading', { level: 2, name: '일지 목록' })).toBeVisible() // 상세로 가지 않는다
  const input = page.getByRole('textbox', { name: '대화 제목' })
  await expect(input).toBeFocused()
  await input.fill(title)
  await page.screenshot({ path: 'test-results/journal-list-editing.png', fullPage: true })
  const renamed = page.waitForResponse(
    (r) => r.url().endsWith(`/api/journal/${closed.session.id}`) && r.request().method() === 'PATCH',
  )
  await page.getByRole('heading', { name: '일지 목록', level: 2 }).click() // 다른 곳을 누르면(포커스 이동) 저장
  expect((await renamed).status()).toBe(200)
  await expect(page.getByRole('button', { name: `제목 수정: ${title}` })).toBeVisible()
  await page.screenshot({ path: 'test-results/journal-list-renamed.png', fullPage: true })

  await page.reload()
  await page.getByRole('tab', { name: '일지' }).click()
  await expect(page.getByRole('button', { name: `제목 수정: ${title}` })).toBeVisible()

  // 카드의 제목 밖을 누르면 상세가 열린다
  await page.getByRole('button', { name: new RegExp(`^${title}`) }).click()
  await expect(page.getByRole('heading', { level: 3, name: title })).toBeVisible()
  await page.getByRole('tab', { name: '일지' }).click()

  let message = ''
  page.once('dialog', (dialog) => {
    message = dialog.message()
    void dialog.accept()
  })
  const removed = page.waitForResponse((r) => r.request().method() === 'DELETE')
  await page.getByRole('button', { name: `삭제: ${title}` }).click()
  expect((await removed).status()).toBe(204)
  expect(message).toBe('이 대화와 노트·전문을 모두 지울까요?')
  await expect(page.getByRole('button', { name: `제목 수정: ${title}` })).toHaveCount(0)
  await page.reload()
  await page.getByRole('tab', { name: '일지' }).click()
  await expect(page.getByText(/불러오는 중/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: `제목 수정: ${title}` })).toHaveCount(0)
})

test('일지 목록: 여러 개를 골라 한 번에 지운다', async ({ page }) => {
  // 대화 2개를 끝내고 서로 다른 제목을 붙인다(다른 spec의 같은 제목 일지와 섞이지 않게)
  const stamp = Date.now()
  const titles = [`골라 지울 대화 A ${stamp}`, `골라 지울 대화 B ${stamp}`]
  await page.goto('/')
  for (const title of titles) {
    await page.getByRole('tab', { name: '대화', exact: true }).click()
    await page.getByRole('button', { name: /^글로 (새 )?대화$/ }).click() // 끝낸 뒤에는 "글로 새 대화"
    const log = page.getByRole('log', { name: '대화 내용' })
    await expect(log.locator('.message.assistant').first()).toBeVisible()
    await page.getByRole('textbox', { name: '메시지' }).fill('Claude Code 최신 버전 알려줘')
    await page.getByRole('button', { name: '보내기' }).click()
    await expect(log.locator('.message.assistant')).toHaveCount(2)
    const ended = page.waitForResponse((r) => r.url().endsWith('/end'))
    await page.getByRole('button', { name: '대화 끝내기' }).click()
    const closed = await (await ended).json()
    expect((await page.request.patch(`/api/journal/${closed.session.id}`, { data: { title } })).status()).toBe(200)
  }

  await page.getByRole('tab', { name: '일지' }).click()
  await page.getByRole('button', { name: '선택', exact: true }).click()
  for (const title of titles) await page.getByText(title).click() // 카드를 눌러 고른다
  await expect(page.getByText('2개 선택')).toBeVisible()
  await page.screenshot({ path: 'test-results/journal-list-selecting.png', fullPage: true })

  let message = ''
  page.once('dialog', (dialog) => {
    message = dialog.message()
    void dialog.accept()
  })
  await page.getByRole('button', { name: '삭제 (2)' }).click()
  await expect(page.getByRole('checkbox')).toHaveCount(0) // 다 지우면 선택 모드가 닫힌다
  expect(message).toBe('선택한 2개 대화와 노트·전문을 모두 지울까요?')
  for (const title of titles) await expect(page.getByText(title)).toHaveCount(0)
  await page.reload()
  await page.getByRole('tab', { name: '일지' }).click()
  await expect(page.getByText(/불러오는 중/)).toHaveCount(0)
  for (const title of titles) await expect(page.getByText(title)).toHaveCount(0)
})

// 이어서 하기(S3-26): 끝난 대화를 일지 상세에서 다시 열어 같은 일지에 이어 쓴다
test('일지 상세: 끝난 대화를 글로 이어서 하고, 다시 끝내면 같은 일지에 쌓인다', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /^글로 (새 )?대화$/ }).click()
  const log = page.getByRole('log', { name: '대화 내용' })
  await expect(log.locator('.message.assistant').first()).toBeVisible()
  await page.getByRole('textbox', { name: '메시지' }).fill('Claude Code 최신 버전 알려줘')
  await page.getByRole('button', { name: '보내기' }).click()
  await expect(log.locator('.message.assistant')).toHaveCount(2)
  const ended = page.waitForResponse((r) => r.url().endsWith('/end'))
  await page.getByRole('button', { name: '대화 끝내기' }).click()
  const closed = await (await ended).json()
  const id = closed.session.id

  await page.getByRole('button', { name: '일지 보기' }).click()
  const reopened = page.waitForResponse((r) => r.url().endsWith(`/api/sessions/${id}/reopen`))
  await page.getByRole('button', { name: '글로 이어서' }).click()
  expect((await reopened).status()).toBe(200)
  await expect(page.getByRole('tab', { name: '대화', exact: true })).toHaveAttribute('aria-selected', 'true')
  // 이전 말풍선(인사말·질문·답변)에 재개 인사말이 더해진다
  await expect(log.locator('.message.user').filter({ hasText: 'Claude Code 최신 버전 알려줘' })).toHaveCount(1)
  await expect(log.locator('.message.assistant')).toHaveCount(3)
  await expect(page.getByRole('textbox', { name: '메시지' })).toBeFocused()
  await page.screenshot({ path: 'test-results/journal-continued.png', fullPage: true })

  await page.getByRole('textbox', { name: '메시지' }).fill('이어서 더 알려줘')
  await page.getByRole('button', { name: '보내기' }).click()
  await expect(log.locator('.message.assistant')).toHaveCount(4)
  const reEnded = page.waitForResponse((r) => r.url().endsWith('/end'))
  await page.getByRole('button', { name: '대화 끝내기' }).click()
  const again = await (await reEnded).json()
  expect(again.session.id).toBe(id) // 같은 일지다
  expect(again.journal_status).toBe('done')

  await page.getByRole('button', { name: '일지 보기' }).click()
  await page.getByText(/대화 전문 보기/).click()
  const transcript = page.locator('.journal-transcript')
  await expect(transcript.getByText('이어서 더 알려줘')).toBeVisible()
  await expect(transcript.getByText('Claude Code 최신 버전 알려줘')).toBeVisible()
})

// 일지 상세에서 삭제(S3-29): 확인 뒤 지우고 목록으로 돌아간다
test('일지 상세: 맨 아래 삭제 버튼으로 지우면 목록으로 돌아가고 다시 보이지 않는다', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /^글로 (새 )?대화$/ }).click()
  const log = page.getByRole('log', { name: '대화 내용' })
  await expect(log.locator('.message.assistant').first()).toBeVisible()
  await page.getByRole('textbox', { name: '메시지' }).fill('Claude Code 최신 버전 알려줘')
  await page.getByRole('button', { name: '보내기' }).click()
  await expect(log.locator('.message.assistant')).toHaveCount(2)
  const ended = page.waitForResponse((r) => r.url().endsWith('/end'))
  await page.getByRole('button', { name: '대화 끝내기' }).click()
  const id = (await (await ended).json()).session.id
  const title = `상세에서 지울 대화 ${Date.now()}`
  expect((await page.request.patch(`/api/journal/${id}`, { data: { title } })).status()).toBe(200)

  await page.getByRole('button', { name: '일지 보기' }).click()
  await expect(page.getByRole('heading', { level: 3, name: title })).toBeVisible()
  let message = ''
  page.once('dialog', (dialog) => {
    message = dialog.message()
    void dialog.accept()
  })
  const removed = page.waitForResponse((r) => r.url().endsWith(`/api/journal/${id}`) && r.request().method() === 'DELETE')
  await page.getByRole('button', { name: '이 대화 삭제' }).click()
  expect((await removed).status()).toBe(204)
  expect(message).toBe('이 대화와 노트·전문을 모두 지울까요?')
  await expect(page.getByRole('heading', { level: 2, name: '일지 목록' })).toBeVisible()
  await expect(page.getByText(/불러오는 중/)).toHaveCount(0)
  await expect(page.getByText(title)).toHaveCount(0)
  await page.reload()
  await page.getByRole('tab', { name: '일지' }).click()
  await expect(page.getByText(/불러오는 중/)).toHaveCount(0)
  await expect(page.getByText(title)).toHaveCount(0)
})

// 지워진 대화 안내(S3-30): 대화 탭이 끝난 대화를 들고 있는 동안 그 일지를 지우면 "일지 보기"가 안내를 보인다
test('지운 대화를 대화 탭의 일지 보기로 열면 지워졌다고 안내한다', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /^글로 (새 )?대화$/ }).click()
  const log = page.getByRole('log', { name: '대화 내용' })
  await expect(log.locator('.message.assistant').first()).toBeVisible()
  await page.getByRole('textbox', { name: '메시지' }).fill('Claude Code 최신 버전 알려줘')
  await page.getByRole('button', { name: '보내기' }).click()
  await expect(log.locator('.message.assistant')).toHaveCount(2)
  const ended = page.waitForResponse((r) => r.url().endsWith('/end'))
  await page.getByRole('button', { name: '대화 끝내기' }).click()
  const id = (await (await ended).json()).session.id
  expect((await page.request.delete(`/api/journal/${id}`)).status()).toBe(204) // 다른 곳(목록·다른 기기)에서 지웠다

  await page.getByRole('button', { name: '일지 보기' }).click()
  await expect(page.getByText('지워진 대화예요. 일지 목록에서 다른 대화를 골라 주세요.')).toBeVisible()
  await expect(page.getByRole('button', { name: '다시 불러오기' })).toHaveCount(0)
  await page.screenshot({ path: 'test-results/journal-deleted.png' })
  await page.getByRole('button', { name: '일지 목록으로' }).click()
  await expect(page.getByRole('heading', { level: 2, name: '일지 목록' })).toBeVisible()
})
