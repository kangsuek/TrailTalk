// 음성 대화 컨트롤러(계획서 S3-13, 클라이언트 규약 4절 "플랫폼이 지킬 것").
// 상태 머신(core/sessionMachine)에 이벤트를 넣고, 나온 명령을 마이크(AudioInput)·재생(AudioOutput)·
// 서버 API로 실행한다. 말풍선은 텍스트 대화와 같은 리듀서(core/conversation)로 그린다.
import {
  ApiError,
  cancelTurn,
  endSession,
  reportLatency,
  sendAudioTurn,
  startSession,
} from '../api/conversation'
import { getProfile } from '../api/profile'
import {
  DEFAULT_SESSION_CONFIG,
  DEFAULT_VAD_SETTINGS,
  initialSession,
  transition,
  vadSettingsFrom,
  type AudioInput,
  type AudioInputEvent,
  type AudioOutput,
  type AudioOutputEvent,
  type RecordedAudio,
  type SessionCommand,
  type SessionConfig,
  type SessionEvent,
  type SessionState,
  type VadSettings,
} from '../core'
import type { ConversationAction } from '../core/conversation'
import { lazyAudioInput, lazyAudioOutput } from './lazyPlatform'
import listenSound from '../../../shared/sounds/listen.mp3'
import offlineSound from '../../../shared/sounds/offline.mp3'
import savedSound from '../../../shared/sounds/saved.mp3'

export interface VoiceDeps {
  createInput: (settings: VadSettings, onEvent: (event: AudioInputEvent) => void) => AudioInput
  createOutput: (onEvent: (event: AudioOutputEvent) => void) => AudioOutput
  startSession: typeof startSession
  sendAudioTurn: typeof sendAudioTurn
  cancelTurn: typeof cancelTurn
  reportLatency: typeof reportLatency
  endSession: typeof endSession
  getProfile: typeof getProfile
  now: () => number // 지연 측정 시계(단조 ms, 말 끝 시각과 같은 기준)
}

const DEFAULT_DEPS: VoiceDeps = {
  createInput: lazyAudioInput,
  createOutput: (onEvent) =>
    lazyAudioOutput(onEvent, { listen: listenSound, saved: savedSound, offline: offlineSound }),
  startSession,
  sendAudioTurn,
  cancelTurn,
  reportLatency,
  endSession,
  getProfile,
  now: () => performance.now(),
}

// 서버가 보내지 않는(또는 메시지를 못 받은) 오류의 문구
// 세션이 서버에서 이미 끝났다는 오류(머신이 정리로 간다)
const SESSION_GONE = new Set(['session_ended', 'session_not_found'])

const ERROR_MESSAGES: Record<string, string> = {
  mic_denied: '마이크 권한이 없어요. 브라우저 설정에서 마이크를 허용한 뒤 다시 시작해 주세요.',
  mic_unavailable: '마이크를 쓸 수 없어요. HTTPS로 접속했는지, 마이크가 연결돼 있는지 확인해 주세요.',
  vad_failed: '음성 감지를 시작하지 못했어요. 글로 대화해 주세요.',
  no_speech: '말소리를 듣지 못했어요. 다시 말해 주세요.',
}

export interface VoiceController {
  /** 큰 버튼 한 번(시작·끼어들기·쉬기 재개). 사용자 동작 안에서 불러야 소리가 난다 */
  tap(): void
  /** 길게 누르기(종료) */
  longPress(): void
  dispose(): Promise<void>
}

