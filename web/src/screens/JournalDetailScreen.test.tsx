import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { JournalDetailScreen } from './JournalDetailScreen'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const DETAIL = {
  session: {
    id: 's1',
    date: '2026-10-15',
    started_at: '2026-10-15T00:00:00Z',
    ended_at: '2026-10-15T00:10:00Z',
    status: 'ended',
    title: '쓰레기통 지도',
    summary: ['등산로 쓰레기통 지도를 이야기했다.', '데이터를 찾아보기로 했다.'],
    tags: ['등산', '지도'],
    journal_status: 'done',
    counts: { idea: 1, todo: 1, memo: 1 },
  },
  persona_name: '도우미',
  notes: [
    { id: 'n1', kind: 'idea', content: '쓰레기통 지도 앱', starred: false, done: false, created_at: '' },
    { id: 'n2', kind: 'todo', content: '공공데이터 찾기', starred: false, done: false, created_at: '' },
    { id: 'n3', kind: 'memo', content: '구청에 문의 가능', starred: false, done: false, created_at: '' },
  ],
  turns: [
    { id: 't0', seq: 0, role: 'assistant', text: '안녕하세요!', interrupted: false, created_at: '' },
    { id: 't1', seq: 1, role: 'user', text: '지도 앱 어때?', interrupted: false, created_at: '' },
    { id: 't2', seq: 2, role: 'assistant', text: '좋아요.', interrupted: true, created_at: '' },
  ],
}

