import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
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
  { type: 'tool', phase: 'start', tool_use_id: 'u1', name: 'save_note', input: null, summary: null, is_error: false },
  {
    type: 'tool',
    phase: 'call',
    tool_use_id: 'u1',
    name: 'save_note',
    input: { kind: 'idea', content: '쓰레기통 지도' },
    summary: null,
    is_error: false,
  },
  { type: 'tool', phase: 'end', tool_use_id: 'u1', name: 'save_note', input: null, summary: { result: 'ok' }, is_error: false },
  { type: 'sentence', index: 0, text: '저장했어요!' },
  { type: 'sentence', index: 1, text: '누가 쓰면 좋을까요?' },
  { type: 'done', turn_id: 'a1', text: '저장했어요! 누가 쓰면 좋을까요?', interrupted: false, session_status: 'active' },
]

function stubServer(turn: () => Response = () => sseResponse(TURN)) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === '/api/sessions') return new Response(JSON.stringify(STARTED), { status: 201 })
    if (url.endsWith('/turns')) return turn()
    if (url.endsWith('/end')) return new Response(JSON.stringify({ ...STARTED.session, status: 'ended' }))
    throw new Error(`unexpected ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function startConversation() {
  render(<ConversationScreen />)
  fireEvent.click(screen.getByRole('button', { name: '대화 시작' }))
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

    expect(await within(log).findByText('메모 저장: 쓰레기통 지도')).toBeInTheDocument()
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
    expect(fetchMock).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await screen.findByText(/누가 쓰면 좋을까요\?/)
  })

  it('Safari처럼 keyCode 229로 오는 조합 확정 Enter도 보내지 않는다', async () => {
    const fetchMock = stubServer()
    await startConversation()
    const input = screen.getByRole('textbox', { name: '메시지' })
    fireEvent.change(input, { target: { value: '안녕' } })
    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
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

  it('대화를 끝내면 입력창이 사라지고 새 대화를 시작할 수 있다', async () => {
    stubServer()
    await startConversation()
    fireEvent.click(screen.getByRole('button', { name: '대화 끝내기' }))
    expect(await screen.findByText('대화가 끝났어요.')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '메시지' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '새 대화 시작' })).toBeInTheDocument()
  })

  it('시작에 실패하면 오류와 함께 다시 시작 버튼을 보여 준다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ error: { code: 'llm_error', message: '인사말을 받지 못했습니다.' } }), { status: 502 })),
    )
    render(<ConversationScreen />)
    fireEvent.click(screen.getByRole('button', { name: '대화 시작' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('인사말을 받지 못했습니다.')
    expect(screen.getByRole('button', { name: '대화 시작' })).toBeEnabled()
  })
})
