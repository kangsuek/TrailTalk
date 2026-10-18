import {
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useReducer,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type Ref,
} from 'react'
import { ApiError, endSession, prepareSession, reopenSession, sendTurn, startSession } from '../api/conversation'
import {
  conversationReducer,
  initialConversation,
  toolNotice,
  type AssistantMessage,
} from '../core/conversation'
import { useVoiceConversation } from './useVoiceConversation'
import { VoiceControls } from './VoiceControls'

type Mode = 'text' | 'voice'

/** 이어서 하기 결과: 시작함(또는 이미 그 대화 중), 다른 대화가 진행 중, 음성 기능을 불러오는 중·못 씀 */
export type ContinueResult = 'ok' | 'busy' | 'voice_loading' | 'voice_unavailable'

export interface ConversationHandle {
  /**
   * 끝난 대화를 다시 열어 이어서 한다(S3-26). 다른 대화가 진행 중이면 'busy'(서버는 막지 않으므로
   * 여기서 막는다). 음성은 시작 버튼처럼 사용자 동작 안에서 불러야 소리가 난다
   */
  continueWith(sessionId: string, mode: Mode): ContinueResult
}

const MODE_KEY = 'trailtalk.mode'

/** 마지막으로 고른 대화 방식(미리 준비를 같은 방식으로 하려고 기억한다). 처음에는 음성 */
function savedMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === 'text' ? 'text' : 'voice'
  } catch {
    return 'voice'
  }
}

const PREPARE_INTERVAL_MS = 4 * 60 * 1000 // 서버 준비분 만료(5분)보다 짧게
const COMPOSER_MAX_PX = 140 // 입력창은 내용만큼 늘다가 약 5줄에서 멈추고 안에서 스크롤한다

/** 페이지 맨 아래로 내린다. 아래 고정 패널(입력창·음성 버튼)은 맨 아래에서 제자리에 놓여 말풍선을 가리지 않는다 */
function scrollToBottom() {
  const page = document.scrollingElement
  page?.scrollTo?.({ top: page.scrollHeight })
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  )
}

function KeyboardIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="6" width="20" height="12" rx="2" />
      <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" />
    </svg>
  )
}

/** 시작 화면 위쪽의 오늘 날짜(예: 10월 18일 일요일) */
function today(): string {
  return new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'long' })
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor"
      strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  )
}

/** 음성 대화 중 글을 지금 보낼 수 없는 이유 */
function typingHint(machine: { name: string; connected: boolean; queued: number }): string {
  if (!machine.connected || machine.name === 'offline') return '연결되면 보낼 수 있어요.'
  if (machine.queued > 0) return '보관한 말을 보낸 뒤에 보낼 수 있어요.'
  if (machine.name === 'closing') return '대화를 정리하는 중이에요.'
  return '답변이 끝나면 보낼 수 있어요.'
}

