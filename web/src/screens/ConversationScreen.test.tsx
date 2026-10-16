import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { StreamEvent } from '../core/conversation'
import { ConversationScreen } from './ConversationScreen'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const STARTED = {
  session: { id: 's1', mode: 'text', status: 'active', started_at: '2026-10-14T00:00:00Z', ended_at: null },
  greeting: { turn_id: 'g1', text: '안녕하세요, 오늘 어떤 이야기를 할까요?' },
  persona: { id: 'p1', name: '도우미' },
}

function sseResponse(events: StreamEvent[]): Response {
  const body = events.map((e) => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join('')
  return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
}

const TURN: StreamEvent[] = [
  { type: 'turn', turn_id: 'a1' },
  { type: 'tool', phase: 'start', tool_use_id: 'u1', name: 'save_note', input: null, summary: null, is_error: false, notice: null },
  {
    type: 'tool',
    phase: 'call',
    tool_use_id: 'u1',
    name: 'save_note',
    input: { kind: 'idea', content: '쓰레기통 지도' },
    summary: null,
    is_error: false,
    notice: null,
  },
  { type: 'tool', phase: 'end', tool_use_id: 'u1', name: 'save_note', input: null, summary: { result: 'ok' }, is_error: false, notice: null },
  { type: 'sentence', index: 0, text: '저장했어요!', audio: null },
  { type: 'sentence', index: 1, text: '누가 쓰면 좋을까요?', audio: null },
  { type: 'done', turn_id: 'a1', text: '저장했어요! 누가 쓰면 좋을까요?', interrupted: false, session_status: 'active' },
]

const CLOSED = {
  session: { ...STARTED.session, status: 'ended', ended_at: '2026-10-14T00:10:00Z' },
  closing: '오늘 아이디어 1개 저장했어요!',
  saved: { idea: 1, todo: 0, memo: 0 },
  journal_status: 'done',
}

function stubServer(turn: () => Response = () => sseResponse(TURN)) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === '/api/sessions') return new Response(JSON.stringify(STARTED), { status: 201 })
    if (url === '/api/sessions/prepare') return new Response(null, { status: 204 })
    if (url.endsWith('/turns')) return turn()
    if (url.endsWith('/end')) return new Response(JSON.stringify(CLOSED))
    throw new Error(`unexpected ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function calls(fetchMock: ReturnType<typeof vi.fn>, suffix: string): number {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(suffix)).length
}

const turnCalls = (fetchMock: ReturnType<typeof vi.fn>) => calls(fetchMock, '/turns')

async function startConversation() {
  render(<ConversationScreen />)
  fireEvent.click(screen.getByRole('button', { name: '글로 대화' }))
  await screen.findByText('안녕하세요, 오늘 어떤 이야기를 할까요?')
}

describe('ConversationScreen', () => {
  it('대화를 시작하고, 보낸 메시지의 답변을 문장과 도구 알림으로 보여 준다', async () => {
    stubServer()
    await startConversation()
    const log = screen.getByRole('log', { name: '대화 내용' })
    expect(within(log).getByText('도우미')).toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox', { name: '메시지' }), {
      target: { value: '쓰레기통 지도 저장해줘' },
    })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))

    expect(await within(log).findByText('아이디어 저장: 쓰레기통 지도')).toBeInTheDocument()
    expect(within(log).getByText('쓰레기통 지도 저장해줘')).toBeInTheDocument()
    expect(within(log).getByText(/저장했어요!/)).toBeInTheDocument()
    expect(within(log).getByText(/누가 쓰면 좋을까요\?/)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '메시지' })).toHaveValue('')
  })

  it('한글 조합 중 Enter는 보내지 않고, 조합이 끝난 Enter는 보낸다', async () => {
    const fetchMock = stubServer()
    await startConversation()
    const input = screen.getByRole('textbox', { name: '메시지' })
    fireEvent.change(input, { target: { value: '안녕' } })
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
    expect(turnCalls(fetchMock)).toBe(0)
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
    expect(turnCalls(fetchMock)).toBe(0)
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(turnCalls(fetchMock)).toBe(1)
    await screen.findByText(/누가 쓰면 좋을까요\?/)
  })

  it('Safari처럼 keyCode 229로 오는 조합 확정 Enter도 보내지 않는다', async () => {
    const fetchMock = stubServer()
    await startConversation()
    const input = screen.getByRole('textbox', { name: '메시지' })
    fireEvent.change(input, { target: { value: '안녕' } })
    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 })
    expect(turnCalls(fetchMock)).toBe(0)
  })

  it('서버가 받기 전에 실패하면 쓴 글을 입력창에 되살린다', async () => {
    stubServer(
      () =>
        new Response(
          JSON.stringify({ error: { code: 'turn_in_progress', message: '이전 답변이 아직 끝나지 않았습니다.' } }),
          { status: 409 },
        ),
    )
    await startConversation()
    const input = screen.getByRole('textbox', { name: '메시지' })
    fireEvent.change(input, { target: { value: '다시 보낼 글' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('이전 답변이 아직 끝나지 않았습니다.')
    expect(input).toHaveValue('다시 보낼 글')
  })

  it('턴 오류를 알림으로 보여 주고 다시 보낼 수 있다', async () => {
    stubServer(() => sseResponse([{ type: 'turn', turn_id: 'a1' }, { type: 'error', code: 'llm_error', message: '답변을 만들지 못했습니다.' }]))
    await startConversation()
    fireEvent.change(screen.getByRole('textbox', { name: '메시지' }), { target: { value: '안녕' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('답변을 만들지 못했습니다.')
    fireEvent.change(screen.getByRole('textbox', { name: '메시지' }), { target: { value: '다시' } })
    expect(screen.getByRole('button', { name: '보내기' })).toBeEnabled()
  })

  it('끝내기 응답 때 일지 정리가 남았으면 정리 중 안내를 보인다', async () => {
    const fetchMock = stubServer()
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith('/end')) return new Response(JSON.stringify({ ...CLOSED, journal_status: 'pending' }))
      if (url === '/api/sessions') return new Response(JSON.stringify(STARTED), { status: 201 })
      return new Response(null, { status: 204 })
    })
    await startConversation()
    fireEvent.click(screen.getByRole('button', { name: '대화 끝내기' }))
    await screen.findByText('대화가 끝났어요.')
    expect(screen.getByText('일지는 아직 정리 중이에요. 잠시 뒤 일지에서 볼 수 있어요.')).toBeInTheDocument()
  })

  it('일지 정리가 끝났으면 정리 중 안내를 보이지 않는다', async () => {
    stubServer()
    await startConversation()
    fireEvent.click(screen.getByRole('button', { name: '대화 끝내기' }))
    await screen.findByText('대화가 끝났어요.')
    expect(screen.queryByText(/일지는 아직 정리 중이에요/)).toBeNull()
  })

  it('시작 전과 대화가 끝난 뒤에 다음 대화를 미리 준비시킨다', async () => {
    const fetchMock = stubServer()
    await startConversation()
    expect(calls(fetchMock, '/prepare')).toBe(1) // 화면이 열릴 때
    fireEvent.click(screen.getByRole('button', { name: '대화 끝내기' }))
    await screen.findByText('대화가 끝났어요.')
    await waitFor(() => expect(calls(fetchMock, '/prepare')).toBe(2)) // 끝난 뒤
  })

  it('대화 탭이 숨겨져 있으면 준비하지 않고, 열려 있는 동안 주기적으로 다시 알린다', async () => {
    vi.useFakeTimers()
    try {
      const fetchMock = stubServer()
      const { rerender } = render(<ConversationScreen visible={false} />)
      expect(calls(fetchMock, '/prepare')).toBe(0)
      rerender(<ConversationScreen visible />)
      expect(calls(fetchMock, '/prepare')).toBe(1)
      vi.advanceTimersByTime(4 * 60 * 1000)
      expect(calls(fetchMock, '/prepare')).toBe(2)
      rerender(<ConversationScreen visible={false} />)
      vi.advanceTimersByTime(4 * 60 * 1000)
      expect(calls(fetchMock, '/prepare')).toBe(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('미리 준비 요청이 실패해도 대화는 시작된다', async () => {
    const fetchMock = stubServer()
    fetchMock.mockImplementationOnce(async () => Promise.reject(new TypeError('network')))
    await startConversation()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('서버가 받기 전에 실패한 메시지를 다시 보내도 말풍선이 하나뿐이다', async () => {
    let first = true
    stubServer(() => {
      if (first) {
        first = false
        return new Response(JSON.stringify({ error: { code: 'turn_in_progress', message: '이전 답변이 아직 끝나지 않았습니다.' } }), { status: 409 })
      }
      return sseResponse(TURN)
    })
    await startConversation()
    const input = screen.getByRole('textbox', { name: '메시지' })
    fireEvent.change(input, { target: { value: '안녕' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    await screen.findByRole('alert')
    expect(input).toHaveValue('안녕')
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    await screen.findByText(/누가 쓰면 좋을까요\?/)
    const log = screen.getByRole('log', { name: '대화 내용' })
    expect(within(log).getAllByText('안녕')).toHaveLength(1)
  })

  it('턴 시작 전에 SSE 오류가 오면 말풍선을 빼고 쓴 글을 되살린다', async () => {
    stubServer(() => sseResponse([{ type: 'error', code: 'internal_error', message: '서버 내부 오류가 발생했습니다.' }]))
    await startConversation()
    const input = screen.getByRole('textbox', { name: '메시지' })
    fireEvent.change(input, { target: { value: '저장 안 된 글' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('서버 내부 오류가 발생했습니다.')
    expect(input).toHaveValue('저장 안 된 글')
    const log = screen.getByRole('log', { name: '대화 내용' })
    expect(within(log).queryByText('저장 안 된 글')).not.toBeInTheDocument()
  })

  it('서버에서 이미 끝난 세션이면 새 대화 시작으로 넘어간다', async () => {
    stubServer(() => new Response(JSON.stringify({ error: { code: 'session_ended', message: '이미 끝난 대화입니다.' } }), { status: 409 }))
    await startConversation()
    fireEvent.change(screen.getByRole('textbox', { name: '메시지' }), { target: { value: '안녕' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    expect(await screen.findByRole('button', { name: '글로 새 대화' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '메시지' })).not.toBeInTheDocument()
  })

  it('답변 없이 오류로 끝난 말풍선에는 안내 문구를 보여 준다', async () => {
    stubServer(() => sseResponse([{ type: 'turn', turn_id: 'a1' }, { type: 'error', code: 'llm_error', message: '답변을 만들지 못했습니다.' }]))
    await startConversation()
    fireEvent.change(screen.getByRole('textbox', { name: '메시지' }), { target: { value: '안녕' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    expect(await screen.findByText('답변을 받지 못했어요.')).toBeInTheDocument()
  })

  it('문장도 알림도 없이 끝난 답(쉬기·끝내기 도구만 쓴 경우)은 빈 말풍선을 그리지 않는다', async () => {
    stubServer(() =>
      sseResponse([
        { type: 'turn', turn_id: 'a1' },
        { type: 'done', turn_id: 'a1', text: '', interrupted: false, session_status: 'paused' },
      ]),
    )
    await startConversation()
    fireEvent.change(screen.getByRole('textbox', { name: '메시지' }), { target: { value: '쉬자' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    await screen.findByText('쉬는 중이에요. 말을 걸면 다시 이어 가요. 30분 동안 말이 없으면 대화를 마쳐요.')
    const log = screen.getByRole('log', { name: '대화 내용' })
    expect(within(log).getAllByText('도우미')).toHaveLength(1) // 인사말 말풍선만
  })

  it('끝내기 도구로 대화가 끝나면 끝내기를 불러 마무리 멘트를 받는다', async () => {
    const fetchMock = stubServer(() =>
      sseResponse([
        { type: 'turn', turn_id: 'a1' },
        { type: 'sentence', index: 0, text: '오늘 즐거웠어요!', audio: null },
        { type: 'done', turn_id: 'a1', text: '오늘 즐거웠어요!', interrupted: false, session_status: 'ended' },
      ]),
    )
    await startConversation()
    fireEvent.change(screen.getByRole('textbox', { name: '메시지' }), { target: { value: '오늘은 여기까지' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    const log = screen.getByRole('log', { name: '대화 내용' })
    expect(await within(log).findByText('오늘 아이디어 1개 저장했어요!')).toBeInTheDocument()
    expect(calls(fetchMock, '/end')).toBe(1)
    expect(screen.getByText('대화가 끝났어요.')).toBeInTheDocument()
  })

  it('끝내기 도구 뒤 턴이 session_ended 오류로 끝나도 마무리 멘트를 받는다', async () => {
    const fetchMock = stubServer(() =>
      sseResponse([
        { type: 'turn', turn_id: 'a1' },
        { type: 'error', code: 'session_ended', message: '대화를 마쳤어요.' },
      ]),
    )
    await startConversation()
    fireEvent.change(screen.getByRole('textbox', { name: '메시지' }), { target: { value: '그만하자' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    const log = screen.getByRole('log', { name: '대화 내용' })
    expect(await within(log).findByText('오늘 아이디어 1개 저장했어요!')).toBeInTheDocument()
    expect(calls(fetchMock, '/end')).toBe(1)
  })

  it('터치 화면에서는 Enter가 보내지 않는다(줄바꿈)', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query === '(pointer: coarse)' }))
    const fetchMock = stubServer()
    await startConversation()
    const input = screen.getByRole('textbox', { name: '메시지' })
    fireEvent.change(input, { target: { value: '안녕' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(turnCalls(fetchMock)).toBe(0)
  })

  it('대화가 시작되면 입력창에 포커스를 둔다', async () => {
    stubServer()
    await startConversation()
    await waitFor(() => expect(screen.getByRole('textbox', { name: '메시지' })).toHaveFocus())
  })

  it('브라우저 탭이 백그라운드면 미리 준비를 보내지 않는다', async () => {
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
    try {
      const fetchMock = stubServer()
      render(<ConversationScreen />)
      expect(calls(fetchMock, '/prepare')).toBe(0)
      visibility.mockReturnValue('visible')
      fireEvent(document, new Event('visibilitychange'))
      await waitFor(() => expect(calls(fetchMock, '/prepare')).toBe(1))
    } finally {
      visibility.mockRestore()
    }
  })

  it('대화를 끝내면 마무리 멘트를 보이고 입력창이 사라지며 새 대화를 시작할 수 있다', async () => {
    let release: () => void = () => {}
    const fetchMock = stubServer()
    const base = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url: string) => {
      // 서버가 일지를 정리하는 동안(끝내기 응답 전) 정리 중 안내를 보인다
      if (url.endsWith('/end')) await new Promise<void>((resolve) => (release = resolve))
      return base(url)
    })
    await startConversation()
    fireEvent.click(screen.getByRole('button', { name: '대화 끝내기' }))
    expect(await screen.findByText('오늘 대화를 일지로 정리하는 중이에요…')).toBeVisible()
    expect(screen.queryByRole('button', { name: '글로 새 대화' })).not.toBeInTheDocument()
    release()
    const log = screen.getByRole('log', { name: '대화 내용' })
    expect(await within(log).findByText('오늘 아이디어 1개 저장했어요!')).toBeInTheDocument()
    expect(screen.queryByText('오늘 대화를 일지로 정리하는 중이에요…')).toBeNull()
    expect(await screen.findByText('대화가 끝났어요.')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '메시지' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '글로 새 대화' })).toBeInTheDocument()
  })

  it('답변을 기다리는 중에도 대화를 끝낼 수 있다(받던 답변은 끊고 대기 표시를 지운다)', async () => {
    const fetchMock = stubServer()
    const base = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (!url.endsWith('/turns')) return base(url)
      // turn 이벤트만 보내고 멈춘 답변(CLI가 멈춘 경우). 요청을 끊으면 스트림도 끝난다
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode('event: turn\ndata: {"type":"turn","turn_id":"a1"}\n\n'))
          init?.signal?.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')))
        },
      })
      return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } })
    })
    await startConversation()
    fireEvent.change(screen.getByRole('textbox', { name: '메시지' }), { target: { value: '안녕' } })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
    expect(await screen.findByText('답변 준비 중')).toBeInTheDocument()
    const end = screen.getByRole('button', { name: '대화 끝내기' })
    expect(end).toBeEnabled()
    fireEvent.click(end)
    expect(await screen.findByText('대화가 끝났어요.')).toBeInTheDocument()
    expect(screen.queryByText('답변 준비 중')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(calls(fetchMock, '/end')).toBe(1)
  })

  it('끝난 대화에서 일지 보기를 누르면 그 세션의 일지를 연다', async () => {
    stubServer()
    const onOpenJournal = vi.fn()
    render(<ConversationScreen onOpenJournal={onOpenJournal} />)
    fireEvent.click(screen.getByRole('button', { name: '글로 대화' }))
    await screen.findByText('안녕하세요, 오늘 어떤 이야기를 할까요?')
    expect(screen.queryByRole('button', { name: '일지 보기' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '대화 끝내기' }))
    fireEvent.click(await screen.findByRole('button', { name: '일지 보기' }))
    expect(onOpenJournal).toHaveBeenCalledWith('s1')
  })

  it('시작에 실패하면 오류와 함께 다시 시작 버튼을 보여 준다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ error: { code: 'llm_error', message: '인사말을 받지 못했습니다.' } }), { status: 502 })),
    )
    render(<ConversationScreen />)
    fireEvent.click(screen.getByRole('button', { name: '글로 대화' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('인사말을 받지 못했습니다.')
    expect(screen.getByRole('button', { name: '글로 대화' })).toBeEnabled()
  })
})

describe('대화 방식', () => {
  beforeEach(() => localStorage.clear()) // 다른 테스트가 글로 대화를 골라 남긴 값을 지운다

  it('처음에는 음성으로 미리 준비하고, 글로 대화를 고르면 그 방식을 기억한다', async () => {
    const fetchMock = stubServer()
    render(<ConversationScreen />)
    expect(screen.getByRole('button', { name: '음성 준비 중…' })).toBeDisabled() // 음성 모듈을 불러오는 중
    expect(await screen.findByRole('button', { name: '음성으로 대화' })).toBeEnabled()
    const requests = () => fetchMock.mock.calls as unknown as [string, RequestInit][]
    const preparedModes = () =>
      requests()
        .filter(([url]) => url.endsWith('/prepare'))
        .map(([, init]) => JSON.parse(init.body as string).mode)
    await waitFor(() => expect(preparedModes()).toEqual(['voice']))

    fireEvent.click(screen.getByRole('button', { name: '글로 대화' }))
    await screen.findByText('안녕하세요, 오늘 어떤 이야기를 할까요?')
    expect(localStorage.getItem('trailtalk.mode')).toBe('text')
    const started = requests().find(([url]) => url === '/api/sessions')
    expect(JSON.parse(started![1].body as string)).toEqual({ mode: 'text' })
  })
})
