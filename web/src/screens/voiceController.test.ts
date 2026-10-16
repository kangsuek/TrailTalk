import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/http'
import type {
  AudioInputEvent,
  AudioOutputEvent,
  PlaybackItem,
  RecordedAudio,
  SessionState,
  VadSettings,
} from '../core'
import type { ConversationAction, StreamEvent } from '../core/conversation'
import { createVoiceController, type VoiceDeps } from './voiceController'

const STARTED = {
  session: { id: 's1', mode: 'voice', status: 'active', started_at: '2026-10-16T00:00:00Z', ended_at: null },
  greeting: { turn_id: 'g1', text: '안녕하세요!', audio: 'R1JFRVQ=' },
  persona: { id: 'jenny', name: '제니' },
} as Awaited<ReturnType<VoiceDeps['startSession']>>

const CLOSED = {
  session: { ...STARTED.session, status: 'ended', ended_at: '2026-10-16T00:10:00Z' },
  closing: '오늘 아이디어 1개 저장했어요!',
  closing_audio: 'Q0xPU0U=',
  saved: { idea: 1, todo: 0, memo: 0 },
  journal_status: 'done',
} as Awaited<ReturnType<VoiceDeps['endSession']>>

const AUDIO: RecordedAudio = { bytes: new Uint8Array(4), mimeType: 'audio/webm;codecs=opus', durationMs: 900 }

const TURN: StreamEvent[] = [
  { type: 'transcript', text: '오늘 산책 좋다' },
  { type: 'turn', turn_id: 'a1' },
  { type: 'sentence', index: 0, text: '정말요?', audio: 'UzA=' },
  { type: 'sentence', index: 1, text: '어디 걸으세요?', audio: null },
  { type: 'done', turn_id: 'a1', text: '정말요? 어디 걸으세요?', interrupted: false, session_status: 'active' },
]

const tick = () => new Promise((r) => setTimeout(r, 0))

afterEach(() => vi.useRealTimers())

function setup(overrides: Partial<VoiceDeps> = {}) {
  const log: string[] = [] // 대기열 넣기와 상태 변화의 순서
  const actions: ConversationAction[] = []
  const states: SessionState[] = []
  let inputEvent: (e: AudioInputEvent) => void = () => {}
  let outputEvent: (e: AudioOutputEvent) => void = () => {}
  const input = {
    start: vi.fn(async () => {}),
    stop: vi.fn(async () => {}),
    setMode: vi.fn(),
    dispose: vi.fn(async () => {}),
  }
  const enqueued: PlaybackItem[] = []
  const output = {
    unlock: vi.fn(async () => {}),
    enqueue: vi.fn((item: PlaybackItem) => {
      enqueued.push(item)
      log.push(`enqueue:${item.index}`)
    }),
    stop: vi.fn(),
    playEffect: vi.fn(),
    dispose: vi.fn(async () => {}),
  }
  const createInput = vi.fn((_settings: VadSettings, onEvent: (e: AudioInputEvent) => void) => {
    inputEvent = onEvent
    return input
  })
  const deps: Partial<VoiceDeps> = {
    createInput,
    createOutput: (onEvent) => {
      outputEvent = onEvent
      return output
    },
    startSession: vi.fn(async () => STARTED),
    sendAudioTurn: vi.fn(async (_id, _audio, onEvent) => {
      for (const event of TURN) onEvent(event)
    }),
    endSession: vi.fn(async () => CLOSED),
    getProfile: vi.fn(async () => {
      throw new ApiError('network_error', '서버에 연결할 수 없어요.', 0)
    }),
    ...overrides,
  }
  const controller = createVoiceController({
    dispatch: (action) => actions.push(action),
    onState: (state) => {
      states.push(state)
      log.push(`state:${state.name}`)
    },
    deps,
  })
  const state = () => states.at(-1)?.name ?? 'idle'
  return {
    controller,
    deps,
    input,
    output,
    createInput,
    enqueued,
    actions,
    log,
    state,
    speak: (audio = AUDIO) => inputEvent({ type: 'speech_end', audio }),
    micEvent: (e: AudioInputEvent) => inputEvent(e),
    played: (e: AudioOutputEvent) => outputEvent(e),
  }
}

/** 시작해서 인사말을 다 듣고 듣기 상태가 될 때까지 */
async function startListening(t: ReturnType<typeof setup>) {
  t.controller.tap()
  await tick()
  t.played({ type: 'playback_idle' })
}

