import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function stubFetch(response: () => Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(response))
}

function stubHealth(ok: boolean) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      url.startsWith('/api/journal')
        ? new Response('[]')
        : new Response(JSON.stringify({ status: ok ? 'ok' : 'down' })),
    ),
  )
}

const JOURNAL_ITEM = {
  id: 's1',
  date: '2026-10-15',
  started_at: '2026-10-15T00:00:00Z',
  ended_at: '2026-10-15T00:10:00Z',
  status: 'ended',
  title: '산책 앱 아이디어',
  summary: ['산책 앱을 이야기했다.'],
  tags: [],
  journal_status: 'done',
  counts: { idea: 0, todo: 0, memo: 0 },
}

describe('App', () => {
  it('탭을 눌러 4개 화면을 전환한다', async () => {
    stubHealth(true)
    render(<App />)
    for (const name of ['대화', '일지 목록', '일지 상세', '설정']) {
      fireEvent.click(screen.getByRole('tab', { name }))
      expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument()
    }
    expect(await screen.findByText('서버 연결됨')).toBeInTheDocument()
  })

  it('탭은 WAI-ARIA 탭 패턴을 따른다(패널 연결, 화살표·Home·End 이동)', () => {
    stubHealth(true)
    render(<App />)
    const tabs = screen.getAllByRole('tab')
    expect(screen.getByRole('tablist', { name: '화면' })).toBeInTheDocument()
    expect(tabs.map((t) => t.tabIndex)).toEqual([0, -1, -1, -1])
    const panel = screen.getByRole('tabpanel', { name: '대화' })
    expect(tabs[0]).toHaveAttribute('aria-controls', panel.id)

    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
    expect(tabs[1]).toHaveFocus()
    expect(screen.getByRole('heading', { level: 2, name: '일지 목록' })).toBeInTheDocument()
    fireEvent.keyDown(tabs[1], { key: 'End' })
    expect(tabs[3]).toHaveFocus()
    fireEvent.keyDown(tabs[3], { key: 'ArrowRight' })
    expect(tabs[0]).toHaveFocus() // 끝에서 처음으로 돈다
    fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' })
    expect(tabs[3]).toHaveFocus()
    fireEvent.keyDown(tabs[3], { key: 'Home' })
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('일지 목록에서 항목을 누르면 일지 상세 탭에서 연다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url === '/api/journal') return new Response(JSON.stringify([JOURNAL_ITEM]))
        if (url === '/api/journal/s1') {
          return new Response(
            JSON.stringify({ session: JOURNAL_ITEM, persona_name: '도우미', notes: [], turns: [] }),
          )
        }
        return new Response(JSON.stringify({ status: 'ok' }))
      }),
    )
    render(<App />)
    fireEvent.click(screen.getByRole('tab', { name: '일지 목록' }))
    fireEvent.click(await screen.findByRole('button', { name: /산책 앱 아이디어/ }))
    expect(screen.getByRole('tab', { name: '일지 상세' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByRole('heading', { level: 3, name: '산책 앱 아이디어' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '목록으로' }))
    expect(screen.getByRole('tab', { name: '일지 목록' })).toHaveAttribute('aria-selected', 'true')
  })

  it('탭을 옮겼다 돌아와도 대화가 남아 있다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url === '/api/sessions'
          ? new Response(
              JSON.stringify({
                session: { id: 's1', mode: 'text', status: 'active', started_at: '', ended_at: null },
                greeting: { turn_id: 'g1', text: '반가워요!' },
                persona: { id: 'p1', name: '도우미' },
              }),
              { status: 201 },
            )
          : new Response(JSON.stringify({ status: 'ok' })),
      ),
    )
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: '대화 시작' }))
    expect(await screen.findByText('반가워요!')).toBeVisible()
    fireEvent.click(screen.getByRole('tab', { name: '설정' }))
    expect(screen.getByText('반가워요!')).not.toBeVisible()
    fireEvent.click(screen.getByRole('tab', { name: '대화' }))
    expect(screen.getByText('반가워요!')).toBeVisible()
  })

  it('서버 상태를 30초마다 다시 확인한다(꺼졌다 켜져도 반영)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      let up = false
      stubFetch(async () => (up ? new Response(JSON.stringify({ status: 'ok' })) : Promise.reject(new TypeError('down'))))
      render(<App />)
      expect(await screen.findByText('서버 연결 안 됨')).toBeInTheDocument()
      up = true
      await vi.advanceTimersByTimeAsync(30_000)
      expect(await screen.findByText('서버 연결됨')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('서버 헬스체크 결과를 표시한다', async () => {
    stubHealth(true)
    render(<App />)
    expect(await screen.findByText('서버 연결됨')).toBeInTheDocument()
  })

  it.each([
    ['네트워크 오류', () => Promise.reject(new TypeError('network'))],
    ['HTTP 500', async () => new Response('', { status: 500 })],
    ['status가 ok가 아님', async () => new Response(JSON.stringify({ status: 'down' }))],
  ])('서버 상태가 비정상이면 오류를 표시한다: %s', async (_case, response) => {
    stubFetch(response)
    render(<App />)
    expect(await screen.findByText('서버 연결 안 됨')).toBeInTheDocument()
  })
})
