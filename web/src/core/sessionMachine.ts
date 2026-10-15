// 음성 대화 세션 상태 머신(설계서 4.1, 계획서 S3-08, 클라이언트 규약 4절).
// 이벤트를 받아 다음 상태와 "명령"을 돌려주는 순수 함수다. 마이크·재생·서버 호출·타이머는 직접 하지 않고
// 명령으로 내보내며, 화면·플랫폼 계층(AudioInput·AudioOutput·LocalQueue)이 실행한다.
// UI·브라우저 API에 의존하지 않는다(안드로이드 Kotlin 포팅 대상). 전이 표는 shared/fixtures/transitions.json.

import clientDefaults from '../../../shared/client-defaults.json'

/** 대기·듣기·처리 중·말하기·쉬기·오프라인 보관·정리 */
export type SessionStateName =
  | 'idle'
  | 'listening'
  | 'processing'
  | 'speaking'
  | 'paused'
  | 'offline'
  | 'closing'

export type EndStatus = 'active' | 'paused' | 'ended'

export interface SessionState {
  name: SessionStateName
  turnId: string | null // 지금 답변 턴(끼어들기 cancel 대상)
  lastPlayed: number // 마지막으로 재생을 끝낸 문장 번호(-1: 아직 없음)
  turnFinished: boolean // 이번 턴의 done을 받았다
  playbackIdle: boolean // 받은 문장을 다 재생했다(done이 재생보다 늦게 와도 바로 넘어가게)
  endStatus: EndStatus // done이 알려 준 세션 상태(재생이 끝나면 이 상태로 간다)
  queued: number // 오프라인 큐에 남은 발화 수
}

export type SessionEvent =
  | { type: 'tap' }
  | { type: 'long_press' }
  // 인사말 턴. 인사말은 SSE가 아니라 시작 응답으로 오므로 플랫폼이 재생을 시작하며 보낸다
  // (재생할 소리가 없으면 바로 playback_idle을 보낸다)
  | { type: 'session_started'; turnId: string }
  | { type: 'start_failed'; code: string }
  | { type: 'speech_start' }
  | { type: 'speech_end'; utteranceId: string }
  | { type: 'turn'; turnId: string }
  // 턴 ID가 지금 턴과 다르면(취소한 턴의 늦은 이벤트) 무시한다
  | { type: 'sentence'; turnId: string; index: number }
  | { type: 'turn_done'; turnId: string; sessionStatus: EndStatus }
  // turnId: turn 이벤트 뒤의 오류면 그 턴 ID, 턴 시작 전 오류(요청 실패 등)면 null
  | { type: 'turn_error'; turnId: string | null; code: string }
  | { type: 'note_saved' }
  | { type: 'sentence_played'; index: number }
  | { type: 'playback_idle' }
  | { type: 'send_failed'; utteranceId: string }
  | { type: 'offline_notice_done' }
  | { type: 'online' }
  | { type: 'queue_flushed'; remaining: number } // 큐 비우기가 끝났다(remaining: 아직 남은 발화 수)
  | { type: 'idle_timeout' }
  | { type: 'session_closed' }
  | { type: 'end_failed'; code: string }

export type SessionCommand =
  | { type: 'startSession' }
  | { type: 'sendTurn'; utteranceId: string }
  | { type: 'cancelTurn'; turnId: string; lastPlayed: number }
  | { type: 'endSession' }
  | { type: 'micOn' }
  | { type: 'micOff' }
  | { type: 'setVadMode'; mode: 'normal' | 'playback' } // 재생 중에는 VAD 임계값을 올린다
  | { type: 'stopPlayback' }
  | { type: 'queueUtterance'; utteranceId: string }
  | { type: 'speakOfflineNotice' }
  | { type: 'flushQueue' }
  | { type: 'playSound'; name: 'listen' | 'saved' | 'offline' }
  | { type: 'notifyError'; code: string }
  | { type: 'startIdleTimer'; minutes: number }
  | { type: 'clearIdleTimer' }

export interface SessionConfig {
  // 마지막 발화 뒤 이 시간 동안 말이 없으면(쉬는 중 포함) 대화를 끝낸다. 서버 안전망과 같은 값
  idleTimeoutMinutes: number
}

// 프로필을 받기 전 대체값(shared/client-defaults.json). 실제 값은 /api/profile의 client.session이다
export const DEFAULT_SESSION_CONFIG: SessionConfig = {
  idleTimeoutMinutes: clientDefaults.session.idle_timeout_minutes,
}

export interface Transition {
  state: SessionState
  commands: SessionCommand[]
}

export const initialSession: SessionState = {
  name: 'idle',
  turnId: null,
  lastPlayed: -1,
  turnFinished: false,
  playbackIdle: true,
  endStatus: 'active',
  queued: 0,
}

