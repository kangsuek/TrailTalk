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
    await page.getByRole('tab', { name: '일지 목록' }).click()
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
  await expect(page.getByRole('tab', { name: '일지 상세' })).toHaveAttribute('aria-selected', 'true')
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

  await page.getByRole('tab', { name: '일지 목록' }).click()
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
  await page.getByRole('tab', { name: '일지 목록' }).click()
  const title = `이름 바꾼 대화 ${Date.now()}`
  await page.getByRole('button', { name: '제목 수정: Claude Code 최신 버전과 uv 알아보기' }).first().click()
  await expect(page.getByRole('tab', { name: '일지 목록' })).toHaveAttribute('aria-selected', 'true') // 상세로 가지 않는다
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
  await page.getByRole('tab', { name: '일지 목록' }).click()
  await expect(page.getByRole('button', { name: `제목 수정: ${title}` })).toBeVisible()

  // 카드의 제목 밖을 누르면 상세가 열린다
  await page.getByRole('button', { name: new RegExp(`^${title}`) }).click()
  await expect(page.getByRole('heading', { level: 3, name: title })).toBeVisible()
  await page.getByRole('tab', { name: '일지 목록' }).click()

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
  await page.getByRole('tab', { name: '일지 목록' }).click()
  await expect(page.getByText(/불러오는 중/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: `제목 수정: ${title}` })).toHaveCount(0)
})