export function createVoiceController({
  dispatch,
  onState,
  deps = {},
}: {
  dispatch: (action: ConversationAction) => void
  onState: (state: SessionState) => void
  deps?: Partial<VoiceDeps>
}): VoiceController {
  const d = { ...DEFAULT_DEPS, ...deps }
  let state = initialSession
  let config: SessionConfig = DEFAULT_SESSION_CONFIG
  let vad: VadSettings = DEFAULT_VAD_SETTINGS
  let input: AudioInput | null = null // 처음 마이크를 쓸 때 만든다(서버 설정값을 받은 뒤)
  let sessionId: string | null = null
  let startAbort: AbortController | null = null
  let turnAbort: AbortController | null = null
  let greetingTurn: string | null = null // 인사말 턴(문장 번호 없이 재생하므로 끼어들어도 자르지 않는다)
  let endAbort: AbortController | null = null
  let idleTimer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  const utterances = new Map<string, { audio: RecordedAudio; speechEndedAt: number }>()
  // 지연 측정(S3-07): 이번 턴의 말 끝·요청 시각. 첫 소리가 나면 한 번 보고한다
  // 소리 없이 끝난 턴(오류·합성 실패·문장 없음)이면 비운다(다른 소리에 붙지 않게)
  let measuring: {
    turnId: string | null
    speechEndedAt: number
    requestAt: number
    hasAudio: boolean // 이 턴의 소리를 대기열에 넣었다
  } | null = null
  let nextUtterance = 0
  const messages = new Map<string, string>() // 오류 코드 → 마지막으로 받은 문구
  // 대화가 끝난 이유(마이크 오류, 서버에서 세션이 끝남). 정리를 시작하면 오류 문구가 지워지므로
  // 정리가 끝난 뒤에 보인다
  let closingReason: string | null = null

  // 명령 실행 중에 이벤트가 또 생길 수 있어(같은 흐름) 차례로 처리한다
  const pending: SessionEvent[] = []
  let processing = false

  const send = (event: SessionEvent) => {
    if (disposed) return
    pending.push(event)
    if (processing) return
    processing = true
    try {
      while (pending.length > 0) {
        const next = pending.shift()!
        const previous = state
        const result = transition(state, next, config)
        state = result.state
        if (state !== previous) onState(state)
        // 정리 중 길게 누르기: 끝내기 응답을 기다리지 않고 대기로 간다(서버 끝내기는 멱등)
        if (previous.name === 'closing' && state.name === 'idle' && next.type === 'long_press') {
          endAbort?.abort()
          dispatch({ type: 'ended' })
          showClosingReason()
        }
        for (const command of result.commands) run(command)
      }
    } finally {
      processing = false
    }
  }

  const output = d.createOutput((event) => {
    if (event.type === 'started') return onPlaybackStarted(event.index === null)
    send(event)
  })

  // notice: 번호 없는 소리(턴 중에는 검색 안내 음성)로 시작했다
  const onPlaybackStarted = (notice: boolean) => {
    if (measuring === null || measuring.turnId === null || sessionId === null) return
    const { turnId, speechEndedAt, requestAt } = measuring
    measuring = null // 턴마다 한 번(검색 안내 음성이 먼저 나와도 캐릭터 목소리가 처음 나온 때다)
    const speechToRequest = Math.max(0, Math.round(requestAt - speechEndedAt))
    const requestToPlayback = Math.max(0, Math.round(d.now() - requestAt))
    void d
      .reportLatency(sessionId, turnId, speechToRequest, requestToPlayback, notice)
      .catch(() => {})
  }

  const remember = (error: unknown): string => {
    if (error instanceof ApiError) {
      messages.set(error.code, error.message)
      return error.code
    }
    return 'network_error'
  }

  const onInput = (event: AudioInputEvent) => {
    switch (event.type) {
      case 'speech_start':
        send({ type: 'speech_start' })
        return
      case 'speech_end': {
        const id = `u${nextUtterance++}`
        utterances.set(id, { audio: event.audio, speechEndedAt: event.speechEndedAt })
        send({ type: 'speech_end', utteranceId: id })
        utterances.delete(id) // 보냈으면 이미 꺼냈고, 머신이 버린 발화(처리 중)는 지운다
        return
      }
      case 'error':
        // 마이크 없이는 음성 대화를 이어 갈 수 없다: 끝내고 일지를 정리한다(이유는 정리 뒤에 보인다).
        // 이미 끝났거나 정리 중이면(늦게 온 오류) 무시한다
        if (state.name === 'idle' || state.name === 'closing') return
        closingReason = ERROR_MESSAGES[event.code]
        send({ type: 'long_press' })
        return
    }
  }

  const mic = () => (input ??= d.createInput(vad, onInput))

  const startConversation = async () => {
    const abort = new AbortController()
    startAbort = abort
    closingReason = null
    dispatch({ type: 'start' })
    try {
      // 서버 설정값(VAD)을 받은 뒤에 마이크를 만들도록 함께 기다린다(보통 먼저 끝나 있다)
      const [body] = await Promise.all([d.startSession('voice', abort.signal), profileLoaded])
      if (abort.signal.aborted || disposed) return
      sessionId = body.session.id
      greetingTurn = body.greeting.turn_id
      dispatch({
        type: 'started',
        sessionId: body.session.id,
        personaName: body.persona.name,
        greeting: { turnId: body.greeting.turn_id, text: body.greeting.text },
      })
      // 소리가 없어도 대기열을 거치면 바로 playback_idle이 온다
      output.enqueue({ audio: body.greeting.audio ?? null, index: null })
      send({ type: 'session_started', turnId: body.greeting.turn_id })
    } catch (error) {
      if (abort.signal.aborted || disposed) return
      send({ type: 'start_failed', code: remember(error) })
    } finally {
      if (startAbort === abort) startAbort = null
    }
  }

  const sendTurn = async (utteranceId: string) => {
    const utterance = utterances.get(utteranceId)
    utterances.delete(utteranceId)
    if (!utterance || sessionId === null) {
      send({ type: 'turn_error', turnId: null, code: 'audio_invalid' })
      return
    }
    const abort = new AbortController()
    turnAbort = abort
    const localId = `voice-${utteranceId}`
    let turnId: string | null = null
    measuring = {
      turnId: null,
      speechEndedAt: utterance.speechEndedAt,
      requestAt: d.now(),
      hasAudio: false,
    }
    const enqueueAudio = (audio: string | null | undefined, index: number | null) => {
      if (audio && measuring !== null) measuring.hasAudio = true
      output.enqueue({ audio: audio ?? null, index })
    }
    try {
      await d.sendAudioTurn(
        sessionId,
        utterance.audio,
        (event) => {
          if (abort.signal.aborted || disposed) return // 끼어들어 취소한 턴의 늦은 이벤트
          switch (event.type) {
            case 'transcript':
              dispatch({ type: 'send', id: localId, text: event.text })
              return
            case 'turn':
              turnId = event.turn_id
              if (measuring !== null) measuring.turnId = event.turn_id
              dispatch({ type: 'event', event })
              send({ type: 'turn', turnId: event.turn_id })
              return
            case 'sentence':
              dispatch({ type: 'event', event })
              // 소리를 대기열에 넣은 뒤 같은 흐름에서 머신에 알린다(규약 4절)
              enqueueAudio(event.audio, event.index)
              if (turnId) send({ type: 'sentence', turnId, index: event.index })
              return
            case 'tool':
              dispatch({ type: 'event', event })
              if (event.notice) enqueueAudio(event.notice.audio, null)
              if (event.name === 'save_note' && event.phase === 'end' && !event.is_error) {
                send({ type: 'note_saved' })
              }
              return
            case 'done':
              if (measuring !== null && !measuring.hasAudio) measuring = null // 들려줄 소리가 없다
              dispatch({ type: 'event', event })
              send({ type: 'turn_done', turnId: event.turn_id, sessionStatus: event.session_status })
              return
            case 'error':
              measuring = null
              messages.set(event.code, event.message)
              if (SESSION_GONE.has(event.code)) closingReason = event.message
              // 턴 전 오류는 서버가 말을 저장하지 않았다: 사용자 말풍선을 뺀다
              if (turnId === null) dispatch({ type: 'failed', message: event.message, code: event.code, unsentId: localId })
              else dispatch({ type: 'event', event })
              send({ type: 'turn_error', turnId, code: event.code })
              return
          }
        },
        abort.signal,
      )
    } catch (error) {
      if (abort.signal.aborted || disposed) return
      measuring = null
      // 네트워크 오류도 여기서 알리고 다시 듣는다(오프라인 보관은 S3-12에서 send_failed로)
      const code = remember(error)
      if (SESSION_GONE.has(code)) closingReason = messageOf(code)
      if (turnId === null) dispatch({ type: 'failed', message: messageOf(code), code, unsentId: localId })
      send({ type: 'turn_error', turnId, code })
    } finally {
      if (turnAbort === abort) turnAbort = null
    }
  }

  const endConversation = async () => {
    turnAbort?.abort()
    measuring = null // 마무리 멘트 소리는 재지 않는다
    if (sessionId === null) {
      // 시작 응답을 받기 전에 끝냈다
      startAbort?.abort()
      dispatch({ type: 'failed', message: '대화를 시작하지 않았어요.' })
      send({ type: 'session_closed' })
      return
    }
    const abort = new AbortController()
    endAbort = abort
    dispatch({ type: 'ending' })
    try {
      const closed = await d.endSession(sessionId, abort.signal)
      if (abort.signal.aborted || disposed) return
      dispatch({
        type: 'ended',
        closing: closed.closing,
        journalPending: closed.journal_status === 'pending',
      })
      showClosingReason()
      output.enqueue({ audio: closed.closing_audio ?? null, index: null })
      send({ type: 'session_closed' })
    } catch (error) {
      if (abort.signal.aborted || disposed) return
      const code = remember(error)
      dispatch({ type: 'ended' }) // 서버 끝내기는 멱등이고 무발화 감시가 정리한다
      showClosingReason()
      send({ type: 'end_failed', code })
    } finally {
      if (endAbort === abort) endAbort = null
    }
  }

  const showClosingReason = () => {
    if (closingReason) dispatch({ type: 'failed', message: closingReason })
    closingReason = null
  }

  const messageOf = (code: string) => messages.get(code) ?? ERROR_MESSAGES[code] ?? '문제가 생겼어요.'

  const run = (command: SessionCommand) => {
    switch (command.type) {
      case 'startSession':
        sessionId = null
        void startConversation()
        return
      case 'sendTurn':
        void sendTurn(command.utteranceId)
        return
      case 'cancelTurn':
        // 받는 중이면 연결을 끊고(늦은 이벤트를 버린다), 서버에 들려준 문장까지만 남기게 한다.
        // 기다리지 않고 실패는 무시한다(연결이 끊긴 것만으로도 보낸 문장까지는 끊긴 답변으로 남는다)
        turnAbort?.abort()
        turnAbort = null
        measuring = null // 끊은 턴은 재지 않는다
        if (sessionId !== null) {
          void d.cancelTurn(sessionId, command.turnId, command.lastPlayed).catch(() => {})
        }
        if (command.turnId !== greetingTurn) {
          dispatch({ type: 'interrupt', turnId: command.turnId, keep: command.lastPlayed + 1 })
        }
        return
      case 'endSession':
        void endConversation()
        return
      case 'micOn':
        void mic().start()
        return
      case 'micOff':
        void input?.stop()
        return
      case 'setVadMode':
        mic().setMode(command.mode)
        return
      case 'stopPlayback':
        output.stop()
        return
      case 'playSound':
        output.playEffect(command.name)
        return
      case 'notifyError':
        dispatch({ type: 'failed', message: messageOf(command.code), code: command.code })
        return
      case 'startIdleTimer':
        clearTimeout(idleTimer)
        idleTimer = setTimeout(() => send({ type: 'idle_timeout' }), command.minutes * 60_000)
        return
      case 'clearIdleTimer':
        clearTimeout(idleTimer)
        return
      // 오프라인 보관(queueUtterance·speakOfflineNotice·flushQueue)은 S3-12에서 연결한다.
      // 지금은 send_failed를 보내지 않으므로 이 명령들은 나오지 않는다
      default:
        return
    }
  }

  // 서버 설정값(VAD·무발화 시간). 받기 전·실패하면 공유 기본값을 쓴다
  const profileLoaded = d
    .getProfile()
    .then((profile) => {
      vad = vadSettingsFrom(profile.client.vad)
      config = { idleTimeoutMinutes: profile.client.session.idle_timeout_minutes }
    })
    .catch(() => {})

  return {
    tap() {
      void output.unlock()
      send({ type: 'tap' })
    },
    longPress() {
      send({ type: 'long_press' })
    },
    async dispose() {
      disposed = true
      startAbort?.abort()
      turnAbort?.abort()
      endAbort?.abort()
      clearTimeout(idleTimer)
      await Promise.all([input?.dispose(), output.dispose()])
    },
  }
}