// 세션이 서버에서 이미 끝났다는 오류(규약 2절: 클라이언트는 끝난 상태로 간다)
const SESSION_GONE = new Set(['session_ended', 'session_not_found'])

const NEW_TURN = {
  turnId: null,
  lastPlayed: -1,
  turnFinished: false,
  playbackIdle: true,
  endStatus: 'active',
} as const

function enterListening(state: SessionState, config: SessionConfig, commands: SessionCommand[]): Transition {
  return {
    state: { ...state, ...NEW_TURN, name: 'listening' },
    commands: [
      ...commands,
      { type: 'micOn' },
      { type: 'setVadMode', mode: 'normal' },
      { type: 'playSound', name: 'listen' },
      { type: 'startIdleTimer', minutes: config.idleTimeoutMinutes },
    ],
  }
}

function enterPaused(state: SessionState, config: SessionConfig): Transition {
  return {
    state: { ...state, ...NEW_TURN, name: 'paused' },
    commands: [{ type: 'micOff' }, { type: 'startIdleTimer', minutes: config.idleTimeoutMinutes }],
  }
}

function enterClosing(state: SessionState, commands: SessionCommand[]): Transition {
  return {
    state: { ...state, ...NEW_TURN, name: 'closing' },
    commands: [...commands, { type: 'micOff' }, { type: 'clearIdleTimer' }, { type: 'endSession' }],
  }
}

/** 턴이 끝나고 들려줄 것도 다 들려줬다: done의 세션 상태로 간다(쉬기·끝내기 도구 반영). */
function finishTurn(state: SessionState, config: SessionConfig): Transition {
  if (state.endStatus === 'paused') return enterPaused(state, config)
  if (state.endStatus === 'ended') return enterClosing(state, [])
  return enterListening(state, config, [])
}

/** 진행 중인 답변을 멈추는 명령(끼어들기·종료). 들려준 문장까지만 기록하도록 마지막 재생 번호를 보낸다. */
function cancelCurrent(state: SessionState): SessionCommand[] {
  return state.turnId === null ? [] : [{ type: 'cancelTurn', turnId: state.turnId, lastPlayed: state.lastPlayed }]
}

const unchanged = (state: SessionState): Transition => ({ state, commands: [] })

