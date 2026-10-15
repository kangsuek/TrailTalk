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
    expect(within(today).getAllByRole('button')).toHaveLength(2)
    expect(within(today).getByText('a 요약 첫 줄')).toBeInTheDocument()
    expect(within(today).getByText('아이디어 2 · 할 일 1')).toBeInTheDocument()
    expect(within(today).getByText('정리 중인 대화')).toBeInTheDocument()
    expect(within(today).getByText('정리 중')).toBeInTheDocument()
    const older = screen.getByRole('region', { name: '10월 13일 (화)' })
    expect(within(older).getByText(/대화 중/)).toBeInTheDocument()

    fireEvent.click(within(today).getByRole('button', { name: /a 제목/ }))
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
})