function stub(patch: (body: Record<string, unknown>) => Response = (body) =>
  new Response(JSON.stringify({ ...DETAIL.notes[0], ...body }))) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/journal/s1') return new Response(JSON.stringify(DETAIL))
    if (url.startsWith('/api/notes/') && init?.method === 'PATCH') {
      return patch(JSON.parse(String(init.body)))
    }
    throw new Error(`unexpected ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('JournalDetailScreen', () => {
  it('세션을 고르지 않았으면 목록으로 안내한다', () => {
    const onBack = vi.fn()
    render(<JournalDetailScreen onBack={onBack} />)
    expect(screen.getByText('일지 목록에서 볼 대화를 골라 주세요.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '일지 목록으로' }))
    expect(onBack).toHaveBeenCalled()
  })

  it('요약·태그·노트를 보이고, 전문은 펼쳐서 본다', async () => {
    stub()
    render(<JournalDetailScreen sessionId="s1" />)
    expect(await screen.findByRole('heading', { level: 3, name: '쓰레기통 지도' })).toBeInTheDocument()
    expect(screen.getByText('10월 15일 (목)')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: '요약' })).getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('#등산 #지도')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: '메모' })).getByText('구청에 문의 가능')).toBeInTheDocument()

    const transcript = screen.getByText('대화 전문 보기 (3)').closest('details')!
    expect(transcript.open).toBe(false)
    expect(within(transcript).getAllByText('도우미')).toHaveLength(2) // 화자 이름은 서버가 준다
    expect(within(transcript).getByText('(말이 끊김)', { exact: false })).toBeInTheDocument()
  })

  it('아이디어 별표와 할 일 완료를 바꾸면 저장한다', async () => {
    const fetchMock = stub((body) => new Response(JSON.stringify({ ...DETAIL.notes[0], ...body })))
    render(<JournalDetailScreen sessionId="s1" />)
    const star = await screen.findByRole('button', { name: '별표: 쓰레기통 지도 앱' })
    expect(star).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(star)
    expect(star).toHaveAttribute('aria-pressed', 'true') // 응답 전에 먼저 바뀐다
    const todo = screen.getByRole('checkbox', { name: '공공데이터 찾기' })
    fireEvent.click(todo)
    expect(todo).toBeChecked()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    const patches = fetchMock.mock.calls.slice(1).map(([url, init]) => [url, JSON.parse(String(init!.body))])
    expect(patches).toEqual([
      ['/api/notes/n1', { starred: true }],
      ['/api/notes/n2', { done: true }],
    ])
  })

  it('아이디어도 완료로 닫을 수 있다(다음 대화의 기억에서 빠진다)', async () => {
    const fetchMock = stub((body) => new Response(JSON.stringify({ ...DETAIL.notes[0], ...body })))
    render(<JournalDetailScreen sessionId="s1" />)
    const done = await screen.findByRole('button', { name: '완료: 쓰레기통 지도 앱' })
    expect(done).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(done)
    expect(done).toHaveAttribute('aria-pressed', 'true')
    expect(done).toHaveTextContent('완료됨')
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]!.body))).toEqual({ done: true })
  })

  it.each([
    ['failed', '일지 정리에 실패했어요. 대화 전문은 아래에서 볼 수 있어요.'],
    [null, '아직 정리하지 않은 대화예요.'],
  ])('정리 상태가 %s면 다시 정리하고 끝날 때까지 다시 불러온다', async (status, message) => {
    let phase = 'before'
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/journal/s1/retry' && init?.method === 'POST') {
        phase = 'pending'
        return new Response(JSON.stringify({ ...DETAIL.session, journal_status: 'pending' }), { status: 202 })
      }
      const journal_status = phase === 'before' ? status : 'done'
      const checks = phase === 'before' ? null : [] // 정리가 끝나면 새 형식(S3-24)
      return new Response(JSON.stringify({ ...DETAIL, checks, session: { ...DETAIL.session, journal_status } }))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<JournalDetailScreen sessionId="s1" pollMs={10} />)
    expect(await screen.findByText(message)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '다시 정리' }))
    expect(await screen.findByText('일지를 정리하는 중이에요. 끝나면 자동으로 보여 드려요.')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('일지를 정리하는 중이에요. 끝나면 자동으로 보여 드려요.')).toBeNull())
    expect(screen.queryByRole('button', { name: '다시 정리' })).toBeNull()
  })

  it('끝나지 않은 대화에는 다시 정리를 보이지 않는다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ ...DETAIL, session: { ...DETAIL.session, status: 'active', journal_status: null } }))),
    )
    render(<JournalDetailScreen sessionId="s1" />)
    await screen.findByRole('heading', { level: 3 })
    expect(screen.queryByRole('button', { name: '다시 정리' })).toBeNull()
    expect(screen.getByText('아직 진행 중인 대화예요. 대화를 끝내면 일지로 정리돼요.')).toBeInTheDocument()
    expect(screen.queryByText('저장한 아이디어·할 일·메모가 없어요.')).toBeNull()
  })

  it('저장에 실패하면 되돌리고 알린다', async () => {
    stub(() => new Response(JSON.stringify({ error: { code: 'note_not_found', message: '노트를 찾을 수 없습니다.' } }), { status: 404 }))
    render(<JournalDetailScreen sessionId="s1" />)
    const star = await screen.findByRole('button', { name: '별표: 쓰레기통 지도 앱' })
    fireEvent.click(star)
    expect(await screen.findByRole('alert')).toHaveTextContent('노트를 찾을 수 없습니다.')
    expect(star).toHaveAttribute('aria-pressed', 'false')
  })

  it('빠르게 두 번 바꾸면 옛 요청의 응답이 최신 화면을 덮지 않는다', async () => {
    const pending: ((r: Response) => void)[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url === '/api/journal/s1'
          ? new Response(JSON.stringify(DETAIL))
          : new Promise<Response>((resolve) => pending.push(resolve)),
      ),
    )
    render(<JournalDetailScreen sessionId="s1" />)
    const star = await screen.findByRole('button', { name: '별표: 쓰레기통 지도 앱' })
    fireEvent.click(star) // 켜기
    fireEvent.click(star) // 끄기
    expect(star).toHaveAttribute('aria-pressed', 'false')
    // 두 번째(끄기) 응답이 먼저, 첫 번째(켜기) 응답이 나중에 온다
    pending[1](new Response(JSON.stringify({ ...DETAIL.notes[0], starred: false })))
    pending[0](new Response(JSON.stringify({ ...DETAIL.notes[0], starred: true })))
    await waitFor(() => expect(pending).toHaveLength(2))
    await new Promise((r) => setTimeout(r, 0))
    expect(star).toHaveAttribute('aria-pressed', 'false')
  })

  it('정리 중이면 끝날 때까지 자동으로 다시 불러온다', async () => {
    let calls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        calls += 1
        const session = { ...DETAIL.session, journal_status: calls < 3 ? 'pending' : 'done' }
        return new Response(JSON.stringify({ ...DETAIL, session, notes: calls < 3 ? [] : DETAIL.notes }))
      }),
    )
    render(<JournalDetailScreen sessionId="s1" pollMs={10} />)
    expect(await screen.findByText('일지를 정리하는 중이에요. 끝나면 자동으로 보여 드려요.')).toBeInTheDocument()
    expect(await screen.findByText('쓰레기통 지도 앱')).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 100))
    expect(calls).toBe(3) // 끝나면 멈춘다
  })

  it('정리 중이면 안내와 다시 불러오기를 보인다', async () => {
    let calls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        calls += 1
        const session = { ...DETAIL.session, journal_status: calls === 1 ? 'pending' : 'done' }
        return new Response(JSON.stringify({ ...DETAIL, session, notes: calls === 1 ? [] : DETAIL.notes }))
      }),
    )
    render(<JournalDetailScreen sessionId="s1" />)
    expect(await screen.findByText('일지를 정리하는 중이에요. 끝나면 자동으로 보여 드려요.')).toBeInTheDocument()
    expect(screen.queryByText('저장한 아이디어·할 일·메모가 없어요.')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }))
    expect(await screen.findByText('쓰레기통 지도 앱')).toBeInTheDocument()
  })

  it('검색으로 알게 된 요약·메모 끝에 출처 번호를, 맨 아래에 인용 목록을 보인다', async () => {
    const cited = {
      ...DETAIL,
      summary_cites: [[1, 2], []],
      citations: [
        { n: 1, title: '쓰레기통 위치 공개', url: 'https://news.example.com/a' },
        { n: 2, title: '공공데이터 안내', url: 'https://data.example.org/b' },
      ],
      notes: DETAIL.notes.map((n) => ({ ...n, cites: n.kind === 'memo' ? [2] : [] })),
    }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(cited))))
    render(<JournalDetailScreen sessionId="s1" />)
    const summary = await screen.findByRole('list', { name: '요약' })
    expect(within(summary).getAllByRole('listitem')[0]).toHaveTextContent('등산로 쓰레기통 지도를 이야기했다.[1][2]')
    expect(within(summary).getAllByRole('listitem')[1]).toHaveTextContent(/^데이터를 찾아보기로 했다\.$/)
    expect(screen.getByRole('region', { name: '메모' })).toHaveTextContent('구청에 문의 가능[2]')
    const list = screen.getByRole('region', { name: '인용' })
    expect(within(list).getByRole('heading', { level: 4, name: '인용:' })).toBeInTheDocument()
    expect(list).toHaveTextContent('[1] 쓰레기통 위치 공개 https://news.example.com/a')
    const link = within(list).getByRole('link', { name: '쓰레기통 위치 공개' })
    expect(link).toHaveAttribute('href', 'https://news.example.com/a')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('인용이 없으면 인용 목록을 보이지 않는다', async () => {
    stub()
    render(<JournalDetailScreen sessionId="s1" />)
    await screen.findByRole('heading', { level: 3, name: '쓰레기통 지도' })
    expect(screen.queryByRole('region', { name: '인용' })).toBeNull()
  })

  it('새 형식은 결론(굵게) → 알게 된 것 → 확인할 것 → 노트 → 인용 → 태그 순서로 보인다', async () => {
    const detail = {
      ...DETAIL,
      session: {
        ...DETAIL.session,
        summary: ['설악산과 내장산이 단풍 산행 후보다.', '설악산: 단풍 절정 10월 중순~하순', '내장산: 단풍 절정 11월 초'],
      },
      summary_cites: [[1], [1], [2]],
      checks: ['올해 설악산 단풍 시기'],
      citations: [
        { n: 1, title: '설악산 단풍 시기', url: 'https://a.example/1' },
        { n: 2, title: '내장산 단풍', url: 'https://b.example/2' },
      ],
    }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(detail))))
    const { container } = render(<JournalDetailScreen sessionId="s1" />)
    const conclusion = await screen.findByLabelText('결론')
    expect(conclusion).toHaveTextContent('설악산과 내장산이 단풍 산행 후보다.[1]')
    expect(within(conclusion).getByText('설악산과 내장산이 단풍 산행 후보다.').tagName).toBe('STRONG')
    const found = screen.getByRole('region', { name: '알게 된 것' })
    expect(within(found).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      '설악산: 단풍 절정 10월 중순~하순[1]',
      '내장산: 단풍 절정 11월 초[2]',
    ])
    expect(screen.getByRole('region', { name: '확인할 것' })).toHaveTextContent('올해 설악산 단풍 시기')
    expect(screen.queryByRole('list', { name: '요약' })).toBeNull()
    expect(screen.queryByRole('button', { name: '다시 정리' })).toBeNull()
    // 태그는 인용 뒤, 전문 앞(맨 아래)
    const order = [...container.querySelectorAll('.journal-conclusion, section[aria-label], .journal-tags, details')].map(
      (el) => el.getAttribute('aria-label') ?? el.className,
    )
    expect(order).toEqual([
      '결론',
      '알게 된 것',
      '확인할 것',
      '아이디어',
      '할 일',
      '메모',
      '인용',
      'journal-tags',
      'journal-transcript',
    ])
  })

  it('예전 형식(확인할 것 없음)으로 정리된 일지는 새 형식으로 다시 정리할 수 있다', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/journal/s1/retry' && init?.method === 'POST') {
        return new Response(JSON.stringify({ ...DETAIL.session, journal_status: 'pending' }), { status: 202 })
      }
      return new Response(JSON.stringify({ ...DETAIL, checks: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<JournalDetailScreen sessionId="s1" pollMs={10} />)
    expect(await screen.findByText(/예전 형식으로 정리된 일지예요/)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: '요약' })).toBeInTheDocument() // 예전 모습 그대로
    fireEvent.click(screen.getByRole('button', { name: '다시 정리' }))
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/journal/s1/retry', expect.objectContaining({ method: 'POST' })),
    )
  })

  it('끝난 대화는 전문 아래에서 글·음성으로 이어서 하고, 다른 대화가 진행 중이면 안내한다', async () => {
    stub()
    const onContinue = vi.fn(() => 'ok' as const)
    const { unmount } = render(<JournalDetailScreen sessionId="s1" onContinue={onContinue} />)
    fireEvent.click(await screen.findByRole('button', { name: '글로 이어서' }))
    expect(onContinue).toHaveBeenLastCalledWith('s1', 'text')
    fireEvent.click(screen.getByRole('button', { name: '음성으로 이어서' }))
    expect(onContinue).toHaveBeenLastCalledWith('s1', 'voice')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    unmount()

    render(<JournalDetailScreen sessionId="s1" onContinue={() => 'busy'} />)
    fireEvent.click(await screen.findByRole('button', { name: '글로 이어서' }))
    expect(screen.getByRole('alert')).toHaveTextContent('진행 중인 대화를 끝낸 뒤 이어서 할 수 있어요.')
    cleanup()

    render(<JournalDetailScreen sessionId="s1" onContinue={() => 'voice_loading'} />)
    fireEvent.click(await screen.findByRole('button', { name: '음성으로 이어서' }))
    expect(screen.getByRole('alert')).toHaveTextContent('음성 기능을 준비하는 중이에요.')
  })

  it('진행 중인 대화에는 이어서 버튼이 없다', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ...DETAIL, session: { ...DETAIL.session, status: 'active', journal_status: null } })),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<JournalDetailScreen sessionId="s1" onContinue={() => 'ok'} />)
    await screen.findByText(/아직 진행 중인 대화예요/)
    expect(screen.queryByRole('button', { name: '글로 이어서' })).not.toBeInTheDocument()
  })

  it('맨 아래 삭제는 확인한 뒤 지우고 목록으로 돌아간다(404도 지운 것으로 본다)', async () => {
    const confirm = vi.fn(() => false)
    vi.stubGlobal('confirm', confirm)
    let status = 204
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return status === 204
          ? new Response(null, { status: 204 })
          : new Response(JSON.stringify({ error: { code: 'session_not_found', message: '없음' } }), { status })
      }
      if (url === '/api/journal/s1') return new Response(JSON.stringify(DETAIL))
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const onDeleted = vi.fn()
    const { unmount } = render(<JournalDetailScreen sessionId="s1" onDeleted={onDeleted} />)
    const button = await screen.findByRole('button', { name: '이 대화 삭제' })
    fireEvent.click(button)
    expect(confirm).toHaveBeenCalledWith('이 대화와 노트·전문을 모두 지울까요?')
    expect(fetchMock).toHaveBeenCalledTimes(1) // 취소하면 지우지 않는다

    confirm.mockReturnValue(true)
    fireEvent.click(button)
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1))
    expect(fetchMock).toHaveBeenLastCalledWith('/api/journal/s1', expect.objectContaining({ method: 'DELETE' }))
    unmount()

    status = 404
    render(<JournalDetailScreen sessionId="s1" onDeleted={onDeleted} />)
    fireEvent.click(await screen.findByRole('button', { name: '이 대화 삭제' }))
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(2))
  })

  it('지우지 못하면 알리고 머무르며, 진행 중인 대화는 이유만 보인다', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    let active = false
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return new Response(
          JSON.stringify({ error: { code: 'turn_in_progress', message: '이전 답변이 아직 끝나지 않았습니다.' } }),
          { status: 409 },
        )
      }
      const session = { ...DETAIL.session, status: active ? 'active' : 'ended' }
      if (url === '/api/journal/s1') return new Response(JSON.stringify({ ...DETAIL, session }))
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const onDeleted = vi.fn()
    const { unmount } = render(<JournalDetailScreen sessionId="s1" onDeleted={onDeleted} />)
    fireEvent.click(await screen.findByRole('button', { name: '이 대화 삭제' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('이전 답변이 아직 끝나지 않았습니다.')
    expect(screen.getByRole('button', { name: '이 대화 삭제' })).toBeEnabled()
    expect(onDeleted).not.toHaveBeenCalled()
    unmount()

    active = true
    const calls = fetchMock.mock.calls.length
    render(<JournalDetailScreen sessionId="s1" onDeleted={onDeleted} />)
    const button = await screen.findByRole('button', { name: '이 대화 삭제' })
    expect(button).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(button)
    expect(screen.getByRole('alert')).toHaveTextContent('진행 중인 대화는 끝낸 뒤 지울 수 있어요.')
    expect(fetchMock.mock.calls.length).toBe(calls + 1) // 상세 불러오기만, DELETE는 없다
  })

  it('지우는 동안 이어서 버튼을 막고, 그사이 화면을 떠났으면 응답이 와도 목록으로 옮기지 않는다', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    let release: () => void = () => {}
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'DELETE') {
          await new Promise<void>((resolve) => (release = resolve))
          return new Response(null, { status: 204 })
        }
        if (url === '/api/journal/s1') return new Response(JSON.stringify(DETAIL))
        throw new Error(`unexpected ${url}`)
      }),
    )
    const onDeleted = vi.fn()
    const { unmount } = render(<JournalDetailScreen sessionId="s1" onDeleted={onDeleted} onContinue={() => 'ok'} />)
    fireEvent.click(await screen.findByRole('button', { name: '이 대화 삭제' }))
    expect(await screen.findByRole('button', { name: '지우는 중…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '글로 이어서' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '음성으로 이어서' })).toBeDisabled()
    unmount() // 응답 전에 다른 탭으로 옮겼다
    release()
    await new Promise((r) => setTimeout(r, 20))
    expect(onDeleted).not.toHaveBeenCalled()
  })
})

