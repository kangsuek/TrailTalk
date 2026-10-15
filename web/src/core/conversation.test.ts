import { describe, expect, it } from 'vitest'
import {
  conversationReducer,
  initialConversation,
  toolNotice,
  type AssistantMessage,
  type ConversationAction,
  type ConversationState,
  type StreamEvent,
  type ToolState,
} from './conversation'

function reduce(actions: ConversationAction[], state = initialConversation): ConversationState {
  return actions.reduce(conversationReducer, state)
}

const started: ConversationAction[] = [
  { type: 'start' },
  {
    type: 'started',
    sessionId: 's1',
    personaName: '도우미',
    greeting: { turnId: 'g1', text: '안녕하세요!' },
  },
]

const ev = (event: StreamEvent): ConversationAction => ({ type: 'event', event })

function tool(phase: 'start' | 'call' | 'end', extra: Partial<StreamEvent> = {}): StreamEvent {
  return {
    type: 'tool',
    phase,
    tool_use_id: 'u1',
    name: 'web_search',
    input: null,
    summary: null,
    is_error: false,
    ...extra,
  } as StreamEvent
}

function last(state: ConversationState): AssistantMessage {
  return state.messages.at(-1) as AssistantMessage
}

describe('conversationReducer', () => {
  it('시작하면 인사말 말풍선 하나로 대화를 연다', () => {
    const state = reduce(started)
    expect(state.status).toBe('active')
    expect(state.personaName).toBe('도우미')
    expect(state.messages).toEqual([
      expect.objectContaining({ role: 'assistant', id: 'g1', sentences: ['안녕하세요!'] }),
    ])
  })

  it('턴 이벤트를 받아 문장을 쌓고 done에서 끝낸다', () => {
    const state = reduce([
      ...started,
      { type: 'send', id: 'u-1', text: '안녕' },
      ev({ type: 'turn', turn_id: 'a1' }),
      ev({ type: 'sentence', index: 0, text: '첫 문장.' }),
      ev({ type: 'sentence', index: 1, text: '둘째 문장.' }),
      ev({
        type: 'done',
        turn_id: 'a1',
        text: '첫 문장. 둘째 문장.',
        interrupted: false,
        session_status: 'active',
      }),
    ])
    expect(state.sending).toBe(false)
    expect(state.messages.map((m) => m.role)).toEqual(['assistant', 'user', 'assistant'])
    expect(last(state)).toMatchObject({
      id: 'a1',
      sentences: ['첫 문장.', '둘째 문장.'],
      status: 'done',
    })
  })

  it('send하면 보내는 중이 되고 이전 오류를 지운다', () => {
    const state = reduce([
      ...started,
      { type: 'failed', message: '실패' },
      { type: 'send', id: 'u-1', text: '다시' },
    ])
    expect(state.sending).toBe(true)
    expect(state.error).toBeNull()
  })

  it('도구 이벤트는 tool_use_id로 합치고 입력·요약을 유지한다', () => {
    const state = reduce([
      ...started,
      ev({ type: 'turn', turn_id: 'a1' }),
      ev(tool('start')),
      ev(tool('call', { input: { query: '날씨' } } as Partial<StreamEvent>)),
      ev(
        tool('end', {
          summary: { query: '날씨', links: [{ url: 'https://www.weather.go.kr/x' }] },
        } as Partial<StreamEvent>),
      ),
    ])
    const [only] = last(state).tools
    expect(last(state).tools).toHaveLength(1)
    expect(only).toMatchObject({ phase: 'end', input: { query: '날씨' } })
    expect(toolNotice(only)).toBe('출처: weather.go.kr')
  })

  it('문장 없이 done이 오면 전체 답변으로 채운다', () => {
    const state = reduce([
      ...started,
      ev({ type: 'turn', turn_id: 'a1' }),
      ev({ type: 'done', turn_id: 'a1', text: '짧은 답', interrupted: false, session_status: 'paused' }),
    ])
    expect(last(state).sentences).toEqual(['짧은 답'])
    expect(state.status).toBe('paused')
  })

  it('error 이벤트는 진행 중인 말풍선을 오류로 표시한다', () => {
    const state = reduce([
      ...started,
      { type: 'send', id: 'u-1', text: '안녕' },
      ev({ type: 'turn', turn_id: 'a1' }),
      ev({ type: 'error', code: 'llm_error', message: '답변을 만들지 못했습니다.' }),
    ])
    expect(state.error).toBe('답변을 만들지 못했습니다.')
    expect(state.sending).toBe(false)
    expect(last(state).status).toBe('error')
  })

  it('시작에 실패하면 처음 화면으로 돌아간다', () => {
    const state = reduce([{ type: 'start' }, { type: 'failed', message: '서버에 연결할 수 없어요.' }])
    expect(state.status).toBe('idle')
    expect(state.error).toBe('서버에 연결할 수 없어요.')
  })

  it('모르는 이벤트·액션은 상태를 그대로 둔다', () => {
    const state = reduce(started)
    const unknownEvent = { type: 'event', event: { type: 'transcript', text: '음성' } } as unknown
    expect(conversationReducer(state, unknownEvent as ConversationAction)).toBe(state)
    expect(conversationReducer(state, { type: 'nope' } as unknown as ConversationAction)).toBe(state)
  })

  it('서버가 받기 전에 실패한 메시지는 목록에서 뺀다(다시 보내도 중복되지 않게)', () => {
    const state = reduce([
      ...started,
      { type: 'send', id: 'u-1', text: '안녕' },
      { type: 'failed', message: '이전 답변이 아직 끝나지 않았습니다.', code: 'turn_in_progress', unsentId: 'u-1' },
    ])
    expect(state.messages.map((m) => m.id)).toEqual(['g1'])
    expect(state.status).toBe('active')
  })

  it.each(['session_ended', 'session_not_found'])('%s 오류면 대화를 끝낸다', (code) => {
    const state = reduce([...started, { type: 'send', id: 'u-1', text: '안녕' }, { type: 'failed', message: '끝', code }])
    expect(state.status).toBe('ended')
  })

  it('턴 도중 session_ended 오류 이벤트가 오면 대화를 끝낸다', () => {
    const state = reduce([
      ...started,
      ev({ type: 'turn', turn_id: 'a1' }),
      ev({ type: 'error', code: 'session_ended', message: '대화를 마쳤어요.' }),
    ])
    expect(state.status).toBe('ended')
  })

  it('done의 session_status가 ended면 대화가 끝난다', () => {
    const state = reduce([
      ...started,
      ev({ type: 'turn', turn_id: 'a1' }),
      ev({ type: 'done', turn_id: 'a1', text: '잘 가요', interrupted: false, session_status: 'ended' }),
    ])
    expect(state.status).toBe('ended')
  })
})

