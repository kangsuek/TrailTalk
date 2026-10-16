// 대화 세션 API(docs/client-contract.md 2절 "세션 API"). 타입은 서버 OpenAPI에서 생성한 schema.d.ts를 쓴다.
import type { StreamEvent } from '../core/conversation'
import { SseParser } from '../core/sse'
import type { RecordedAudio } from '../core/audio'
import { ApiError, RawBody, request } from './http'
import type { components } from './schema'

export { ApiError }

export type SessionStarted = components['schemas']['SessionStarted']
export type SessionOut = components['schemas']['SessionOut']
export type SessionClosed = components['schemas']['SessionClosed']

function post(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  return request(path, 'POST', body, signal)
}

/** 다음 대화의 CLI를 서버에 미리 띄워 둔다(인사말 대기 단축). 응답 본문은 없다. */
export async function prepareSession(
  mode: 'text' | 'voice' = 'text',
  signal?: AbortSignal,
): Promise<void> {
  await post('/api/sessions/prepare', { mode }, signal)
}

export async function startSession(
  mode: 'text' | 'voice' = 'text',
  signal?: AbortSignal,
): Promise<SessionStarted> {
  return (await post('/api/sessions', { mode }, signal)).json()
}

/** 대화를 끝낸다. 서버가 일지 정리를 잠깐 기다린 뒤 마무리 멘트와 저장 개수를 준다(여러 번 불러도 같다). */
export async function endSession(sessionId: string, signal?: AbortSignal): Promise<SessionClosed> {
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
  await readTurnStream(response, onEvent, signal)
}

/**
 * 말 한 번의 녹음을 보내고 답변 이벤트를 넘긴다(transcript → turn → …). 인식 오류·말 없음(no_speech)은
 * 스트림 전에 ApiError로 던진다(규약 2절 음성 턴).
 */
export async function sendAudioTurn(
  sessionId: string,
  audio: RecordedAudio,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await post(
    `/api/sessions/${encodeURIComponent(sessionId)}/turns/audio`,
    new RawBody(audio.bytes, audio.mimeType),
    signal,
  )
  await readTurnStream(response, onEvent, signal)
}

async function readTurnStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
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
    if (typeof event !== 'object' || event === null || typeof event.type !== 'string') {
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