/** 상태에 이벤트를 적용한다. 표에 없는 조합은 상태도 명령도 바꾸지 않는다. */
export function transition(
  state: SessionState,
  event: SessionEvent,
  config: SessionConfig = DEFAULT_SESSION_CONFIG,
): Transition {
  // 어느 상태에서나 같은 이벤트
  switch (event.type) {
    case 'online':
      return { state, commands: state.queued > 0 ? [{ type: 'flushQueue' }] : [] }
    case 'queue_flushed':
      return { state: { ...state, queued: Math.max(event.remaining, 0) }, commands: [] }
    case 'note_saved':
      return state.name === 'idle' ? unchanged(state) : { state, commands: [{ type: 'playSound', name: 'saved' }] }
    case 'long_press':
      if (state.name === 'idle') return unchanged(state)
      // 끝내기 응답이 오지 않아 정리에서 멈췄을 때의 탈출구(서버 끝내기는 멱등이고 무발화 감시가 정리한다)
      if (state.name === 'closing') return { state: { ...initialSession, queued: state.queued }, commands: [] }
      return enterClosing(state, [
        ...(state.name === 'speaking' || state.name === 'offline' ? [{ type: 'stopPlayback' } as const] : []),
        ...cancelCurrent(state),
      ])
  }

  switch (state.name) {
    case 'idle':
      if (event.type === 'tap') {
        return { state: { ...initialSession, queued: state.queued, name: 'processing' }, commands: [{ type: 'startSession' }] }
      }
      return unchanged(state)

    case 'listening':
      if (event.type === 'speech_end') {
        if (state.queued > 0) {
          // 앞선 발화가 큐에 남아 있으면 순서를 지키려고 이 발화도 큐 뒤에 넣는다
          return {
            state: { ...state, queued: state.queued + 1 },
            commands: [
              { type: 'queueUtterance', utteranceId: event.utteranceId },
              { type: 'flushQueue' },
              { type: 'startIdleTimer', minutes: config.idleTimeoutMinutes },
            ],
          }
        }
        return {
          state: { ...state, ...NEW_TURN, name: 'processing' },
          commands: [{ type: 'clearIdleTimer' }, { type: 'sendTurn', utteranceId: event.utteranceId }],
        }
      }
      if (event.type === 'idle_timeout') return enterClosing(state, [])
      return unchanged(state)

    case 'processing':
      switch (event.type) {
        case 'session_started':
          // 인사말 재생 시작. 인사말은 이미 끝난 턴이다
          return {
            state: { ...state, ...NEW_TURN, name: 'speaking', turnId: event.turnId, turnFinished: true, playbackIdle: false },
            commands: [{ type: 'setVadMode', mode: 'playback' }],
          }
        case 'start_failed':
          return { state: { ...initialSession, queued: state.queued }, commands: [{ type: 'notifyError', code: event.code }] }
        case 'turn':
          return { state: { ...state, ...NEW_TURN, turnId: event.turnId }, commands: [] }
        case 'sentence':
          if (event.turnId !== state.turnId) return unchanged(state)
          return {
            state: { ...state, name: 'speaking', playbackIdle: false },
            commands: [{ type: 'setVadMode', mode: 'playback' }],
          }
        case 'turn_done':
          if (event.turnId !== state.turnId) return unchanged(state)
          // 들려줄 문장 없이 끝났다(쉬기·끝내기 도구만 쓴 답 등)
          return finishTurn({ ...state, turnFinished: true, endStatus: event.sessionStatus }, config)
        case 'turn_error':
          if (event.turnId !== null && event.turnId !== state.turnId) return unchanged(state)
          return failTurn(state, event.code, config, [])
        case 'send_failed':
          return {
            state: { ...state, ...NEW_TURN, name: 'offline', queued: state.queued + 1 },
            commands: [
              { type: 'queueUtterance', utteranceId: event.utteranceId },
              // 안내 음성을 발화로 잡지 않게 재생 중 임계값을 쓴다
              { type: 'setVadMode', mode: 'playback' },
              { type: 'playSound', name: 'offline' },
              { type: 'speakOfflineNotice' },
            ],
          }
        case 'tap':
          // 답변을 기다리는 중 버튼: 이번 답변을 취소하고 다시 듣는다(턴 시작 전이면 기다린다)
          if (state.turnId === null) return unchanged(state)
          return enterListening(state, config, cancelCurrent(state))
        default:
          return unchanged(state)
      }

    case 'speaking':
      switch (event.type) {
        case 'sentence_played':
          return { state: { ...state, lastPlayed: Math.max(state.lastPlayed, event.index) }, commands: [] }
        case 'sentence':
          if (event.turnId !== state.turnId) return unchanged(state)
          return { state: { ...state, playbackIdle: false }, commands: [] }
        case 'turn_done': {
          if (event.turnId !== state.turnId) return unchanged(state)
          const done = { ...state, turnFinished: true, endStatus: event.sessionStatus }
          // 문장을 다 들려준 뒤에 done이 왔다(마지막 문장 뒤 도구를 쓴 경우): 더 기다릴 재생이 없다
          return done.playbackIdle ? finishTurn(done, config) : { state: done, commands: [] }
        }
        case 'playback_idle':
          if (state.turnFinished) return finishTurn(state, config)
          return { state: { ...state, playbackIdle: true }, commands: [] } // 다음 문장을 기다린다
        case 'speech_start':
        case 'tap':
          // 끼어들기: 재생을 멈추고 들려준 문장까지만 남기게 한다
          return enterListening(state, config, [{ type: 'stopPlayback' }, ...cancelCurrent(state)])
        case 'turn_error':
          // 말하는 중에는 이미 턴이 시작됐으므로 턴 시작 전 오류(turnId null)는 늦게 온 것이다
          if (event.turnId !== state.turnId) return unchanged(state)
          return failTurn(state, event.code, config, [{ type: 'stopPlayback' }])
        default:
          return unchanged(state)
      }

    case 'paused':
      if (event.type === 'tap') return enterListening(state, config, [])
      if (event.type === 'idle_timeout') return enterClosing(state, [])
      return unchanged(state)

    case 'offline':
      if (event.type === 'offline_notice_done') return enterListening(state, config, [])
      if (event.type === 'speech_end') {
        // 안내를 듣는 중에 한 말도 큐에 넣는다
        return {
          state: { ...state, queued: state.queued + 1 },
          commands: [{ type: 'queueUtterance', utteranceId: event.utteranceId }],
        }
      }
      return unchanged(state)

    case 'closing':
      if (event.type === 'session_closed') return { state: { ...initialSession, queued: state.queued }, commands: [] }
      if (event.type === 'end_failed') {
        // 서버 세션은 끝내기가 멱등이고 무발화 감시가 정리한다
        return { state: { ...initialSession, queued: state.queued }, commands: [{ type: 'notifyError', code: event.code }] }
      }
      return unchanged(state)
  }
}

function failTurn(state: SessionState, code: string, config: SessionConfig, commands: SessionCommand[]): Transition {
  if (SESSION_GONE.has(code)) return enterClosing(state, commands)
  return enterListening(state, config, [...commands, { type: 'notifyError', code }])
}
