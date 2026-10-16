// 음성 대화 컨트롤러(계획서 S3-13, 클라이언트 규약 4절 "플랫폼이 지킬 것").
// 상태 머신(core/sessionMachine)에 이벤트를 넣고, 나온 명령을 마이크(AudioInput)·재생(AudioOutput)·
// 서버 API로 실행한다. 말풍선은 텍스트 대화와 같은 리듀서(core/conversation)로 그린다.
import {
  ApiError,
  cancelTurn,
  endSession,
  recordAudioTurn,
  reportLatency,
  sendAudioTurn,
  startSession,
} from '../api/conversation'
import { fetchHealth } from '../api/health'
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
  type LocalQueue,
  type QueuedUtterance,
  type RecordedAudio,
  type SessionCommand,
  type SessionConfig,
  type SessionEvent,
  type SessionState,
  type VadSettings,
} from '../core'
import type { ConversationAction } from '../core/conversation'
import { createLocalQueue } from '../platform/localQueue'
import clientDefaults from '../../../shared/client-defaults.json'
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
  // 오프라인 보관(S3-12)
  queue: LocalQueue
  recordAudioTurn: typeof recordAudioTurn // 대답 없이 기록만 남기기(대답할 수 없는 말)
  speak: (text: string) => Promise<void> // 기기 TTS로 오프라인 안내를 읽는다(끝나면 resolve)
  watchOnline: (onOnline: () => void) => () => void // 연결이 돌아오면 부른다. 해제 함수를 돌려준다
  checkHealth: () => Promise<boolean> // 서버에 닿는지(30초 재시도 전에 확인한다)
  cancelSpeech: () => void // 읽던 오프라인 안내를 멈춘다
}

const NOTICE_TIMEOUT_MS = 6000 // 기기 TTS가 끝 알림을 주지 않을 때의 상한
const RETRY_MS = 30_000 // 연결이 끊긴 동안 다시 시도하는 간격(서버만 안 닿는 경우 online 이벤트가 없다)
// 턴이 시작되기(인식 결과가 오기) 전까지 기다리는 시간. 넘으면 서버에 닿지 않은 것으로 본다
const PRE_TURN_TIMEOUT_MS = 30_000
const MAX_ATTEMPTS = 5 // 보관한 말을 서버 오류로 보내지 못한 횟수 상한(넘으면 기록만 남긴다)
const QUEUE_TTL_MS = 30 * 24 * 60 * 60 * 1000 // 보관한 녹음을 두는 최대 기간(음성 원본 보관과 같다)

// 남은 말 기록은 화면에 컨트롤러가 둘 생겨도(재마운트) 하나씩 돌린다
let flushChain: Promise<void> = Promise.resolve()

/** 브라우저 speechSynthesis로 읽는다. 없거나 실패하거나 너무 오래 걸리면 그냥 끝낸다 */
function speakWithSynthesis(text: string): Promise<void> {
  return new Promise((resolve) => {
    const synth = typeof speechSynthesis === 'undefined' ? null : speechSynthesis
    if (synth === null || typeof SpeechSynthesisUtterance === 'undefined') return resolve()
    const timer = setTimeout(resolve, NOTICE_TIMEOUT_MS)
    const done = () => {
      clearTimeout(timer)
      resolve()
    }
    try {
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = 'ko-KR'
      utterance.onend = done
      utterance.onerror = done
      synth.speak(utterance)
    } catch {
      done()
    }
  })
}

function watchBrowserOnline(onOnline: () => void): () => void {
  window.addEventListener('online', onOnline)
  return () => window.removeEventListener('online', onOnline)
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
  queue: createLocalQueue(),
  recordAudioTurn,
  speak: speakWithSynthesis,
  watchOnline: watchBrowserOnline,
  checkHealth: () => fetchHealth().catch(() => false),
  cancelSpeech: () => {
    if (typeof speechSynthesis !== 'undefined') speechSynthesis.cancel()
  },
}

// 서버가 보내지 않는(또는 메시지를 못 받은) 오류의 문구
// 세션이 서버에서 이미 끝났다는 오류(머신이 정리로 간다)
const SESSION_GONE = new Set(['session_ended', 'session_not_found'])
// 서버에 닿지 않은 실패(턴 시작 전): 보관했다가 연결되면 다시 보낸다
const UNREACHABLE = new Set(['network_error', 'stream_closed'])
// 다시 보내도 소용없는 말(말소리 없음·형식 오류): 보관하지 않고 버린다
const UNUSABLE = new Set(['no_speech', 'audio_invalid'])

