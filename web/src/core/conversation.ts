// 텍스트 대화 화면 상태(리듀서)와 도구 알림 문구.
// 서버 SSE 이벤트(docs/client-contract.md 2절)를 말풍선 목록으로 바꾼다. 문장 분할·요약은 서버가 하고
// 여기서는 받은 그대로 쌓기만 한다. UI·브라우저 API에 의존하지 않는다(안드로이드 포팅 대상).
import type { components } from '../api/schema'

export type StreamEvent = components['schemas']['StreamEvent']
type ToolEvent = components['schemas']['ToolEvent']

export interface ToolState {
  id: string
  name: string
  phase: ToolEvent['phase']
  input: Record<string, unknown> | null
  summary: Record<string, unknown> | null
  isError: boolean
}

export interface UserMessage {
  role: 'user'
  id: string
  text: string
}

export interface AssistantMessage {
  role: 'assistant'
  id: string
  sentences: string[]
  tools: ToolState[]
  status: 'streaming' | 'done' | 'error'
  interrupted: boolean
}

export type Message = UserMessage | AssistantMessage

export type SessionStatus = 'idle' | 'starting' | 'active' | 'paused' | 'ended'

export interface ConversationState {
  status: SessionStatus
  sessionId: string | null
  personaName: string | null
  messages: Message[]
  sending: boolean
  // 끝내기 요청 중(서버가 일지를 정리하는 동안 기다린다)
  ending: boolean
  // 끝내기 응답 때 일지 정리가 아직 끝나지 않았다(마무리 멘트의 개수가 나중에 늘 수 있다)
  journalPending: boolean
  error: string | null
}

export type ConversationAction =
  | { type: 'start' }
  | {
      type: 'started'
      sessionId: string
      personaName: string
      greeting: { turnId: string; text: string }
    }
  | { type: 'send'; id: string; text: string }
  | { type: 'event'; event: StreamEvent }
  // code: 서버 오류 코드(세션이 이미 끝났으면 대화를 끝낸다), unsentId: 서버가 받기 전에 실패해
  // 입력창으로 되돌린 사용자 메시지(목록에서 뺀다)
  | { type: 'failed'; message: string; code?: string; unsentId?: string }
  // 끼어들기: 그 답변을 들려준 문장(keep개)까지만 남기고 끊긴 답변으로 마무리한다(받는 중이었어도)
  | { type: 'interrupt'; turnId: string; keep: number }
  | { type: 'ending' }
  // closing: 서버가 준 마무리 멘트(캐릭터 말풍선으로 보인다), journalPending: 일지 정리가 아직 진행 중
  | { type: 'ended'; closing?: string; journalPending?: boolean }

const SESSION_GONE = new Set(['session_ended', 'session_not_found'])

export const initialConversation: ConversationState = {
  status: 'idle',
  sessionId: null,
  personaName: null,
  messages: [],
  sending: false,
  ending: false,
  journalPending: false,
  error: null,
}

/** 진행 중인 답변 말풍선을 바꾼다(없으면 그대로). */
function updateStreaming(
  messages: Message[],
  update: (message: AssistantMessage) => AssistantMessage,
): Message[] {
  const index = messages.findLastIndex((m) => m.role === 'assistant' && m.status === 'streaming')
  if (index === -1) return messages
  const next = messages.slice()
  next[index] = update(messages[index] as AssistantMessage)
  return next
}

function applyTool(tools: ToolState[], event: ToolEvent): ToolState[] {
  const index = tools.findIndex((t) => t.id === event.tool_use_id)
  const previous = index === -1 ? null : tools[index]
  const tool: ToolState = {
    id: event.tool_use_id,
    name: event.name,
    phase: event.phase,
    input: event.input ?? previous?.input ?? null,
    summary: event.summary ?? previous?.summary ?? null,
    isError: event.is_error,
  }
  if (index === -1) return [...tools, tool]
  const next = tools.slice()
  next[index] = tool
  return next
}

function applyEvent(state: ConversationState, event: StreamEvent): ConversationState {
  switch (event.type) {
    case 'turn':
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            role: 'assistant',
            id: event.turn_id,
            sentences: [],
            tools: [],
            status: 'streaming',
            interrupted: false,
          },
        ],
      }
    case 'sentence':
      return {
        ...state,
        messages: updateStreaming(state.messages, (m) => ({
          ...m,
          sentences: [...m.sentences, event.text],
        })),
      }
    case 'tool':
      return {
        ...state,
        messages: updateStreaming(state.messages, (m) => ({
          ...m,
          tools: applyTool(m.tools, event),
        })),
      }
    case 'done':
      return {
        ...state,
        sending: false,
        status: event.session_status,
        messages: updateStreaming(state.messages, (m) => ({
          ...m,
          // 문장 이벤트를 하나도 못 받았으면 전체 답변으로 채운다
          sentences: m.sentences.length > 0 || !event.text ? m.sentences : [event.text],
          status: 'done',
          interrupted: event.interrupted,
        })),
      }
    case 'error':
      return {
        ...state,
        // 턴 도중 세션이 끝났으면(끝내기 요청 뒤 오류 등) 끝난 화면으로 간다
        status: SESSION_GONE.has(event.code) ? 'ended' : state.status,
        sending: false,
        error: event.message,
        messages: updateStreaming(state.messages, (m) => ({ ...m, status: 'error' })),
      }
    default:
      return state // 서버가 먼저 추가한 새 이벤트는 무시한다(앱이 멈추지 않게)
  }
}

