// 대화 세션 API(docs/client-contract.md 2절 "세션 API"). 타입은 서버 OpenAPI에서 생성한 schema.d.ts를 쓴다.
import type { StreamEvent } from '../core/conversation'
import { SseParser } from '../core/sse'
import type { components } from './schema'

export type SessionStarted = components['schemas']['SessionStarted']
export type SessionOut = components['schemas']['SessionOut']

/** 서버 공통 오류 형식(클라이언트 규약 7절) 또는 네트워크 오류. */
export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

const NETWORK_ERROR = '서버에 연결할 수 없어요.'

async function post(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  let response: Response
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError('network_error', NETWORK_ERROR, 0)
  }
  if (!response.ok) throw await errorOf(response)
  return response
}

async function errorOf(response: Response): Promise<ApiError> {
  try {
    const body = await response.json()
    if (body?.error?.code) {
      return new ApiError(body.error.code, body.error.message, response.status)
    }
  } catch {
    // 본문이 JSON이 아니면 상태 코드로만 알린다
  }
  return new ApiError('http_error', `요청이 실패했어요(${response.status}).`, response.status)
}

export async function startSession(
  mode: 'text' | 'voice' = 'text',
  signal?: AbortSignal,
): Promise<SessionStarted> {
  return (await post('/api/sessions', { mode }, signal)).json()
}

export async function endSession(sessionId: string, signal?: AbortSignal): Promise<SessionOut> {
  return (await post(`/api/sessions/${encodeURIComponent(sessionId)}/end`, {}, signal)).json()
}

/**
 * 메시지를 보내고 답변 이벤트를 onEvent로 차례대로 넘긴다. done·error 이벤트 뒤에 끝난다.
 * 시작 전 오류(세션 없음, 진행 중인 턴 등)와 스트림이 중간에 끊긴 경우는 ApiError로 던진다.
 */
export async function sendTurn(
  sessionId: string,
  text: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await post(
    `/api/sessions/${encodeURIComponent(sessionId)}/turns`,
    { text },
    signal,
  )
  if (!response.body) throw new ApiError('stream_closed', '답변을 받지 못했어요.', 0)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const parser = new SseParser()
  let finished = false
  const handle = (data: string) => {
    let event: StreamEvent
    try {
      event = JSON.parse(data) as StreamEvent
    } catch {
      throw new ApiError('bad_event', '답변을 읽지 못했어요.', 0)
    }
    if (event.type === 'done' || event.type === 'error') finished = true
    onEvent(event)
  }
  try {
    for (;;) {
      let result: ReadableStreamReadResult<Uint8Array>
      try {
        result = await reader.read()
      } catch (error) {
        if (signal?.aborted) throw error
        throw new ApiError('stream_closed', '답변을 받는 중에 연결이 끊겼어요.', 0)
      }
      const { done, value } = result
      const chunk = done ? decoder.decode() : decoder.decode(value, { stream: true })
      for (const message of parser.feed(chunk)) handle(message.data)
      if (done) break
    }
    for (const message of parser.end()) handle(message.data)
  } catch (error) {
    // 여기서 그만 읽으면 연결을 닫아 서버가 턴을 멈추게 한다(열어 두면 다음 전송이 409가 된다)
    await reader.cancel().catch(() => {})
    throw error
  } finally {
    reader.releaseLock()
  }
  if (!finished) throw new ApiError('stream_closed', '답변을 받는 중에 연결이 끊겼어요.', 0)
}
