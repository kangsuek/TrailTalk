import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MAX_POLLS } from '../core/journal'
import { JournalListScreen } from './JournalListScreen'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function item(id: string, date: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    date,
    started_at: `${date}T00:00:00Z`,
    ended_at: null,
    status: 'ended',
    title: `${id} 제목`,
    summary: [`${id} 요약 첫 줄`, '둘째 줄'],
    tags: [],
    journal_status: 'done',
    counts: { idea: 2, todo: 1, memo: 0 },
    ...extra,
  }
}

function stub(...responses: (() => Response | Promise<Response>)[]) {
  const fetchMock = vi.fn(async () => (responses.length > 1 ? responses.shift()! : responses[0])())
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('JournalListScreen', () => {
  it('날짜별로 묶어 제목·요약 첫 줄·개수를 보이고, 누르면 연다', async () => {
    stub(() =>
      new Response(
        JSON.stringify([
          item('a', '2026-10-15'),
          item('b', '2026-10-15', { title: null, journal_status: 'pending', counts: { idea: 0, todo: 0, memo: 0 } }),
          item('c', '2026-10-13', { journal_status: null, status: 'active' }),
        ]),
      ),
    )
    const onOpen = vi.fn()
    render(<JournalListScreen onOpen={onOpen} />)
    expect(screen.getByText('불러오는 중…')).toBeInTheDocument()
    const today = await screen.findByRole('region', { name: '10월 15일 (목)' })
    expect(within(today).getAllByRole('button', { name: /^삭제:/ })).toHaveLength(2)
    expect(within(today).getByText('a 요약 첫 줄')).toBeInTheDocument()
    expect(within(today).getByText('아이디어 2 · 할 일 1')).toBeInTheDocument()
    expect(within(today).getByText('정리 중인 대화')).toBeInTheDocument()
    expect(within(today).getByText('정리 중')).toBeInTheDocument()
    const older = screen.getByRole('region', { name: '10월 13일 (화)' })
    expect(within(older).getByText(/대화 중/)).toBeInTheDocument()

    fireEvent.click(within(today).getByRole('button', { name: /^a 제목/ }))
    expect(onOpen).toHaveBeenCalledWith('a')
  })

  it('정리 중인 일지가 있으면 끝날 때까지 다시 불러온다', async () => {
    let calls = 0
    const fetchMock = stub(() => {
      calls += 1
      const pending = calls < 3
      return new Response(
        JSON.stringify([item('a', '2026-10-15', pending ? { title: null, journal_status: 'pending' } : {})]),
      )
    })
    render(<JournalListScreen pollMs={10} />)
    expect(await screen.findByText('정리 중인 대화')).toBeInTheDocument()
    expect(await screen.findByText('a 제목')).toBeInTheDocument() // 세 번째 응답에서 정리 끝
    await new Promise((r) => setTimeout(r, 100))
    expect(fetchMock).toHaveBeenCalledTimes(3) // 끝났으면 멈춘다
  })

  it('다시 불러오기가 한 번 실패해도 계속 확인한다', async () => {
    let calls = 0
    stub(() => {
      calls += 1
      if (calls === 2) return Promise.reject(new TypeError('순간 끊김'))
      const pending = calls < 3
      return new Response(
        JSON.stringify([item('a', '2026-10-15', pending ? { title: null, journal_status: 'pending' } : {})]),
      )
    })
    render(<JournalListScreen pollMs={10} />)
    expect(await screen.findByText('정리 중인 대화')).toBeInTheDocument()
    expect(await screen.findByText('a 제목')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument() // 조용히 다시 본다
  })

  it('계속 정리 중이어도 정해진 횟수까지만 다시 불러온다', async () => {
    const fetchMock = stub(() => new Response(JSON.stringify([item('a', '2026-10-15', { journal_status: 'pending' })])))
    render(<JournalListScreen pollMs={1} />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1 + MAX_POLLS))
    await new Promise((r) => setTimeout(r, 100))
    expect(fetchMock).toHaveBeenCalledTimes(1 + MAX_POLLS)
  })

  it('일지가 없으면 안내를 보인다', async () => {
    stub(() => new Response('[]'))
    render(<JournalListScreen />)
    expect(await screen.findByText('아직 일지가 없어요. 대화를 나누면 여기에 정리돼요.')).toBeInTheDocument()
  })

  it('불러오지 못하면 오류와 다시 불러오기를 보인다', async () => {
    const fetchMock = stub(
      () => Promise.reject(new TypeError('down')),
      () => new Response(JSON.stringify([item('a', '2026-10-15')])),
    )
    render(<JournalListScreen />)
    expect(await screen.findByRole('alert')).toHaveTextContent('서버에 연결할 수 없어요.')
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }))
    expect(await screen.findByText('a 제목')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('제목을 누르면 그 자리에서 고치고, 포커스가 떠나면 저장한다(Esc·빈 값·실패 포함)', async () => {
    const fetchMock = stub(
      () => new Response(JSON.stringify([item('a', '2026-10-15')])),
      () =>
        new Response(JSON.stringify({ error: { code: 'validation_error', message: '1~200자로 입력하세요' } }), {
          status: 422,
        }),
      () => new Response(JSON.stringify(item('a', '2026-10-15', { title: '새 제목' }))),
    )
    const onOpen = vi.fn()
    render(<JournalListScreen onOpen={onOpen} />)
    fireEvent.click(await screen.findByRole('button', { name: '제목 수정: a 제목' }))
    expect(onOpen).not.toHaveBeenCalled() // 제목을 누르면 상세가 아니라 편집이 열린다
    let input = screen.getByRole('textbox', { name: '대화 제목' })
    expect(input).toHaveValue('a 제목')
    expect(input).toHaveFocus()
    fireEvent.change(input, { target: { value: '버릴 제목' } })
    fireEvent.keyDown(input, { key: 'Escape' }) // 취소하면 닫히고 보내지 않는다
    expect(screen.queryByRole('textbox', { name: '대화 제목' })).not.toBeInTheDocument()
    expect(screen.getByText('a 제목')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '제목 수정: a 제목' }))
    input = screen.getByRole('textbox', { name: '대화 제목' })
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.blur(input) // 빈 값이면 저장하지 않는다
    expect(fetchMock).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: '제목 수정: a 제목' }))
    input = screen.getByRole('textbox', { name: '대화 제목' })
    fireEvent.change(input, { target: { value: '  새 제목 ' } })
    fireEvent.blur(input)
    expect(await screen.findByRole('alert')).toHaveTextContent('1~200자로 입력하세요')
    expect(screen.getByText('a 제목')).toBeInTheDocument() // 실패하면 되돌린다

    fireEvent.click(screen.getByRole('button', { name: '제목 수정: a 제목' }))
    input = screen.getByRole('textbox', { name: '대화 제목' })
    fireEvent.change(input, { target: { value: '새 제목' } })
    fireEvent.keyDown(input, { key: 'Enter' }) // Enter는 포커스를 빼서 저장한다
    fireEvent.blur(input) // jsdom은 blur()로 blur 이벤트가 오지 않을 수 있다(두 번 와도 한 번만 보낸다)
    expect(await screen.findByRole('button', { name: '제목 수정: 새 제목' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/journal/a',
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ title: '새 제목' }) }),
    )
    fireEvent.click(screen.getByRole('button', { name: /^새 제목 a 요약 첫 줄/ }))
    expect(onOpen).toHaveBeenCalledWith('a')
  })

  it('쓰레기통은 확인한 뒤에만 지우고, 지운 항목은 목록에서 빠진다', async () => {
    const confirm = vi.fn(() => false)
    vi.stubGlobal('confirm', confirm)
    const fetchMock = stub(
      () => new Response(JSON.stringify([item('a', '2026-10-15'), item('b', '2026-10-14')])),
      () => new Response(null, { status: 204 }),
    )
    render(<JournalListScreen />)
    fireEvent.click(await screen.findByRole('button', { name: '삭제: b 제목' }))
    expect(confirm).toHaveBeenCalledWith('이 대화와 노트·전문을 모두 지울까요?')
    expect(screen.getByText('b 제목')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: '삭제: b 제목' }))
    await waitFor(() => expect(screen.queryByText('b 제목')).not.toBeInTheDocument())
    expect(screen.queryByRole('region', { name: '10월 14일 (수)' })).not.toBeInTheDocument() // 빈 날짜 묶음도 사라진다
    expect(screen.getByText('a 제목')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/journal/b', expect.objectContaining({ method: 'DELETE' }))
  })

  it('진행 중인 대화는 지울 수 없고, 삭제 실패는 알린다', async () => {
    stub(
      () =>
        new Response(
          JSON.stringify([item('a', '2026-10-15', { status: 'active' }), item('b', '2026-10-15', { status: 'paused' })]),
        ),
      () => Promise.reject(new TypeError('끊김')),
    )
    render(<JournalListScreen />)
    const confirm = vi.fn(() => true)
    vi.stubGlobal('confirm', confirm)
    const active = await screen.findByRole('button', { name: '삭제: a 제목' })
    expect(active).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(active) // 터치 화면에는 툴팁이 없으니 누르면 이유를 글로 보인다
    expect(screen.getByRole('alert')).toHaveTextContent('진행 중인 대화는 끝낸 뒤 지울 수 있어요.')
    expect(confirm).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '삭제: b 제목' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/연결|서버|네트워크/)
    expect(screen.getByText('b 제목')).toBeInTheDocument()
  })

  it('제목을 고치기 전에 떠난 다시 불러오기 응답은 고친 제목을 되돌리지 않는다', async () => {
    let lists = 0
    let releaseStale: () => void = () => {}
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'PATCH') return new Response(JSON.stringify(item('a', '2026-10-15', { title: '새 제목' })))
      lists += 1
      if (lists === 2) {
        // 정리 중이라 다시 불러오는 응답이 제목 수정보다 늦게 도착한다(옛 제목)
        await new Promise<void>((resolve) => (releaseStale = resolve))
        return new Response(JSON.stringify([item('a', '2026-10-15', { journal_status: 'pending' })]))
      }
      return new Response(
        JSON.stringify([item('a', '2026-10-15', lists === 1 ? { journal_status: 'pending' } : { title: '새 제목' })]),
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<JournalListScreen pollMs={10} />)
    await waitFor(() => expect(lists).toBe(2))
    fireEvent.click(screen.getByRole('button', { name: '제목 수정: a 제목' }))
    const input = screen.getByRole('textbox', { name: '대화 제목' })
    fireEvent.change(input, { target: { value: '새 제목' } })
    fireEvent.blur(input)
    expect(await screen.findByRole('button', { name: '제목 수정: 새 제목' })).toBeInTheDocument()
    releaseStale()
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.getByRole('button', { name: '제목 수정: 새 제목' })).toBeInTheDocument()
  })

  it('선택 모드: 카드를 눌러 고르고(상세는 열지 않음), 전체 선택은 진행 중인 대화를 뺀다', async () => {
    stub(() =>
      new Response(
        JSON.stringify([
          item('a', '2026-10-15'),
          item('b', '2026-10-15'),
          item('c', '2026-10-14', { status: 'active' }),
        ]),
      ),
    )
    const onOpen = vi.fn()
    render(<JournalListScreen onOpen={onOpen} />)
    fireEvent.click(await screen.findByRole('button', { name: '선택' }))
    expect(screen.queryByRole('button', { name: /^삭제:/ })).not.toBeInTheDocument() // 쓰레기통은 숨긴다
    expect(screen.queryByRole('button', { name: /^제목 수정:/ })).not.toBeInTheDocument()
    expect(screen.getByText('0개 선택')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '삭제' })).toBeDisabled()

    fireEvent.click(screen.getByText('a 요약 첫 줄')) // 카드 아무 데나 눌러도 고른다
    expect(screen.getByRole('checkbox', { name: '선택: a 제목' })).toBeChecked()
    expect(onOpen).not.toHaveBeenCalled()
    expect(screen.getByText('1개 선택')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '삭제 (1)' })).toBeEnabled()

    const active = screen.getByRole('checkbox', { name: '선택: c 제목' })
    expect(active).toBeDisabled()
    fireEvent.click(screen.getByText('c 제목'))
    expect(screen.getByRole('alert')).toHaveTextContent('진행 중인 대화는 끝낸 뒤 지울 수 있어요.')

    fireEvent.click(screen.getByRole('button', { name: '전체 선택' }))
    expect(screen.getByText('2개 선택')).toBeInTheDocument()
    expect(active).not.toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: '전체 해제' }))
    expect(screen.getByText('0개 선택')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '취소' }))
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^a 제목/ }))
    expect(onOpen).toHaveBeenCalledWith('a')
  })

  it('선택한 일지를 확인한 뒤 차례로 지우고, 다 지우면 선택 모드를 닫는다(404는 지운 것으로 본다)', async () => {
    const confirm = vi.fn(() => false)
    vi.stubGlobal('confirm', confirm)
    const order: string[] = []
    let inFlight = 0
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method !== 'DELETE') {
        return new Response(
          JSON.stringify([item('a', '2026-10-15'), item('b', '2026-10-15'), item('c', '2026-10-14')]),
        )
      }
      inFlight += 1
      expect(inFlight).toBe(1) // 동시에 보내지 않는다
      order.push(url)
      await new Promise((r) => setTimeout(r, 5))
      inFlight -= 1
      if (url.endsWith('/c')) {
        return new Response(JSON.stringify({ error: { code: 'session_not_found', message: '없음' } }), { status: 404 })
      }
      return new Response(null, { status: 204 })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<JournalListScreen />)
    fireEvent.click(await screen.findByRole('button', { name: '선택' }))
    fireEvent.click(screen.getByRole('checkbox', { name: '선택: a 제목' }))
    fireEvent.click(screen.getByRole('checkbox', { name: '선택: c 제목' }))

    fireEvent.click(screen.getByRole('button', { name: '삭제 (2)' }))
    expect(confirm).toHaveBeenCalledWith('선택한 2개 대화와 노트·전문을 모두 지울까요?')
    expect(order).toEqual([])

    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: '삭제 (2)' }))
    expect(await screen.findByText(/지우는 중… 1\/2/)).toBeInTheDocument()
    expect(await screen.findByText(/지우는 중… 2\/2/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('checkbox')).not.toBeInTheDocument())
    expect(order).toEqual(['/api/journal/a', '/api/journal/c'])
    expect(screen.queryByText('a 제목')).not.toBeInTheDocument()
    expect(screen.queryByText('c 제목')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '10월 14일 (수)' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '제목 수정: b 제목' })).toBeInTheDocument()
  })

  it('일부만 지우지 못하면 그 항목을 선택한 채 남기고 알린다', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true))
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method !== 'DELETE') {
        return new Response(JSON.stringify([item('a', '2026-10-15'), item('b', '2026-10-15', { status: 'paused' })]))
      }
      if (url.endsWith('/b')) {
        return new Response(
          JSON.stringify({ error: { code: 'turn_in_progress', message: '답변을 만드는 중이에요.' } }),
          { status: 409 },
        )
      }
      return new Response(null, { status: 204 })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<JournalListScreen />)
    fireEvent.click(await screen.findByRole('button', { name: '선택' }))
    fireEvent.click(screen.getByRole('button', { name: '전체 선택' }))
    fireEvent.click(screen.getByRole('button', { name: '삭제 (2)' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('1개는 지우지 못했어요.')
    expect(screen.queryByText('a 제목')).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '선택: b 제목' })).toBeChecked()
    expect(screen.getByRole('button', { name: '삭제 (1)' })).toBeEnabled()
  })
})