/** 브라우저 탭이 보이는지(백그라운드 탭에서는 미리 준비 요청을 보내지 않는다) */
function usePageVisible(): boolean {
  const [shown, setShown] = useState(() => document.visibilityState !== 'hidden')
  useEffect(() => {
    const update = () => setShown(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])
  return shown
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '알 수 없는 오류가 났어요.'
}

function AssistantBubble({ message, name }: { message: AssistantMessage; name: string }) {
  const notices = message.tools
    .map((tool) => ({ id: tool.id, text: toolNotice(tool), done: tool.phase === 'end' }))
    .filter((n) => n.text !== null)
  const waiting = message.status === 'streaming' && message.sentences.length === 0
  const empty = message.sentences.length === 0 && notices.length === 0
  // 문장도 알림도 없이 끝난 답(쉬기·끝내기 도구만 쓴 경우)은 그리지 않는다
  if (empty && message.status === 'done') return null
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
      {message.status === 'error' && message.sentences.length === 0 && (
        <p className="bubble">답변을 받지 못했어요.</p>
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

function VoiceUnavailable() {
  return <p className="conversation-note">음성 기능을 불러오지 못했어요. 글로 대화하거나 새로 고침해 주세요.</p>
}

/** visible: 탭에서 지금 보이는지. 숨겨져 있어도 대화를 유지하려고 언마운트하지 않는다(App).
 * onOpenJournal: 끝난 대화의 일지 상세를 연다(App이 탭을 옮긴다).
 * ref: 일지 상세의 "이어서" 버튼이 이 화면으로 대화를 다시 연다(ConversationHandle). */
export function ConversationScreen({
  visible = true,
  onOpenJournal,
  ref,
}: {
  visible?: boolean
  onOpenJournal?: (sessionId: string) => void
  ref?: Ref<ConversationHandle>
}) {
  const [state, dispatch] = useReducer(conversationReducer, initialConversation)
  const [draft, setDraft] = useState('')
  const controller = useRef<AbortController | null>(null)
  const nextId = useRef(0)
  const input = useRef<HTMLTextAreaElement>(null)
  const pageVisible = usePageVisible()
  const [mode, setMode] = useState<Mode>(savedMode)
  const voice = useVoiceConversation(dispatch)
  // 음성 대화가 진행 중(상태 머신이 대기가 아님)이면 큰 버튼을 보인다
  const voiceActive = mode === 'voice' && voice.machine.name !== 'idle'

  const chooseMode = (next: Mode) => {
    setMode(next)
    try {
      localStorage.setItem(MODE_KEY, next)
    } catch {
      // 저장하지 못해도 이번 대화에는 지장이 없다
    }
  }

  // 화면을 떠나면 진행 중인 요청을 멈춘다(서버는 연결이 끊기면 CLI 턴을 정리한다)
  useEffect(() => () => controller.current?.abort(), [])

  // 대화 탭이 보이고 대화 시작 전·끝난 뒤이면 서버가 다음 대화의 CLI를 미리 띄워 두게 한다
  // (인사말 대기 단축). 서버는 쓰지 않으면 5분 뒤 닫으므로, 화면이 열려 있는 동안 4분마다 다시
  // 알린다(같은 조건이면 만료만 미룬다). 결과를 기다리지 않고 실패해도 무시한다.
  // 준비분은 대화 방식(글·음성)마다 다르므로 마지막으로 고른 방식으로 준비한다
  const waitingToStart =
    visible && pageVisible && !voiceActive && (state.status === 'idle' || state.status === 'ended')
  useEffect(() => {
    if (!waitingToStart) return
    const prepare = new AbortController()
    const ping = () => prepareSession(mode, prepare.signal).catch(() => {})
    void ping()
    const timer = setInterval(ping, PREPARE_INTERVAL_MS)
    return () => {
      clearInterval(timer)
      prepare.abort()
    }
  }, [waitingToStart, mode])

  // 새 말풍선·문장이 오면 아래로 내린다. 위로 올려 읽는 중이면 끌어내리지 않는다
  const stickToBottom = useRef(true)
  useEffect(() => {
    if (!visible) return // 다른 탭의 스크롤은 대화 위치와 상관없다
    const onScroll = () => {
      const { scrollY, innerHeight } = window
      stickToBottom.current = scrollY + innerHeight >= document.documentElement.scrollHeight - 120
    }
    // 휴대폰 키보드가 열리고 닫혀 화면 높이가 바뀌어도 바닥에 붙어 있었으면 그대로 둔다
    const onResize = () => stickToBottom.current && scrollToBottom()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.visualViewport?.addEventListener('resize', onResize)
    // 다시 보이면 숨겨진 동안 온 답변까지 바닥으로 내린다
    stickToBottom.current = true
    scrollToBottom()
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.visualViewport?.removeEventListener('resize', onResize)
    }
  }, [visible])
  useEffect(() => {
    if (visible && stickToBottom.current) scrollToBottom()
  }, [state.messages, visible])

  // 아래 고정 패널의 높이가 바뀌면(음성 시작, 안내 문구, 입력창이 늘어남) 바닥에 붙어 있던 화면을 다시 내린다
  const [dock, setDock] = useState<HTMLElement | null>(null)
  useEffect(() => {
    if (!dock || !visible || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => stickToBottom.current && scrollToBottom())
    observer.observe(dock)
    return () => observer.disconnect()
  }, [dock, visible])

  // 입력창은 한 줄에서 시작해 내용만큼 늘어난다(보내서 비면 다시 한 줄, 새로 그려져도 다시 잰다).
  // scrollHeight에는 테두리가 빠지므로 더한다(빼면 두 줄부터 안에서 스크롤된다)
  useLayoutEffect(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    const border = el.offsetHeight - el.clientHeight
    el.style.height = `${Math.min(el.scrollHeight + border, COMPOSER_MAX_PX)}px`
  }, [draft, state.status, mode, voiceActive])

  // 대화가 시작되면 바로 입력할 수 있게 입력창으로 포커스를 옮긴다
  const previousStatus = useRef(state.status)
  useEffect(() => {
    // 음성 대화에는 입력창이 있어도 옮기지 않는다(폰 키보드가 올라와 구슬을 가린다)
    if (previousStatus.current === 'starting' && state.status === 'active' && mode === 'text') input.current?.focus()
    previousStatus.current = state.status
  }, [state.status, mode])

  /** unsentId: 실패했을 때 서버가 받지 못한 사용자 메시지 id(목록에서 뺀다) */
  const run = async (
    task: (signal: AbortSignal) => Promise<void>,
    unsentId: () => string | undefined = () => undefined,
  ) => {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    try {
      await task(current.signal)
    } catch (error) {
      if (current.signal.aborted) return
      dispatch({
        type: 'failed',
        message: errorMessage(error),
        code: error instanceof ApiError ? error.code : undefined,
        unsentId: unsentId(),
      })
    }
  }

  // 다시 여는 중인 대화(S3-26). 응답이 오기 전(sessionId 없음)에 같은 대화를 또 눌러도 그 대화로 본다
  const reopening = useRef<string | null>(null)

  const startVoice = () => {
    reopening.current = null
    chooseMode('voice')
    stickToBottom.current = true
    voice.tap() // 버튼을 누른 동작 안에서 오디오를 연다
  }

  const start = () => {
    reopening.current = null
    chooseMode('text')
    void startText()
  }

  const startText = () =>
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

  const continueWith = (sessionId: string, next: Mode): ContinueResult => {
    const live =
      state.status === 'starting' ||
      state.status === 'active' ||
      state.status === 'paused' ||
      state.ending ||
      voice.machine.name !== 'idle'
    // 그 대화가 이미 진행 중(또는 다시 여는 중)이면 방식은 그대로 두고 화면만 옮긴다
    if (live) return (state.sessionId ?? reopening.current) === sessionId && !state.ending ? 'ok' : 'busy'
    if (next === 'voice') {
      if (voice.ready !== true) return voice.ready === null ? 'voice_loading' : 'voice_unavailable'
      if (!voice.resume(sessionId)) return 'busy'
      reopening.current = sessionId
      stickToBottom.current = true
      chooseMode('voice')
      return 'ok'
    }
    reopening.current = sessionId
    stickToBottom.current = true
    chooseMode('text')
    void run(async (signal) => {
      dispatch({ type: 'start' })
      const body = await reopenSession(sessionId, 'text', signal)
      dispatch({
        type: 'started',
        sessionId: body.session.id,
        personaName: body.persona.name,
        greeting: { turnId: body.greeting.turn_id, text: body.greeting.text },
        history: body.turns,
      })
    })
    return 'ok'
  }
  // 상세 화면의 버튼이 늘 지금 상태로 판단하도록 매번 새로 넘긴다
  useImperativeHandle(ref, () => ({ continueWith }))

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
    const id = `local-${nextId.current++}`
    dispatch({ type: 'send', id, text })
    let answered = false
    let endedByTool = false // 끝내기 도구로 대화가 끝났다(마무리 멘트를 받으러 끝내기를 부른다)
    void run(
      async (signal) => {
      try {
        await sendTurn(
          sessionId,
          text,
          (streamEvent) => {
            if (signal.aborted) return // 끝내기로 끊은 뒤 늦게 읽힌 이벤트
            if (streamEvent.type === 'turn') answered = true
            // 끝내기 도구 뒤 턴이 정상 또는 오류로 끝났다
            if (streamEvent.type === 'done' && streamEvent.session_status === 'ended') {
              endedByTool = true
            }
            if (streamEvent.type === 'error' && answered && streamEvent.code === 'session_ended') {
              endedByTool = true
            }
            if (streamEvent.type === 'error' && !answered) {
              // 서버가 사용자 메시지를 받기 전에 실패했다: 말풍선을 빼고 쓴 글을 되살린다
              setDraft((current) => current || text)
              dispatch({
                type: 'failed',
                message: streamEvent.message,
                code: streamEvent.code,
                unsentId: id,
              })
              return
            }
            dispatch({ type: 'event', event: streamEvent })
          },
          signal,
        )
      } catch (error) {
        // 서버가 받기 전에 실패했으면(네트워크·409 등) 쓴 글을 되살려 다시 보낼 수 있게 한다
        if (!answered && !signal.aborted) setDraft((current) => current || text)
        throw error
      }
      if (endedByTool) await finish(sessionId, signal)
      },
      () => (answered ? undefined : id),
    )
  }

  // 음성 대화 중 글로 보낸 말: 듣는 중(말하는 중이면 끼어든 뒤)에만 보낸다. 서버에 닿지 않으면 글을 돌려받는다
  const voiceCanType =
    voice.machine.connected &&
    voice.machine.queued === 0 &&
    (voice.machine.name === 'listening' || voice.machine.name === 'speaking' || voice.machine.name === 'paused')
  const sendVoiceText = (event?: FormEvent) => {
    event?.preventDefault()
    const text = draft.trim()
    if (!text || !voiceCanType) return
    stickToBottom.current = true
    if (voice.sendText(text, (unsent) => setDraft((current) => current || unsent))) setDraft('')
  }
  const submit = voiceActive ? sendVoiceText : send

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // 한글 조합 중 Enter는 글자 확정이므로 보내지 않는다(Safari는 isComposing 대신 keyCode 229)
    const composing = event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229
    // 터치 화면의 가상 키보드에는 Shift+Enter가 없으므로 Enter는 줄바꿈, 보내기는 버튼으로 한다
    const touch = window.matchMedia?.('(pointer: coarse)').matches ?? false
    if (event.key === 'Enter' && !event.shiftKey && !composing && !touch) {
      event.preventDefault()
      submit()
    }
  }

  /** 끝내기를 서버에 알리고 마무리 멘트를 받는다(일지 정리를 잠깐 기다린다). */
  const finish = async (sessionId: string, signal: AbortSignal) => {
    dispatch({ type: 'ending' })
    const closed = await endSession(sessionId, signal)
    dispatch({
      type: 'ended',
      closing: closed.closing,
      journalPending: closed.journal_status === 'pending',
    })
  }

  const end = () => {
    if (state.sessionId === null) return
    const sessionId = state.sessionId
    void run((signal) => finish(sessionId, signal))
  }

  // 메신저형 입력줄(자동 높이 입력창 + 둥근 보내기). 글 대화와 음성 대화가 같이 쓴다
  const composerRow = (locked: boolean) => (
    <div className="composer-row">
      <textarea
        ref={input}
        aria-label="메시지"
        value={draft}
        rows={1}
        maxLength={4000}
        placeholder={voiceActive ? '말 대신 글로 보내기' : '메시지를 입력하세요'}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <button type="submit" className="send-button" aria-label="보내기" disabled={locked || !draft.trim()}>
        <SendIcon />
      </button>
    </div>
  )

  const name = state.personaName ?? ''
  const inConversation = state.status === 'active' || state.status === 'paused'

  return (
    <section className="conversation">
      <h2 className="sr-only">대화</h2>
      {(state.status === 'idle' || state.status === 'starting') && !voiceActive && (
        <div className="conversation-start">
          <p className="conversation-date">{today()}</p>
          <p className="conversation-lead">
            걸으면서 떠오른 생각,
            <br />
            같이 이야기해 봐요.
          </p>
          <div className="start-actions">
            <button
              type="button"
              className="start-voice"
              onClick={startVoice}
              disabled={state.status === 'starting' || voice.ready !== true}
            >
              <span className="start-orb" aria-hidden="true">
                <MicIcon />
              </span>
              {voice.ready === null ? '음성 준비 중…' : '음성으로 대화'}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={start}
              disabled={state.status === 'starting'}
            >
              <KeyboardIcon />
              {state.status === 'starting' ? '연결하는 중…' : '글로 대화'}
            </button>
          </div>
          {voice.ready === false && <VoiceUnavailable />}
        </div>
      )}

      {/* 스크린리더가 첫 인사말부터 읽도록 목록은 비어 있어도 그려 둔다 */}
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
      </ol>

      {state.error && (
        <p className="conversation-error" role="alert">
          {state.error}
        </p>
      )}
      {/* 라이브 영역은 미리 그려 두고 글만 바꾼다(새로 넣은 영역은 스크린리더가 놓치기 쉽다) */}
      <p className="conversation-note" aria-live="polite" hidden={!state.ending}>
        {state.ending ? '오늘 대화를 일지로 정리하는 중이에요…' : ''}
      </p>
      {state.status === 'paused' && mode === 'text' && (
        <p className="conversation-note">쉬는 중이에요. 말을 걸면 다시 이어 가요. 30분 동안 말이 없으면 대화를 마쳐요.</p>
      )}

      {voiceActive && (
        <VoiceControls
          dockRef={setDock}
          state={voice.machine.name}
          connecting={state.status === 'starting'}
          queued={voice.machine.queued}
          connected={voice.machine.connected}
          onTap={voice.tap}
          onLongPress={voice.longPress}
        >
          {state.sessionId !== null && (
            <form className="voice-composer" onSubmit={sendVoiceText}>
              {composerRow(!voiceCanType)}
              {draft.trim() && !voiceCanType && <p className="voice-hint">{typingHint(voice.machine)}</p>}
            </form>
          )}
        </VoiceControls>
      )}

      {inConversation && mode === 'text' && (
        <form className="composer" onSubmit={send} ref={setDock}>
          <div className="composer-bar">
            {/* 답변을 기다리는 중에도 끝낼 수 있다(진행 중 요청은 끊고, 서버가 CLI 턴을 정리한다) */}
            <button type="button" className="secondary small" onClick={end} disabled={state.ending}>
              대화 끝내기
            </button>
          </div>
          {composerRow(!canSend)}
        </form>
      )}

      {state.status === 'ended' && !state.ending && !voiceActive && (
        <div className="conversation-start ended">
          <p className="conversation-note">대화가 끝났어요.</p>
          {state.journalPending && (
            <p className="conversation-note">일지는 아직 정리 중이에요. 잠시 뒤 일지에서 볼 수 있어요.</p>
          )}
          <div className="start-actions">
            <button type="button" className="start-voice" onClick={startVoice} disabled={voice.ready !== true}>
              <span className="start-orb" aria-hidden="true">
                <MicIcon />
              </span>
              음성으로 새 대화
            </button>
            <button type="button" className="secondary" onClick={start}>
              <KeyboardIcon />
              글로 새 대화
            </button>
            {onOpenJournal && state.sessionId && (
              <button
                type="button"
                className="secondary"
                onClick={() => onOpenJournal(state.sessionId!)}
              >
                일지 보기
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
