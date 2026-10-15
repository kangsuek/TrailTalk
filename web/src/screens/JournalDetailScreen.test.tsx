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
    expect(await screen.findByText('일지를 정리하는 중이에요. 잠시 뒤 다시 불러와 주세요.')).toBeInTheDocument()
    expect(screen.queryByText('저장한 아이디어·할 일·메모가 없어요.')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }))
    expect(await screen.findByText('쓰레기통 지도 앱')).toBeInTheDocument()
  })
})