export function conversationReducer(
  state: ConversationState,
  action: ConversationAction,
): ConversationState {
  switch (action.type) {
    case 'start':
      return { ...initialConversation, status: 'starting' }
    case 'started':
      return {
        ...state,
        status: 'active',
        sessionId: action.sessionId,
        personaName: action.personaName,
        error: null,
        messages: [
          {
            role: 'assistant',
            id: action.greeting.turnId,
            sentences: [action.greeting.text],
            tools: [],
            status: 'done',
            interrupted: false,
          },
        ],
      }
    case 'send':
      return {
        ...state,
        sending: true,
        error: null,
        messages: [...state.messages, { role: 'user', id: action.id, text: action.text }],
      }
    case 'event':
      return applyEvent(state, action.event)
    case 'failed': {
      const messages = action.unsentId
        ? state.messages.filter((m) => m.id !== action.unsentId)
        : state.messages
      return {
        ...state,
        ending: false,
        // 시작 실패면 처음 화면으로, 서버에서 이미 끝난 세션이면 끝난 화면으로 간다
        status:
          state.status === 'starting'
            ? 'idle'
            : action.code && SESSION_GONE.has(action.code)
              ? 'ended'
              : state.status,
        sending: false,
        error: action.message,
        messages: updateStreaming(messages, (m) => ({ ...m, status: 'error' })),
      }
    }
    case 'interrupt': {
      const index = state.messages.findIndex((m) => m.role === 'assistant' && m.id === action.turnId)
      if (index === -1) return state
      const message = state.messages[index] as AssistantMessage
      const streaming = message.status === 'streaming'
      if (!streaming && action.keep >= message.sentences.length) return state // 다 들었다
      const messages = state.messages.slice()
      messages[index] = {
        ...message,
        sentences: message.sentences.slice(0, Math.max(action.keep, 0)),
        status: 'done',
        interrupted: true,
      }
      return { ...state, messages, sending: streaming ? false : state.sending }
    }
    case 'ending':
      // 받는 중에 끝내면 그 답변은 받은 데까지 끊긴 답변으로 마무리한다(대기 표시가 남지 않게)
      return {
        ...state,
        sending: true,
        ending: true,
        error: null,
        messages: updateStreaming(state.messages, (m) => ({ ...m, status: 'done', interrupted: true })),
      }
    case 'ended': {
      const closing: AssistantMessage[] = action.closing
        ? [
            {
              role: 'assistant',
              id: 'closing',
              sentences: [action.closing],
              tools: [],
              status: 'done',
              interrupted: false,
            },
          ]
        : []
      return {
        ...state,
        status: 'ended',
        sending: false,
        ending: false,
        journalPending: action.journalPending ?? false,
        messages: [...state.messages.filter((m) => m.id !== 'closing'), ...closing],
      }
    }
    default:
      return state
  }
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function hostOf(url: unknown): string | null {
  if (typeof url !== 'string') return null
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return null
  }
}

function sources(summary: Record<string, unknown> | null): string[] {
  const links = Array.isArray(summary?.links) ? summary.links : []
  const hosts = links.map((link) => hostOf((link as { url?: unknown })?.url))
  return [...new Set(hosts.filter((h): h is string => h !== null))].slice(0, 3)
}

// 저장한 노트 종류의 이름과 목적격(을/를)
const NOTE_LABELS: Record<string, [string, string]> = {
  idea: ['아이디어', '아이디어를'],
  todo: ['할 일', '할 일을'],
  memo: ['메모', '메모를'],
}

/** 도구 상태를 한 줄 알림으로. 보여 줄 필요가 없는 도구(쉬기·끝내기)는 null. */
export function toolNotice(tool: ToolState): string | null {
  const finished = tool.phase === 'end'
  switch (tool.name) {
    case 'web_search': {
      if (!finished) {
        const query = text(tool.input?.query)
        return query ? `'${query}' 검색 중…` : '검색 중…'
      }
      if (tool.isError) return '검색하지 못했어요'
      const hosts = sources(tool.summary)
      return hosts.length > 0 ? `출처: ${hosts.join(', ')}` : '검색 완료'
    }
    case 'web_fetch': {
      if (!finished) return '페이지 읽는 중…'
      const code = tool.summary?.code
      if (tool.isError || (typeof code === 'number' && code >= 400)) return '페이지를 읽지 못했어요'
      const host = hostOf(tool.input?.url)
      return host ? `출처: ${host}` : '페이지 읽기 완료'
    }
    case 'save_note': {
      // 도구 입력의 종류(idea·todo·memo)대로 부른다. start 단계에는 입력이 없어 종류를 모른다
      const kind = String(tool.input?.kind)
      const [label, object] = Object.hasOwn(NOTE_LABELS, kind) ? NOTE_LABELS[kind] : NOTE_LABELS.memo
      if (!finished) return tool.input ? `${label} 저장 중…` : '저장 중…'
      if (tool.isError) return `${object} 저장하지 못했어요`
      const content = text(tool.input?.content)
      return content ? `${label} 저장: ${content}` : `${label} 저장 완료`
    }
    case 'search_notes': {
      const keyword = text(tool.input?.keyword)
      if (!finished) return keyword ? `지난 메모에서 '${keyword}' 찾는 중…` : '지난 메모 찾는 중…'
      return keyword ? `지난 메모 찾기: ${keyword}` : '지난 메모 찾기 완료'
    }
    case 'summarize_session':
      return finished ? '대화 정리 완료' : '대화 정리 중…'
    default:
      return null
  }
}