describe('createVoiceController', () => {
  it('버튼을 누르면 음성 대화를 시작하고, 인사말을 다 들으면 마이크를 켠다', async () => {
    const t = setup()
    t.controller.tap()
    expect(t.output.unlock).toHaveBeenCalled() // 누른 동작 안에서 오디오를 연다
    expect(t.state()).toBe('processing')
    await tick()
    expect(t.deps.startSession).toHaveBeenCalledWith('voice', expect.any(AbortSignal))
    expect(t.actions.map((a) => a.type)).toEqual(['start', 'started'])
    expect(t.enqueued).toEqual([{ audio: 'R1JFRVQ=', index: null }])
    expect(t.state()).toBe('speaking')
    expect(t.input.setMode).toHaveBeenLastCalledWith('playback')

    t.played({ type: 'playback_idle' })
    expect(t.state()).toBe('listening')
    expect(t.input.start).toHaveBeenCalledTimes(1)
    expect(t.input.setMode).toHaveBeenLastCalledWith('normal')
    expect(t.output.playEffect).toHaveBeenCalledWith('listen')
  })

  it('말이 끝나면 녹음을 보내고, 문장 소리를 대기열에 넣은 뒤 머신에 알린다', async () => {
    const t = setup()
    await startListening(t)
    t.speak()
    await tick()
    expect(t.deps.sendAudioTurn).toHaveBeenCalledWith('s1', AUDIO, expect.any(Function), expect.any(AbortSignal))
    // 처리 중 → 첫 문장 소리를 대기열에 넣은 다음에 말하기로 바뀐다
    const afterSpeak = t.log.slice(t.log.indexOf('state:listening'))
    expect(afterSpeak.indexOf('enqueue:0')).toBeGreaterThan(afterSpeak.indexOf('state:processing'))
    expect(afterSpeak.indexOf('enqueue:0')).toBeLessThan(afterSpeak.indexOf('state:speaking'))
    expect(t.actions).toContainEqual({ type: 'send', id: 'voice-u0', text: '오늘 산책 좋다' })
    expect(t.enqueued.slice(1)).toEqual([
      { audio: 'UzA=', index: 0 },
      { audio: null, index: 1 },
    ])

    t.played({ type: 'sentence_played', index: 0 })
    t.played({ type: 'sentence_played', index: 1 })
    t.played({ type: 'playback_idle' })
    expect(t.state()).toBe('listening')
    expect(t.input.start).toHaveBeenCalledTimes(2)
  })

  it('말하는 중에 누르면 재생을 멈추고 진행 중인 답변 요청을 끊은 뒤 다시 듣는다', async () => {
    let signal: AbortSignal | undefined
    const t = setup({
      sendAudioTurn: vi.fn(async (_id, _audio, onEvent, s) => {
        signal = s
        onEvent({ type: 'turn', turn_id: 'a1' })
        onEvent({ type: 'sentence', index: 0, text: '정말요?', audio: 'UzA=' })
        await new Promise((resolve) => s?.addEventListener('abort', resolve))
        onEvent({ type: 'sentence', index: 1, text: '늦은 문장', audio: null }) // 끊은 뒤 온 문장은 버린다
        throw new DOMException('aborted', 'AbortError')
      }),
    })
    await startListening(t)
    t.speak()
    await tick()
    expect(t.state()).toBe('speaking')
    t.controller.tap()
    expect(t.output.stop).toHaveBeenCalled()
    expect(signal?.aborted).toBe(true)
    expect(t.state()).toBe('listening')
    await tick()
    expect(t.enqueued.map((i) => i.index)).toEqual([null, 0])
    expect(t.actions.some((a) => a.type === 'failed')).toBe(false)
    // 받는 중이던 말풍선은 끊긴 답변으로 마무리한다
    expect(t.actions).toContainEqual({
      type: 'event',
      event: { type: 'done', turn_id: 'a1', text: '', interrupted: true, session_status: 'active' },
    })
  })

  it('끝내기 도구로 턴이 끝나면 다 들려준 뒤 끝내기를 부르고 마무리 멘트를 들려준다', async () => {
    const t = setup({
      sendAudioTurn: vi.fn(async (_id, _audio, onEvent) => {
        onEvent({ type: 'turn', turn_id: 'a1' })
        onEvent({ type: 'sentence', index: 0, text: '오늘은 여기까지!', audio: null })
        onEvent({ type: 'done', turn_id: 'a1', text: '오늘은 여기까지!', interrupted: false, session_status: 'ended' })
      }),
    })
    await startListening(t)
    t.speak()
    await tick()
    t.played({ type: 'sentence_played', index: 0 })
    t.played({ type: 'playback_idle' })
    expect(t.state()).toBe('closing')
    expect(t.input.stop).toHaveBeenCalled()
    await tick()
    expect(t.deps.endSession).toHaveBeenCalledWith('s1', expect.any(AbortSignal))
    expect(t.actions).toContainEqual({ type: 'ended', closing: CLOSED.closing, journalPending: false })
    expect(t.enqueued.at(-1)).toEqual({ audio: 'Q0xPU0U=', index: null })
    expect(t.state()).toBe('idle')
  })

  it('말소리가 없으면(no_speech) 알리고 다시 듣는다', async () => {
    const t = setup({
      sendAudioTurn: vi.fn(async () => {
        throw new ApiError('no_speech', '말소리를 듣지 못했어요.', 422)
      }),
    })
    await startListening(t)
    t.speak()
    await tick()
    expect(t.actions).toContainEqual({ type: 'failed', message: '말소리를 듣지 못했어요.', code: 'no_speech', unsentId: 'voice-u0' })
    expect(t.state()).toBe('listening')
    expect(t.input.start).toHaveBeenCalledTimes(2)
  })

  it('처리 중에 들어온 말은 보내지 않는다', async () => {
    let finishTurn = () => {}
    const t = setup({
      sendAudioTurn: vi.fn(async () => {
        await new Promise<void>((resolve) => (finishTurn = resolve))
      }),
    })
    await startListening(t)
    t.speak()
    t.speak()
    expect(t.deps.sendAudioTurn).toHaveBeenCalledTimes(1)
    finishTurn()
  })

  it('마이크를 쓸 수 없으면 대화를 마치고 이유를 보인다', async () => {
    const t = setup()
    await startListening(t)
    t.micEvent({ type: 'error', code: 'mic_denied' })
    await tick()
    expect(t.deps.endSession).toHaveBeenCalled()
    const ended = t.actions.findIndex((a) => a.type === 'ended')
    const failed = t.actions.findIndex((a) => a.type === 'failed')
    expect(failed).toBeGreaterThan(ended) // 정리가 문구를 지우지 않게 끝난 뒤에 보인다
    expect(t.actions[failed]).toMatchObject({ message: expect.stringContaining('마이크 권한') })
  })

  it('듣는 중 무발화 시간이 지나면 대화를 마친다', async () => {
    vi.useFakeTimers()
    const t = setup()
    t.controller.tap()
    await vi.advanceTimersByTimeAsync(0)
    t.played({ type: 'playback_idle' })
    await vi.advanceTimersByTimeAsync(30 * 60_000 - 1)
    expect(t.deps.endSession).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(t.deps.endSession).toHaveBeenCalled()
  })

  it('서버 설정값(VAD·무발화 시간)을 받아 쓴다', async () => {
    vi.useFakeTimers()
    const vad = {
      speech_threshold: 0.6,
      silence_threshold: 0.4,
      playback_speech_threshold: 0.9,
      playback_silence_threshold: 0.7,
      end_of_speech_silence_ms: 1000,
      min_speech_ms: 250,
    }
    const t = setup({
      getProfile: vi.fn(async () => ({ client: { vad, session: { idle_timeout_minutes: 1 } } }) as never),
    })
    await vi.advanceTimersByTimeAsync(0)
    t.controller.tap()
    await vi.advanceTimersByTimeAsync(0)
    t.played({ type: 'playback_idle' })
    expect(t.createInput.mock.calls[0][0]).toMatchObject({ speechThreshold: 0.6, endOfSpeechSilenceMs: 1000 })
    await vi.advanceTimersByTimeAsync(60_000)
    expect(t.deps.endSession).toHaveBeenCalled()
  })

  it('정리 중 길게 누르면 끝내기 응답을 기다리지 않고 대기로 간다', async () => {
    let endSignal: AbortSignal | undefined
    const t = setup({
      endSession: vi.fn(async (_id, s) => {
        endSignal = s
        return new Promise<never>(() => {})
      }),
    })
    await startListening(t)
    t.controller.longPress()
    expect(t.state()).toBe('closing')
    t.controller.longPress()
    expect(t.state()).toBe('idle')
    expect(endSignal?.aborted).toBe(true)
    expect(t.actions.at(-1)).toEqual({ type: 'ended' })
  })

  it('시작에 실패하면 알리고 대기로 돌아간다', async () => {
    const t = setup({
      startSession: vi.fn(async () => {
        throw new ApiError('llm_error', '인사말을 만들지 못했어요.', 502)
      }),
    })
    t.controller.tap()
    await tick()
    expect(t.state()).toBe('idle')
    expect(t.actions.at(-1)).toEqual({ type: 'failed', message: '인사말을 만들지 못했어요.', code: 'llm_error' })
  })

  it('dispose하면 마이크·재생을 정리하고 이후 이벤트를 무시한다', async () => {
    const t = setup()
    await startListening(t)
    await t.controller.dispose()
    expect(t.input.dispose).toHaveBeenCalled()
    expect(t.output.dispose).toHaveBeenCalled()
    t.speak()
    expect(t.deps.sendAudioTurn).not.toHaveBeenCalled()
  })

  it('정리 중에 늦게 온 마이크 오류는 무시한다(마무리 멘트를 잃지 않게)', async () => {
    type Closed = Awaited<ReturnType<VoiceDeps['endSession']>>
    let finishEnd = (_v: Closed) => {}
    const t = setup({ endSession: vi.fn(() => new Promise<Closed>((resolve) => (finishEnd = resolve))) })
    await startListening(t)
    t.controller.longPress()
    expect(t.state()).toBe('closing')
    t.micEvent({ type: 'error', code: 'mic_denied' })
    expect(t.state()).toBe('closing')
    finishEnd(CLOSED)
    await tick()
    expect(t.actions).toContainEqual({ type: 'ended', closing: CLOSED.closing, journalPending: false })
    expect(t.actions.some((a) => a.type === 'failed')).toBe(false)
  })

  it('시작 응답 전에 길게 누르면 시작을 취소하고 대기로 돌아간다', async () => {
    let startSignal: AbortSignal | undefined
    const t = setup({
      startSession: vi.fn((_mode, s) => {
        startSignal = s
        return new Promise<never>(() => {})
      }),
    })
    t.controller.tap()
    t.controller.longPress()
    await tick()
    expect(startSignal?.aborted).toBe(true)
    expect(t.deps.endSession).not.toHaveBeenCalled()
    expect(t.state()).toBe('idle')
    expect(t.actions.at(-1)).toMatchObject({ type: 'failed' })
  })

  it('끝내기가 실패해도 끝난 화면으로 가고 이유를 보인다', async () => {
    const t = setup({
      endSession: vi.fn(async () => {
        throw new ApiError('network_error', '서버에 연결할 수 없어요.', 0)
      }),
    })
    await startListening(t)
    t.controller.longPress()
    await tick()
    expect(t.state()).toBe('idle')
    const ended = t.actions.findIndex((a) => a.type === 'ended')
    expect(ended).toBeGreaterThan(-1)
    expect(t.actions.at(-1)).toEqual({ type: 'failed', message: '서버에 연결할 수 없어요.', code: 'network_error' })
  })

  it('턴 도중 세션이 서버에서 끝나면 정리로 가고, 이유는 끝난 뒤에 보인다', async () => {
    const t = setup({
      sendAudioTurn: vi.fn(async (_id, _audio, onEvent) => {
        onEvent({ type: 'turn', turn_id: 'a1' })
        onEvent({ type: 'error', code: 'session_ended', message: '대화를 마쳤어요.' })
      }),
    })
    await startListening(t)
    t.speak()
    await tick()
    expect(t.deps.endSession).toHaveBeenCalled()
    expect(t.state()).toBe('idle')
    const ended = t.actions.findIndex((a) => a.type === 'ended')
    expect(t.actions.slice(ended + 1)).toContainEqual({ type: 'failed', message: '대화를 마쳤어요.' })
  })

  it('처리 중에 누르면 안내 음성을 멈추고 답변을 취소한 뒤 다시 듣는다', async () => {
    let signal: AbortSignal | undefined
    const t = setup({
      sendAudioTurn: vi.fn(async (_id, _audio, onEvent, s) => {
        signal = s
        onEvent({ type: 'turn', turn_id: 'a1' })
        onEvent({
          type: 'tool',
          phase: 'start',
          tool_use_id: 'w1',
          name: 'web_search',
          input: null,
          summary: null,
          is_error: false,
          notice: { text: '잠깐만요, 찾아볼게요!', audio: 'Tk9USUNF' },
        })
        await new Promise((resolve) => s?.addEventListener('abort', resolve))
        throw new DOMException('aborted', 'AbortError')
      }),
    })
    await startListening(t)
    t.speak()
    await tick()
    expect(t.state()).toBe('processing')
    expect(t.enqueued.at(-1)).toEqual({ audio: 'Tk9USUNF', index: null })
    t.controller.tap()
    expect(t.output.stop).toHaveBeenCalled()
    expect(signal?.aborted).toBe(true)
    expect(t.state()).toBe('listening')
    expect(t.actions).toContainEqual({
      type: 'event',
      event: { type: 'done', turn_id: 'a1', text: '', interrupted: true, session_status: 'active' },
    })
  })
})