const ERROR_MESSAGES: Record<string, string> = {
  mic_denied: '마이크 권한이 없어요. 브라우저 설정에서 마이크를 허용한 뒤 다시 시작해 주세요.',
  mic_unavailable: '마이크를 쓸 수 없어요. HTTPS로 접속했는지, 마이크가 연결돼 있는지 확인해 주세요.',
  vad_failed: '음성 감지를 시작하지 못했어요. 글로 대화해 주세요.',
  no_speech: '말소리를 듣지 못했어요. 다시 말해 주세요.',
  queue_empty: '', // 보관한 말이 이미 없다(알리지 않는다)
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
  const failed = new Map<string, RecordedAudio>() // 서버에 닿지 않아 보관할 말(send_failed → queueUtterance)
  let offlineNotice = clientDefaults.offline_notice
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
        if (previous.name !== 'idle' && state.name === 'idle') {
          // 대화가 끝났다(정상·끝내기 실패·시작 실패): 이 대화에 남은 말은 이제 대답할 수 없으므로
          // 기록만 남긴다(연결이 없으면 다음에)
          sessionId = null
          void flushOthers(null)
        }
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

  /** 대답할 수 없는 말(서버가 대화를 끝냄)을 기록만 남긴다. 서버에 닿지 않으면 보관해 두고
   * 나중에(연결된 뒤·다음 대화 때) 다시 기록한다(유실 0건, NFR-04) */
  const preserve = async (sid: string, audio: { bytes: Uint8Array<ArrayBuffer>; mimeType: string }) => {
    try {
      await d.recordAudioTurn(sid, audio)
    } catch (error) {
      const code = remember(error)
      // 말소리가 없거나 대화가 아예 없으면 남길 곳이 없다. 그 밖(연결·서버 오류)은 보관해 두고 다시 기록한다
      if (!UNUSABLE.has(code) && code !== 'session_not_found') await keepForLater(sid, audio)
    }
  }

  let queuedCount = 0
  const keepForLater = (sid: string, audio: { bytes: Uint8Array<ArrayBuffer>; mimeType: string }) =>
    d.queue.add({
      id: `${Date.now()}-${String(queuedCount++).padStart(6, '0')}`, // 같은 ms 안에서도 순서대로
      sessionId: sid,
      mimeType: audio.mimeType,
      bytes: audio.bytes,
      createdAt: Date.now(),
      attempts: 0,
    })

  // 보낼 말: 방금 한 말(utteranceId, 지연 측정) 또는 큐에 보관한 말
  type TurnSource =
    | { kind: 'new'; utteranceId: string; audio: RecordedAudio; speechEndedAt: number }
    | { kind: 'queued'; item: QueuedUtterance }

  const sendTurn = (utteranceId: string) => {
    const utterance = utterances.get(utteranceId)
    utterances.delete(utteranceId)
    if (!utterance || sessionId === null) {
      send({ type: 'turn_error', turnId: null, code: 'audio_invalid' })
      return
    }
    void runTurn({ kind: 'new', utteranceId, ...utterance })
  }

  let removing: Promise<unknown> = Promise.resolve() // 서버가 받은 큐 항목 지우기(다음 전송 전에 끝낸다)
  const sendQueued = async () => {
    const sid = sessionId
    let item: QueuedUtterance | null
    try {
      await removing
      item = sid === null ? null : await d.queue.oldest(sid)
    } catch {
      if (!disposed) send({ type: 'queue_send_failed' }) // 보관함을 읽지 못했다: 나중에 다시
      return
    }
    if (disposed) return
    if (item === null) {
      // 보관한 말이 이미 없다(세는 값이 어긋났다): 머신을 처리 중에서 꺼낸다(알리지 않음)
      send({ type: 'queue_sent', remaining: 0 })
      send({ type: 'turn_error', turnId: null, code: 'queue_empty' })
      return
    }
    void runTurn({ kind: 'queued', item })
  }

  /** 큐의 말을 서버가 받았다: 남은 수를 바로 줄여 알리고(다음 전송 판단이 늦지 않게), 큐에서 지운다 */
  const dequeue = (id: string) => {
    send({ type: 'queue_sent', remaining: Math.max(state.queued - 1, 0) })
    removing = removing
      .then(() => d.queue.remove(id))
      .catch((error) => console.warn('보관한 말을 지우지 못했습니다', error))
    return removing
  }

  const runTurn = async (source: TurnSource) => {
    const sid = sessionId
    if (sid === null) return
    const queued = source.kind === 'queued' ? source.item : null
    const audio: RecordedAudio =
      queued === null
        ? (source as Extract<TurnSource, { kind: 'new' }>).audio
        : { bytes: queued.bytes, mimeType: queued.mimeType, durationMs: 0 }
    const abort = new AbortController()
    turnAbort = abort
    const localId =
      queued === null ? `voice-${(source as Extract<TurnSource, { kind: 'new' }>).utteranceId}` : `voice-q-${queued.id}`
    let turnId: string | null = null
    let timedOut = false
    // 서버가 받지도 거절하지도 않고 붙잡혀 있으면(서버만 닿지 않음) 닿지 않은 것으로 본다
    const preTurnTimer = setTimeout(() => {
      timedOut = true
      abort.abort()
    }, PRE_TURN_TIMEOUT_MS)
    // 지연은 방금 한 말만 잰다(보관한 말은 말 끝 시각이 의미 없다)
    measuring =
      source.kind === 'new'
        ? { turnId: null, speechEndedAt: source.speechEndedAt, requestAt: d.now(), hasAudio: false }
        : null
    const enqueueAudio = (sound: string | null | undefined, index: number | null) => {
      if (sound && measuring !== null) measuring.hasAudio = true
      output.enqueue({ audio: sound ?? null, index })
    }

    /** 턴이 시작되기 전에 실패했다(서버가 말을 받지 않았다). 저장소 오류에도 이벤트는 꼭 보낸다 */
    const failedBeforeTurn = async (code: string, message: string | null) => {
      const quietly = (work: Promise<unknown>) => work.catch((error) => console.warn('보관함 오류', error))
      if (UNREACHABLE.has(code)) {
        // 서버에 닿지 않았다: 보관했다가 연결되면 다시 보낸다
        if (queued === null) {
          failed.set((source as Extract<TurnSource, { kind: 'new' }>).utteranceId, audio)
          send({ type: 'send_failed', utteranceId: (source as Extract<TurnSource, { kind: 'new' }>).utteranceId })
        } else {
          await quietly(d.queue.update(queued.id, { attempts: queued.attempts + 1 }))
          send({ type: 'queue_send_failed' })
        }
        return
      }
      if (SESSION_GONE.has(code)) {
        // 서버가 대화를 끝냈다: 대답은 못 하지만 기록은 남긴다
        closingReason = message ?? messageOf(code)
        await preserve(sid, audio)
        if (queued !== null) await quietly(d.queue.remove(queued.id))
      } else if (queued !== null) {
        if (!UNUSABLE.has(code) && queued.attempts + 1 < MAX_ATTEMPTS) {
          // 서버 쪽 일시 오류일 수 있다: 남겨 두고 나중에 다시 보낸다(바로 다시 보내면 되풀이된다)
          await quietly(d.queue.update(queued.id, { attempts: queued.attempts + 1 }))
          send({ type: 'queue_send_failed' })
          return
        }
        if (UNUSABLE.has(code)) {
          await quietly(dequeue(queued.id)) // 쓸 수 없는 말은 버린다
        } else {
          // 계속 실패하는 말은 대답을 포기하고 기록만 남긴다(뒤의 말을 막지 않게). 보통 전송에서 빼고
          // 기록 경로로 넘긴다(기록도 실패하면 거기서 다시 시도한다)
          send({ type: 'queue_sent', remaining: Math.max(state.queued - 1, 0) })
          await quietly(d.queue.update(queued.id, { recordOnly: true }))
          void flushOthers(sid)
        }
      }
      dispatch({ type: 'failed', message: message ?? messageOf(code), code, unsentId: localId })
      send({ type: 'turn_error', turnId: null, code })
    }

    try {
      await d.sendAudioTurn(
        sid,
        audio,
        (event) => {
          if (abort.signal.aborted || disposed) return // 끼어들어 취소한 턴의 늦은 이벤트
          clearTimeout(preTurnTimer) // 서버가 받았다(인식 결과나 오류가 왔다)
          switch (event.type) {
            case 'transcript':
              dispatch({ type: 'send', id: localId, text: event.text })
              return
            case 'turn':
              turnId = event.turn_id
              if (measuring !== null) measuring.turnId = event.turn_id
              if (queued !== null) void dequeue(queued.id) // 서버가 받았다
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
              if (turnId === null) {
                void failedBeforeTurn(event.code, event.message)
                return
              }
              if (SESSION_GONE.has(event.code)) closingReason = event.message
              dispatch({ type: 'event', event })
              send({ type: 'turn_error', turnId, code: event.code })
              return
          }
        },
        abort.signal,
      )
    } catch (error) {
      if (disposed) return
      if (abort.signal.aborted && !timedOut) {
        // 끝내기로 끊었다: 서버가 받기 전이면 이 말을 보관해 기록만 남기게 한다(큐의 말은 그대로 남아 있다)
        if (turnId === null && source.kind === 'new') {
          void keepForLater(sid, audio).catch((e) => console.warn('보관함 오류', e))
        }
        return
      }
      measuring = null
      const code = timedOut ? 'network_error' : remember(error)
      if (turnId === null) return void (await failedBeforeTurn(code, null))
      if (SESSION_GONE.has(code)) closingReason = messageOf(code)
      send({ type: 'turn_error', turnId, code })
    } finally {
      clearTimeout(preTurnTimer)
      if (turnAbort === abort) turnAbort = null
    }
  }

  /** 이전 대화의 남은 말(새로 고침·끝난 대화)은 대답 없이 기록만 남긴다. 기한(30일)이 지났거나
   * 계속 실패하는 말은 버린다(녹음을 기기에 끝없이 두지 않게) */
  const flushOthers = (exclude: string | null) => {
    flushChain = flushChain.then(async () => {
      try {
        for (const item of await d.queue.others(exclude)) {
          if (disposed) return
          if (Date.now() - item.createdAt > QUEUE_TTL_MS) {
            await d.queue.remove(item.id)
            continue
          }
          try {
            await d.recordAudioTurn(item.sessionId, item)
            await d.queue.remove(item.id)
          } catch (error) {
            const code = remember(error)
            // 아직 연결이 없거나 그 대화의 턴이 진행 중이다(일시적): 세지 않고 다음 차례에
            if (UNREACHABLE.has(code) || code === 'turn_in_progress') return
            // 기록 실패는 전송 실패와 따로 센다. 5번 넘게 실패하거나 30일이 지난 말은 버린다(NFR-04의 예외)
            const tries = (item.recordAttempts ?? 0) + 1
            const hopeless = UNUSABLE.has(code) || code === 'session_not_found'
            if (hopeless || tries >= MAX_ATTEMPTS) await d.queue.remove(item.id)
            else await d.queue.update(item.id, { recordAttempts: tries })
          }
        }
      } catch (error) {
        console.warn('보관한 말을 기록하지 못했습니다', error) // 다음 차례에 다시
      }
    })
    return flushChain
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
        d.cancelSpeech() // 오프라인 안내를 읽던 중이면 멈춘다
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
      case 'queueUtterance': {
        // 보관할 말: 서버에 닿지 않은 말(failed) 또는 큐가 남아 있는 동안 한 새 말(utterances)
        const audio = failed.get(command.utteranceId) ?? utterances.get(command.utteranceId)?.audio
        failed.delete(command.utteranceId)
        if (audio && sessionId !== null) {
          void keepForLater(sessionId, audio).catch((e) => console.warn('보관함 오류', e))
        }
        return
      }
      case 'sendQueued':
        void sendQueued()
        return
      case 'speakOfflineNotice':
        void d.speak(offlineNotice).then(() => send({ type: 'offline_notice_done' }))
        return
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
      offlineNotice = profile.client.offline_notice
    })
    .catch(() => {})

  // 연결이 돌아오면 보관한 말을 보낸다. 서버만 안 닿는 경우는 online 이벤트가 없어 주기적으로 시도한다
  const unwatch = d.watchOnline(() => {
    send({ type: 'online' })
    void flushOthers(sessionId)
  })
  // 서버에 닿는지 먼저 확인한다(헛되이 처리 중에 들어가 효과음·무발화 타이머가 되풀이되지 않게)
  const retry = setInterval(() => {
    if (state.connected || state.queued === 0) return
    void d.checkHealth().then((ok) => {
      if (ok && !state.connected) send({ type: 'online' })
    })
  }, RETRY_MS)
  void flushOthers(null) // 지난번(새로 고치기 전)에 남은 말

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
      clearInterval(retry)
      unwatch()
      d.cancelSpeech()
      await Promise.all([input?.dispose(), output.dispose()])
    },
  }
}
