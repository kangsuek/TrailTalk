import { useEffect, useReducer, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, endSession, sendTurn, startSession } from '../api/conversation'
import {
  conversationReducer,
  initialConversation,
  toolNotice,
  type AssistantMessage,
} from '../core/conversation'

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '알 수 없는 오류가 났어요.'
}

function AssistantBubble({ message, name }: { message: AssistantMessage; name: string }) {
  const notices = message.tools
    .map((tool) => ({ id: tool.id, text: toolNotice(tool), done: tool.phase === 'end' }))
    .filter((n) => n.text !== null)
  const waiting = message.status === 'streaming' && message.sentences.length === 0
  return (
    <li className="message assistant" data-status={message.status}>
      <span className="speaker">{name}</span>
      {notices.length > 0 && (
        <ul className="notices">
          {notices.map((n) => (
            <li key={n.id} className="notice" data-done={n.done} title={n.text ?? undefined}>
              {n.text}
            </li>
          ))}
        </ul>
      )}
      {message.sentences.length > 0 && (
        <p className="bubble">
          {message.sentences.map((sentence, i) => (
            <span key={i} className="sentence">
              {sentence}{' '}
            </span>
          ))}
        </p>
      )}
      {waiting && notices.length === 0 && (
        <p className="bubble typing">
          <span aria-hidden="true">…</span>
          <span className="sr-only">답변 준비 중</span>
        </p>
      )}
    </li>
  )
}

/** visible: 탭에서 지금 보이는지. 숨겨져 있어도 대화를 유지하려고 언마운트하지 않는다(App). */
export function ConversationScreen({ visible = true }: { visible?: boolean }) {
  const [state, dispatch] = useReducer(conversationReducer, initialConversation)
  const [draft, setDraft] = useState('')
  const controller = useRef<AbortController | null>(null)
  const nextId = useRef(0)
  const listEnd = useRef<HTMLLIElement>(null)

  // 화면을 떠나면 진행 중인 요청을 멈춘다(서버는 연결이 끊기면 CLI 턴을 정리한다)
  useEffect(() => () => controller.current?.abort(), [])

  // 새 말풍선·문장이 오면 아래로 내린다. 위로 올려 읽는 중이면 끌어내리지 않는다
  const stickToBottom = useRef(true)
  useEffect(() => {
    if (!visible) return // 다른 탭의 스크롤은 대화 위치와 상관없다
    const onScroll = () => {
      const { scrollY, innerHeight } = window
      stickToBottom.current = scrollY + innerHeight >= document.documentElement.scrollHeight - 200
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    // 다시 보이면 숨겨진 동안 온 답변까지 바닥으로 내린다
    stickToBottom.current = true
    listEnd.current?.scrollIntoView?.({ block: 'end' })
    return () => window.removeEventListener('scroll', onScroll)
  }, [visible])
  useEffect(() => {
    if (visible && stickToBottom.current) listEnd.current?.scrollIntoView?.({ block: 'end' })
  }, [state.messages, visible])

  const run = async (task: (signal: AbortSignal) => Promise<void>) => {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    try {
      await task(current.signal)
    } catch (error) {
      if (!current.signal.aborted) dispatch({ type: 'failed', message: errorMessage(error) })
    }
  }

  const start = () =>
    run(async (signal) => {
      dispatch({ type: 'start' })
      const body = await startSession('text', signal)
      dispatch({
        type: 'started',
        sessionId: body.session.id,
        personaName: body.persona.name,
        greeting: { turnId: body.greeting.turn_id, text: body.greeting.text },
      })
    })

  const canSend =
    state.sessionId !== null &&
    (state.status === 'active' || state.status === 'paused') &&
    !state.sending

  const send = (event?: FormEvent) => {
    event?.preventDefault()
    const text = draft.trim()
    if (!text || !canSend || state.sessionId === null) return
    const sessionId = state.sessionId
    setDraft('')
    stickToBottom.current = true
    dispatch({ type: 'send', id: `local-${nextId.current++}`, text })
    let answered = false
    void run(async (signal) => {
      try {
        await sendTurn(
          sessionId,
          text,
          (streamEvent) => {
            if (streamEvent.type === 'turn') answered = true
            dispatch({ type: 'event', event: streamEvent })
          },
          signal,
        )
      } catch (error) {
        // 서버가 받기 전에 실패했으면(네트워크·409 등) 쓴 글을 되살려 다시 보낼 수 있게 한다
        if (!answered && !signal.aborted) setDraft((current) => current || text)
        throw error
      }
    })
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 조합 중 Enter는 글자 확정이므로 보내지 않는다(Safari는 isComposing 대신 keyCode 229)
    const composing = event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229
    if (event.key === 'Enter' && !event.shiftKey && !composing) {
      event.preventDefault()
      send()
    }
  }

  const end = () => {
    if (state.sessionId === null) return
    const sessionId = state.sessionId
    void run(async (signal) => {
      dispatch({ type: 'ending' })
      await endSession(sessionId, signal)
      dispatch({ type: 'ended' })
    })
  }

  const name = state.personaName ?? ''
  const inConversation = state.status === 'active' || state.status === 'paused'

  return (
    <section className="conversation">
      <h2>대화</h2>
      {(state.status === 'idle' || state.status === 'starting') && (
        <div className="conversation-start">
          <p>걸으면서 떠오르는 생각을 같이 이야기해 봐요.</p>
          <button type="button" onClick={start} disabled={state.status === 'starting'}>
            {state.status === 'starting' ? '연결하는 중…' : '대화 시작'}
          </button>
        </div>
      )}

      {state.messages.length > 0 && (
        <ol className="messages" role="log" aria-label="대화 내용" aria-live="polite">
          {state.messages.map((message) =>
            message.role === 'user' ? (
              <li key={message.id} className="message user">
                <span className="speaker">나</span>
                <p className="bubble">{message.text}</p>
              </li>
            ) : (
              <AssistantBubble key={message.id} message={message} name={name} />
            ),
          )}
          <li ref={listEnd} className="list-end" aria-hidden="true" />
        </ol>
      )}

      {state.error && (
        <p className="conversation-error" role="alert">
          {state.error}
        </p>
      )}
      {state.status === 'paused' && (
        <p className="conversation-note">쉬는 중이에요. 말을 걸면 다시 이어 가요.</p>
      )}

      {inConversation && (
        <form className="composer" onSubmit={send}>
          <textarea
            aria-label="메시지"
            value={draft}
            rows={2}
            maxLength={4000}
            placeholder="메시지를 입력하세요"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <div className="composer-actions">
            <button type="button" className="secondary" onClick={end} disabled={state.sending}>
              대화 끝내기
            </button>
            <button type="submit" disabled={!canSend || !draft.trim()}>
              보내기
            </button>
          </div>
        </form>
      )}

      {state.status === 'ended' && (
        <div className="conversation-start">
          <p className="conversation-note">대화가 끝났어요.</p>
          <button type="button" onClick={start}>
            새 대화 시작
          </button>
        </div>
      )}
    </section>
  )
}
