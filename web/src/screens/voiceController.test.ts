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
import { createMemoryQueue } from '../core'
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
  const clock = { now: 10_000 } // 지연 측정 시계(테스트가 움직인다)
  const queue = overrides.queue ?? createMemoryQueue()
  let online = () => {}
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
    cancelTurn: vi.fn(async () => {}),
    reportLatency: vi.fn(async () => {}),
    now: () => clock.now,
    getProfile: vi.fn(async () => {
      throw new ApiError('network_error', '서버에 연결할 수 없어요.', 0)
    }),
    queue,
    recordAudioTurn: vi.fn(async () => ({ text: '기록함' })),
    speak: vi.fn(async () => {}),
    checkHealth: vi.fn(async () => true),
    cancelSpeech: vi.fn(),
    watchOnline: (cb) => {
      online = cb
      return () => {}
    },
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
    clock,
    queue,
    goOnline: () => online(),
    speak: (audio = AUDIO, speechEndedAt = clock.now - 1500) =>
      inputEvent({ type: 'speech_end', audio, speechEndedAt }),
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
    // 서버와 말풍선 모두 들려준 문장까지만 남긴다(아직 한 문장도 다 듣지 못했다)
    expect(t.deps.cancelTurn).toHaveBeenCalledWith('s1', 'a1', -1)
    expect(t.actions).toContainEqual({ type: 'interrupt', turnId: 'a1', keep: 0 })
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

  it('답변을 기다리는 중에 이어서 한 말은 큐에 넣었다가 답변이 끝나면 보낸다', async () => {
    let finishTurn = () => {}
    const later: RecordedAudio = { bytes: new Uint8Array([7]), mimeType: 'audio/webm', durationMs: 500 }
    const sendAudioTurn = vi.fn<VoiceDeps['sendAudioTurn']>(async (_id, _audio, onEvent) => {
      onEvent({ type: 'transcript', text: '첫말' })
      onEvent({ type: 'turn', turn_id: 'a1' })
      await new Promise<void>((resolve) => (finishTurn = resolve))
      onEvent({ type: 'done', turn_id: 'a1', text: '', interrupted: false, session_status: 'active' })
    })
    const t = setup({ sendAudioTurn })
    await startListening(t)
    t.speak()
    await tick()
    t.speak(later) // 처리 중에 이어서 한 말
    expect(sendAudioTurn).toHaveBeenCalledTimes(1)
    expect(t.state()).toBe('processing')
    await tick()
    expect(await t.queue.count('s1')).toBe(1)
    sendAudioTurn.mockImplementation(async (_id, _audio, onEvent) => {
      onEvent({ type: 'transcript', text: '이어서 한 말' })
      onEvent({ type: 'turn', turn_id: 'a2' })
      onEvent({ type: 'done', turn_id: 'a2', text: '', interrupted: false, session_status: 'active' })
    })
    finishTurn()
    await vi.waitFor(() => expect(sendAudioTurn).toHaveBeenCalledTimes(2))
    expect(sendAudioTurn.mock.calls[1][1].bytes).toEqual(later.bytes)
    await vi.waitFor(() => expect(t.state()).toBe('listening'))
    expect(await t.queue.count('s1')).toBe(0)
  })

  it('보내던 말이 서버에 닿지 않으면 그사이 이어서 한 말보다 앞에 보관한다', async () => {
    let fail: (error: Error) => void = () => {}
    const first: RecordedAudio = { bytes: new Uint8Array([1]), mimeType: 'audio/webm', durationMs: 500 }
    const later: RecordedAudio = { bytes: new Uint8Array([2]), mimeType: 'audio/webm', durationMs: 500 }
    const t = setup({
      sendAudioTurn: vi.fn(async () => {
        await new Promise<void>((_resolve, reject) => (fail = reject))
      }),
    })
    await startListening(t)
    t.speak(first)
    await tick()
    t.speak(later) // 첫 말을 보내는 중(처리 중)에 이어서 한 말
    await tick()
    fail(new ApiError('network_error', '서버에 연결할 수 없어요.', 0))
    await vi.waitFor(() => expect(t.deps.speak).toHaveBeenCalled()) // 오프라인 안내
    await vi.waitFor(async () => expect(await t.queue.count('s1')).toBe(2))
    expect((await t.queue.oldest('s1'))?.bytes).toEqual(first.bytes)
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
    expect(t.deps.cancelTurn).toHaveBeenCalledWith('s1', 'a1', -1)
    expect(t.actions).toContainEqual({ type: 'interrupt', turnId: 'a1', keep: 0 })
  })

  it('끝까지 받은 답변을 재생 중에 끊으면 들려준 문장 번호로 자른다', async () => {
    const t = setup()
    await startListening(t)
    t.speak()
    await tick()
    t.played({ type: 'sentence_played', index: 0 }) // 첫 문장만 다 들었다
    t.controller.tap()
    expect(t.deps.cancelTurn).toHaveBeenCalledWith('s1', 'a1', 0)
    expect(t.actions).toContainEqual({ type: 'interrupt', turnId: 'a1', keep: 1 })
  })

  it('인사말 중에 끊으면 서버에 알리되 인사말 말풍선은 자르지 않는다', async () => {
    const t = setup()
    t.controller.tap()
    await tick()
    t.controller.tap() // 인사말 재생 중 끼어들기
    expect(t.state()).toBe('listening')
    expect(t.deps.cancelTurn).toHaveBeenCalledWith('s1', 'g1', -1)
    expect(t.actions.some((a) => a.type === 'interrupt')).toBe(false)
  })

  it('첫 소리가 나면 말 끝 → 요청, 요청 → 첫 소리를 한 번 보고한다', async () => {
    const t = setup()
    await startListening(t)
    t.played({ type: 'started', index: null }) // 인사말 소리는 재지 않는다
    t.clock.now = 20_000
    t.speak(AUDIO, 18_800) // 말은 1.2초 전에 끝났다
    await tick()
    t.clock.now = 21_900
    t.played({ type: 'started', index: 0 })
    t.played({ type: 'started', index: 1 })
    expect(t.deps.reportLatency).toHaveBeenCalledTimes(1)
    expect(t.deps.reportLatency).toHaveBeenCalledWith('s1', 'a1', 1200, 1900, false)
  })

  it('검색 안내 음성으로 시작한 턴은 그렇다고 알린다', async () => {
    const t = setup({
      sendAudioTurn: vi.fn(async (_id, _audio, onEvent) => {
        onEvent({ type: 'turn', turn_id: 'a1' })
        onEvent({
          type: 'tool',
          phase: 'start',
          tool_use_id: 'w1',
          name: 'web_search',
          input: null,
          summary: null,
          is_error: false,
          notice: { text: '잠깐만요!', audio: 'Tk9USUNF' },
        })
      }),
    })
    await startListening(t)
    t.speak()
    await tick()
    t.played({ type: 'started', index: null })
    expect(t.deps.reportLatency).toHaveBeenCalledWith('s1', 'a1', expect.any(Number), expect.any(Number), true)
  })

  it('소리 없이 끝난 턴의 측정은 마무리 멘트 소리에 붙지 않는다', async () => {
    const t = setup({
      sendAudioTurn: vi.fn(async (_id, _audio, onEvent) => {
        onEvent({ type: 'turn', turn_id: 'a1' })
        onEvent({ type: 'error', code: 'llm_error', message: '답변을 만들지 못했습니다.' })
      }),
    })
    await startListening(t)
    t.speak()
    await tick()
    t.controller.longPress() // 끝내고 마무리 멘트를 들려준다
    await tick()
    t.played({ type: 'started', index: null })
    expect(t.deps.reportLatency).not.toHaveBeenCalled()
  })

  it('끊은 턴은 재지 않는다', async () => {
    let release = () => {}
    const t = setup({
      sendAudioTurn: vi.fn(async (_id, _audio, onEvent, s) => {
        onEvent({ type: 'turn', turn_id: 'a1' })
        onEvent({ type: 'sentence', index: 0, text: '정말요?', audio: 'UzA=' })
        await new Promise<void>((resolve) => {
          release = resolve
          s?.addEventListener('abort', () => resolve())
        })
      }),
    })
    await startListening(t)
    t.speak()
    await tick()
    t.controller.tap() // 소리가 나기 전에 끊었다
    t.played({ type: 'started', index: 0 })
    release()
    expect(t.deps.reportLatency).not.toHaveBeenCalled()
  })

  describe('오프라인 보관(S3-12)', () => {
    const unreachable = () => new ApiError('network_error', '서버에 연결할 수 없어요.', 0)

    /** 첫 전송은 서버에 닿지 않고, 그다음부터는 TURN을 낸다 */
    function offlineOnce(times = 1) {
      let failures = times
      return vi.fn(async (_id: string, _audio: unknown, onEvent: (e: StreamEvent) => void) => {
        if (failures-- > 0) throw unreachable()
        for (const event of TURN) onEvent(event)
      })
    }

    it('서버에 닿지 않으면 보관하고 안내한 뒤, 연결되면 보관한 말을 보내 대답을 듣는다', async () => {
      let noticeDone = () => {}
      const t = setup({
        sendAudioTurn: offlineOnce(),
        speak: vi.fn(() => new Promise<void>((resolve) => (noticeDone = resolve))),
      })
      await startListening(t)
      t.speak()
      await tick()
      expect(t.state()).toBe('offline')
      expect(await t.queue.count('s1')).toBe(1)
      expect(t.deps.speak).toHaveBeenCalledWith('네트워크 연결이 불안하여 메모만 해둘게요.')
      expect(t.output.playEffect).toHaveBeenCalledWith('offline')
      noticeDone()
      await tick()
      expect(t.state()).toBe('listening') // 안내가 끝났다

      t.goOnline()
      await tick()
      expect(t.deps.sendAudioTurn).toHaveBeenCalledTimes(2)
      const sent = (t.deps.sendAudioTurn as ReturnType<typeof vi.fn>).mock.calls[1][1]
      expect(sent).toMatchObject({ bytes: AUDIO.bytes, mimeType: AUDIO.mimeType })
      expect(await t.queue.count('s1')).toBe(0)
      expect(t.state()).toBe('speaking') // 보관한 말의 대답을 들려준다
      t.played({ type: 'playback_idle' })
      expect(t.state()).toBe('listening')
    })

    it('큐가 남아 있는 동안 한 새 말은 큐 뒤에 넣고 차례로 보낸다', async () => {
      const t = setup({ sendAudioTurn: offlineOnce(2) })
      await startListening(t)
      t.speak()
      await tick()
      await tick() // 안내 뒤 듣기
      const second: RecordedAudio = { ...AUDIO, bytes: new Uint8Array([9, 9]) }
      t.speak(second) // 연결이 없으니 보관만 한다
      await tick()
      expect(t.state()).toBe('listening')
      expect(await t.queue.count('s1')).toBe(2)

      t.goOnline() // 첫 재전송도 실패(offlineOnce(2))
      await tick()
      expect(t.state()).toBe('listening')
      expect((await t.queue.oldest('s1'))?.attempts).toBe(1)

      t.goOnline()
      await tick()
      const calls = (t.deps.sendAudioTurn as ReturnType<typeof vi.fn>).mock.calls
      expect(calls[2][1].bytes).toEqual(AUDIO.bytes) // 먼저 한 말부터
      t.played({ type: 'playback_idle' })
      await tick()
      expect(calls[3][1].bytes).toEqual(second.bytes)
    })

    it('끊긴 동안 30초마다 다시 시도한다', async () => {
      vi.useFakeTimers()
      const t = setup({ sendAudioTurn: offlineOnce() })
      t.controller.tap()
      await vi.advanceTimersByTimeAsync(0)
      t.played({ type: 'playback_idle' })
      t.speak()
      await vi.advanceTimersByTimeAsync(0)
      expect(t.state()).toBe('listening')
      await vi.advanceTimersByTimeAsync(30_000)
      expect(t.deps.sendAudioTurn).toHaveBeenCalledTimes(2)
    })

    it('보관한 말을 보낼 때 서버가 대화를 끝냈으면 기록만 남기고 정리로 간다', async () => {
      let calls = 0
      const t = setup({
        sendAudioTurn: vi.fn(async () => {
          if (calls++ === 0) throw unreachable()
          throw new ApiError('session_ended', '이미 끝난 대화입니다.', 409)
        }),
      })
      await startListening(t)
      t.speak()
      await tick()
      await tick()
      t.goOnline()
      await tick()
      expect(t.deps.recordAudioTurn).toHaveBeenCalledWith('s1', expect.objectContaining({ bytes: AUDIO.bytes }))
      expect(await t.queue.count('s1')).toBe(0)
      expect(t.deps.endSession).toHaveBeenCalled()
    })

    it('보관한 말이 말소리가 없으면 버리고, 서버 일시 오류면 남겨 둔다', async () => {
      let calls = 0
      const errors = [unreachable(), new ApiError('llm_error', '답변을 만들지 못했습니다.', 502), new ApiError('no_speech', '말소리를 알아듣지 못했어요.', 422)]
      const t = setup({
        sendAudioTurn: vi.fn(async () => {
          throw errors[Math.min(calls++, errors.length - 1)]
        }),
      })
      await startListening(t)
      t.speak()
      await tick()
      await tick()
      t.goOnline() // 일시 오류: 남겨 두고 조용히 듣는다
      await tick()
      expect(await t.queue.count('s1')).toBe(1)
      expect(t.state()).toBe('listening')
      t.goOnline() // 말소리 없음: 버린다
      await tick()
      expect(await t.queue.count('s1')).toBe(0)
      expect(t.actions.at(-1)).toMatchObject({ type: 'failed', code: 'no_speech' })
    })

    it('새로 말한 것도 서버가 대화를 끝냈으면 기록만 남긴다', async () => {
      const t = setup({
        sendAudioTurn: vi.fn(async () => {
          throw new ApiError('session_ended', '이미 끝난 대화입니다.', 409)
        }),
      })
      await startListening(t)
      t.speak()
      await tick()
      expect(t.deps.recordAudioTurn).toHaveBeenCalledWith('s1', AUDIO)
    })

    it('끊긴 채 대화를 끝내면 남은 말은 연결이 돌아온 뒤 기록만 남긴다', async () => {
      let online = false
      const record = vi.fn(async (): Promise<{ text: string }> => {
        if (!online) throw unreachable()
        return { text: '기록함' }
      })
      const t = setup({
        sendAudioTurn: offlineOnce(),
        recordAudioTurn: record,
        endSession: vi.fn(async () => {
          throw unreachable()
        }),
      })
      await startListening(t)
      t.speak()
      await tick()
      await tick()
      t.controller.longPress() // 끊긴 채 끝낸다(끝내기도 실패한다)
      await tick()
      expect(t.state()).toBe('idle')
      expect(await t.queue.count('s1')).toBe(1) // 연결이 없어 아직 남아 있다

      online = true
      t.goOnline()
      await tick()
      expect(record).toHaveBeenLastCalledWith('s1', expect.objectContaining({ sessionId: 's1' }))
      expect(await t.queue.count('s1')).toBe(0)
    })

    it('30일이 지난 녹음과 계속 실패하는 말은 기기에 남기지 않는다', async () => {
      const queue = createMemoryQueue()
      const day = 24 * 60 * 60 * 1000
      const base = { mimeType: 'audio/webm', bytes: new Uint8Array([1]), attempts: 0 }
      await queue.add({ ...base, id: 'stale', sessionId: 'old', createdAt: Date.now() - 31 * day })
      await queue.add({ ...base, id: 'tired', sessionId: 'old', createdAt: Date.now(), recordAttempts: 4 })
      const record = vi.fn(async (): Promise<{ text: string }> => {
        throw new ApiError('stt_failed', '음성 인식 실패', 502)
      })
      setup({ queue, recordAudioTurn: record })
      await tick()
      expect(record).toHaveBeenCalledTimes(1) // 기한이 지난 말은 보내지도 않는다
      expect(await queue.others(null)).toEqual([]) // 다섯 번째 실패로 지웠다
    })

    it('다섯 번째로 보내지 못한 말은 대답을 포기하고 기록만 남긴다(다시 보내지 않는다)', async () => {
      const queue = createMemoryQueue()
      let calls = 0
      const t = setup({
        queue,
        sendAudioTurn: vi.fn(async () => {
          if (calls++ === 0) throw unreachable()
          throw new ApiError('llm_error', '답변을 만들지 못했습니다.', 502)
        }),
      })
      await startListening(t)
      t.speak()
      await tick()
      await tick()
      const item = (await queue.oldest('s1'))!
      await queue.update(item.id, { attempts: 4 }) // 이미 네 번 실패했다
      t.goOnline()
      await tick()
      await tick()
      expect(t.deps.recordAudioTurn).toHaveBeenCalledWith('s1', expect.objectContaining({ id: item.id }))
      expect(await queue.others(null)).toEqual([])
      expect(t.state()).toBe('listening')
      t.goOnline()
      await tick()
      expect(t.deps.sendAudioTurn).toHaveBeenCalledTimes(2) // 포기한 말을 다시 보내지 않는다
    })

    it('기록이 진행 중인 턴과 겹쳐도(409) 실패로 세지 않는다', async () => {
      const queue = createMemoryQueue()
      await queue.add({ id: 'busy', sessionId: 'old', mimeType: 'audio/webm', bytes: new Uint8Array([1]), createdAt: Date.now(), attempts: 0 })
      const record = vi.fn(async (): Promise<{ text: string }> => {
        throw new ApiError('turn_in_progress', '이전 답변이 아직 끝나지 않았습니다.', 409)
      })
      setup({ queue, recordAudioTurn: record })
      await tick()
      expect(record).toHaveBeenCalled()
      expect((await queue.others(null))[0].recordAttempts ?? 0).toBe(0)
    })

    it('처리 중 보관함을 읽지 못해도 멈추지 않는다', async () => {
      const queue = createMemoryQueue()
      const t = setup({ queue, sendAudioTurn: offlineOnce() })
      await startListening(t)
      t.speak()
      await tick()
      await tick()
      queue.oldest = async () => {
        throw new Error('IndexedDB 오류')
      }
      t.goOnline()
      await tick()
      expect(t.state()).toBe('listening')
    })

    it('끊긴 동안의 재시도는 서버에 닿을 때만 다시 보낸다', async () => {
      vi.useFakeTimers()
      let reachable = false
      const t = setup({ sendAudioTurn: offlineOnce(), checkHealth: vi.fn(async () => reachable) })
      t.controller.tap()
      await vi.advanceTimersByTimeAsync(0)
      t.played({ type: 'playback_idle' })
      t.speak()
      await vi.advanceTimersByTimeAsync(0)
      const listenSounds = () => (t.output.playEffect as ReturnType<typeof vi.fn>).mock.calls.filter(([n]) => n === 'listen').length
      const before = listenSounds()
      await vi.advanceTimersByTimeAsync(90_000)
      expect(t.deps.sendAudioTurn).toHaveBeenCalledTimes(1) // 닿지 않으니 다시 보내지 않는다
      expect(listenSounds()).toBe(before) // 효과음도 되풀이하지 않는다
      reachable = true
      await vi.advanceTimersByTimeAsync(30_000)
      expect(t.deps.sendAudioTurn).toHaveBeenCalledTimes(2)
    })

    it('서버가 붙잡고 답하지 않으면 30초 뒤 닿지 않은 것으로 보고 보관한다', async () => {
      vi.useFakeTimers()
      const t = setup({
        sendAudioTurn: vi.fn(
          (_id: string, _audio: unknown, _onEvent: unknown, signal?: AbortSignal) =>
            new Promise<void>((_, reject) => signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))),
        ),
      })
      t.controller.tap()
      await vi.advanceTimersByTimeAsync(0)
      t.played({ type: 'playback_idle' })
      t.speak()
      await vi.advanceTimersByTimeAsync(30_000)
      expect(t.deps.speak).toHaveBeenCalled() // 오프라인 안내를 했다
      expect(await t.queue.count('s1')).toBe(1)
    })

    it('보내는 중에 끝내면 그 말을 보관해 기록만 남긴다', async () => {
      const t = setup({
        sendAudioTurn: vi.fn(
          (_id: string, _audio: unknown, _onEvent: unknown, signal?: AbortSignal) =>
            new Promise<void>((_, reject) => signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))),
        ),
      })
      await startListening(t)
      t.speak()
      await tick()
      t.controller.longPress()
      await tick()
      await tick()
      expect(t.deps.recordAudioTurn).toHaveBeenCalledWith('s1', expect.objectContaining({ bytes: AUDIO.bytes }))
    })

    it('이전 대화의 남은 말은 시작할 때 기록만 남기고, 연결이 없으면 남겨 둔다', async () => {
      const queue = createMemoryQueue()
      await queue.add({ id: 'old', sessionId: 'old-session', mimeType: 'audio/webm', bytes: new Uint8Array([1]), createdAt: Date.now(), attempts: 0 })
      const record = vi.fn(async (): Promise<{ text: string }> => {
        throw unreachable()
      })
      setup({ queue, recordAudioTurn: record })
      await tick()
      expect(record).toHaveBeenCalledWith('old-session', expect.objectContaining({ id: 'old' }))
      expect(await queue.count('old-session')).toBe(1)

      record.mockImplementation(async () => ({ text: '기록함' }))
      const t = setup({ queue, recordAudioTurn: record })
      await tick()
      expect(await queue.count('old-session')).toBe(0)
      t.goOnline()
    })
  })

  describe('음성 대화 중 글 입력(sendText)', () => {
    const TEXT_TURN = TURN.filter((e) => e.type !== 'transcript') // 글 턴에는 인식 결과가 없다

    it('듣는 중이면 글을 보내고 내 말풍선을 바로 그린 뒤, 답변을 들려주고 다시 듣는다', async () => {
      const sendTextTurn = vi.fn<VoiceDeps['sendTextTurn']>(async (_id, _text, onEvent) => {
        for (const event of TEXT_TURN) onEvent(event)
      })
      const t = setup({ sendTextTurn })
      await startListening(t)
      expect(t.controller.sendText('  링크 보내 줘 ')).toBe(true)
      expect(t.actions).toContainEqual({ type: 'send', id: 'voice-t0', text: '링크 보내 줘' })
      await tick()
      expect(sendTextTurn).toHaveBeenCalledWith('s1', '링크 보내 줘', expect.any(Function), expect.any(AbortSignal))
      expect(t.deps.sendAudioTurn).not.toHaveBeenCalled()
      expect(t.state()).toBe('speaking')
      t.played({ type: 'playback_idle' })
      expect(t.state()).toBe('listening')
      expect(t.deps.reportLatency).not.toHaveBeenCalled() // 말 끝 시각이 없어 재지 않는다
    })

    it('말하는 중이면 끼어들고, 서버가 취소를 마친 뒤에 보낸다(바쁘다고 하면 잠깐 뒤 다시)', async () => {
      let finishCancel: () => void = () => {}
      const cancelTurn = vi.fn(() => new Promise<void>((resolve) => (finishCancel = resolve)))
      let busy = true
      const sendTextTurn = vi.fn<VoiceDeps['sendTextTurn']>(async (_id, _text, onEvent) => {
        if (busy) {
          busy = false // 이전 답변 정리가 아직 끝나지 않았다(서버 turn_lock)
          onEvent({ type: 'error', code: 'turn_in_progress', message: '이전 답변이 아직 끝나지 않았습니다.' })
          return
        }
        for (const event of TEXT_TURN) onEvent(event)
      })
      const t = setup({
        sendTextTurn,
        cancelTurn,
        sendAudioTurn: vi.fn(async (_id, _audio, onEvent, s) => {
          onEvent({ type: 'turn', turn_id: 'a1' })
          onEvent({ type: 'sentence', index: 0, text: '정말요?', audio: 'UzA=' })
          await new Promise((resolve) => s?.addEventListener('abort', resolve))
          throw new DOMException('aborted', 'AbortError')
        }),
      })
      await startListening(t)
      t.speak()
      await tick()
      expect(t.state()).toBe('speaking')
      const onUnsent = vi.fn()
      expect(t.controller.sendText('잠깐, 글로 할게', onUnsent)).toBe(true)
      expect(t.output.stop).toHaveBeenCalled()
      expect(cancelTurn).toHaveBeenCalledWith('s1', 'a1', -1)
      await tick()
      expect(sendTextTurn).not.toHaveBeenCalled() // 취소가 끝나기를 기다린다
      finishCancel()
      await tick()
      expect(sendTextTurn).toHaveBeenCalledTimes(1)
      await new Promise((r) => setTimeout(r, 600)) // 바쁨 → 잠깐 뒤 다시 보낸다
      expect(sendTextTurn).toHaveBeenCalledTimes(2)
      expect(onUnsent).not.toHaveBeenCalled()
      expect(t.actions.filter((a) => a.type === 'send' && a.text === '잠깐, 글로 할게')).toHaveLength(1)
      expect(t.actions.some((a) => a.type === 'failed')).toBe(false)
      expect(t.state()).toBe('speaking')
    })

    it('바빠서 다시 보내려고 기다리는 사이 대화를 끝내면 다시 보내지 않고 말풍선을 뺀다', async () => {
      const sendTextTurn = vi.fn<VoiceDeps['sendTextTurn']>(async (_id, _text, onEvent) => {
        onEvent({ type: 'error', code: 'turn_in_progress', message: '이전 답변이 아직 끝나지 않았습니다.' })
      })
      const t = setup({ sendTextTurn })
      await startListening(t)
      const onUnsent = vi.fn()
      t.controller.sendText('보낼게', onUnsent)
      await tick()
      expect(sendTextTurn).toHaveBeenCalledTimes(1)
      t.controller.longPress() // 기다리는 중에 끝내기
      await new Promise((r) => setTimeout(r, 600))
      expect(sendTextTurn).toHaveBeenCalledTimes(1)
      expect(onUnsent).not.toHaveBeenCalled() // 끝난 대화의 글은 다음 대화로 넘기지 않는다
      expect(t.actions).toContainEqual({ type: 'unsend', id: 'voice-t0' })
      expect(t.actions.some((a) => a.type === 'failed')).toBe(false) // 정리 중 표시를 건드리지 않는다
    })

    it('답변을 기다리는 중·시작 전·빈 글은 받지 않는다', async () => {
      const sendTextTurn = vi.fn<VoiceDeps['sendTextTurn']>(async () => {})
      const t = setup({ sendTextTurn, sendAudioTurn: vi.fn(() => new Promise<void>(() => {})) })
      expect(t.controller.sendText('시작 전')).toBe(false)
      await startListening(t)
      expect(t.controller.sendText('   ')).toBe(false)
      t.speak()
      await tick()
      expect(t.state()).toBe('processing')
      expect(t.controller.sendText('기다리는 중')).toBe(false)
      await tick()
      expect(sendTextTurn).not.toHaveBeenCalled()
    })

    it('서버에 닿지 않으면 보관하지 않고 글을 돌려준 뒤 다시 듣는다', async () => {
      const t = setup({
        sendTextTurn: vi.fn(async () => {
          throw new ApiError('network_error', '서버에 연결할 수 없어요.', 0)
        }),
      })
      await startListening(t)
      const onUnsent = vi.fn()
      expect(t.controller.sendText('보내 줘', onUnsent)).toBe(true)
      await tick()
      await tick()
      expect(onUnsent).toHaveBeenCalledWith('보내 줘')
      expect(t.actions).toContainEqual(expect.objectContaining({ type: 'failed', unsentId: 'voice-t0' }))
      expect(await t.queue.oldest('s1')).toBeNull() // 오프라인 큐(녹음)에 넣지 않았다
      expect(t.state()).toBe('listening')
    })
  })
})
