import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { JournalDetailScreen } from './JournalDetailScreen'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const REPORT = {
  conclusion: '**등산로 쓰레기통 지도** 앱을 **다음 달**부터 만들기로 했다',
  conclusion_cites: [1],
  key_points: [{ text: '**공공데이터** 위치 자료가 있다', cites: [1, 2] }],
  details: [{ text: '구청에 문의할 수 있다', cites: [] }],
  citations: [
    { n: 1, title: '쓰레기통 위치 공개', url: 'https://news.example.com/a' },
    { n: 2, title: 'data.example.org', url: 'https://data.example.org/b' },
  ],
}

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
  report: null as null | typeof REPORT, // 예전 형식(요약 줄만)
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
    const terms = screen.getByLabelText('검색어')
    expect(terms).toHaveTextContent('#등산, #지도')
    expect(within(terms).getByRole('link', { name: '#등산' })).toHaveAttribute(
      'href',
      'https://www.google.com/search?q=%EB%93%B1%EC%82%B0',
    )
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
      const report = phase === 'before' ? null : REPORT // 정리가 끝나면 새 형식 보고서가 온다
      return new Response(JSON.stringify({ ...DETAIL, report, session: { ...DETAIL.session, journal_status } }))
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

  it('새 형식 보고서를 결론·핵심 내용·세부 내용·인용·검색어 순으로 보인다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ...DETAIL, report: REPORT }))))
    render(<JournalDetailScreen sessionId="s1" />)
    await screen.findByRole('heading', { level: 3, name: '쓰레기통 지도' })
    expect(screen.queryByRole('list', { name: '요약' })).toBeNull() // 예전 요약 줄 대신 보고서
    expect(screen.queryByRole('button', { name: '다시 정리' })).toBeNull()
    const conclusion = screen.getByText((_, el) => el?.classList.contains('journal-conclusion') ?? false)
    expect(conclusion).toHaveTextContent('등산로 쓰레기통 지도 앱을 다음 달부터 만들기로 했다[1]')
    expect(within(conclusion).getByText('등산로 쓰레기통 지도').tagName).toBe('STRONG')
    const key = screen.getByRole('region', { name: '핵심 내용' })
    expect(within(key).getByRole('heading', { level: 4, name: '핵심 내용' })).toBeInTheDocument()
    expect(key).toHaveTextContent('공공데이터 위치 자료가 있다[1][2]')
    expect(screen.getByRole('region', { name: '세부 내용' })).toHaveTextContent('구청에 문의할 수 있다')
    const cited = screen.getByRole('region', { name: '인용' })
    expect(cited).toHaveTextContent('인용:')
    const link = within(cited).getByRole('link', { name: '쓰레기통 위치 공개' })
    expect(link).toHaveAttribute('href', 'https://news.example.com/a')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(cited).toHaveTextContent('[1] 쓰레기통 위치 공개 https://news.example.com/a')
    expect(screen.getByLabelText('검색어')).toHaveTextContent('#등산, #지도')
  })

  it('예전 형식으로 정리된 일지는 새 형식으로 다시 정리할 수 있다', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/journal/s1/retry' && init?.method === 'POST') {
        return new Response(JSON.stringify({ ...DETAIL.session, journal_status: 'pending' }), { status: 202 })
      }
      return new Response(JSON.stringify(DETAIL))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<JournalDetailScreen sessionId="s1" pollMs={10} />)
    expect(await screen.findByText(/예전 형식으로 정리된 일지예요/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '다시 정리' }))
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/journal/s1/retry', expect.objectContaining({ method: 'POST' })),
    )
  })
})