describe('toolNotice', () => {
  const base: ToolState = {
    id: 'u1',
    name: 'web_search',
    phase: 'start',
    input: null,
    summary: null,
    isError: false,
  }

  it.each<[Partial<ToolState>, string | null]>([
    [{}, '검색 중…'],
    [{ phase: 'call', input: { query: 'uv' } }, "'uv' 검색 중…"],
    [{ phase: 'end', summary: { links: [] } }, '검색 완료'],
    [{ phase: 'end', isError: true }, '검색하지 못했어요'],
    [
      {
        phase: 'end',
        summary: {
          links: [
            { url: 'https://a.com/1' },
            { url: 'https://a.com/2' },
            { url: 'not a url' },
            { url: 'https://b.org' },
          ],
        },
      },
      '출처: a.com, b.org',
    ],
    [{ name: 'web_fetch' }, '페이지 읽는 중…'],
    [{ name: 'web_fetch', phase: 'end', input: { url: 'https://docs.astral.sh/uv/' } }, '출처: docs.astral.sh'],
    [{ name: 'save_note' }, '메모 저장 중…'],
    [{ name: 'save_note', phase: 'end', input: { kind: 'idea', content: '지도 앱' } }, '메모 저장: 지도 앱'],
    [{ name: 'save_note', phase: 'end', isError: true }, '메모를 저장하지 못했어요'],
    [{ name: 'search_notes' }, '지난 메모 찾는 중…'],
    [{ name: 'search_notes', phase: 'call', input: { keyword: '쓰레기통' } }, "지난 메모에서 '쓰레기통' 찾는 중…"],
    [{ name: 'search_notes', phase: 'end', input: { keyword: '쓰레기통' } }, '지난 메모 찾기: 쓰레기통'],
    [{ name: 'web_fetch', phase: 'end', input: { url: 'https://a.com/x' }, summary: { code: 404, bytes: 0 } }, '페이지를 읽지 못했어요'],
    [{ name: 'summarize_session', phase: 'end' }, '대화 정리 완료'],
    [{ name: 'pause_session' }, null],
    [{ name: 'end_session', phase: 'end' }, null],
    [{ name: 'unknown_tool' }, null],
  ])('%o → %s', (patch, expected) => {
    expect(toolNotice({ ...base, ...patch })).toBe(expected)
  })
})
