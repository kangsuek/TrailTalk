// 마이크 입력(AudioInput) 약속과 VAD 설정값(설계서 4.8, 계획서 S3-10, 클라이언트 규약 5절).
// 브라우저 구현은 src/platform/audioInput.ts, 안드로이드는 같은 인터페이스를 네이티브로 구현한다.
import clientDefaults from '../../../shared/client-defaults.json'

/** VAD 설정(서버 /api/profile의 client.vad). 확률 임계값은 Silero VAD 출력 기준이다. */
export interface VadSettings {
  speechThreshold: number
  silenceThreshold: number
  playbackSpeechThreshold: number // 캐릭터 음성 재생 중(setVadMode playback)
  playbackSilenceThreshold: number
  endOfSpeechSilenceMs: number // 무음이 이만큼 이어지면 발화 끝
  minSpeechMs: number // 이보다 짧은 소리는 버린다
}

/** 서버 client.vad(snake_case)와 같은 모양 */
export interface ClientVadConfig {
  speech_threshold: number
  silence_threshold: number
  playback_speech_threshold: number
  playback_silence_threshold: number
  end_of_speech_silence_ms: number
  min_speech_ms: number
}

export function vadSettingsFrom(vad: ClientVadConfig): VadSettings {
  return {
    speechThreshold: vad.speech_threshold,
    silenceThreshold: vad.silence_threshold,
    playbackSpeechThreshold: vad.playback_speech_threshold,
    playbackSilenceThreshold: vad.playback_silence_threshold,
    endOfSpeechSilenceMs: vad.end_of_speech_silence_ms,
    minSpeechMs: vad.min_speech_ms,
  }
}

// 프로필을 받기 전 대체값(shared/client-defaults.json)
export const DEFAULT_VAD_SETTINGS: VadSettings = vadSettingsFrom(clientDefaults.vad)

export type VadMode = 'normal' | 'playback'

/** 말 한 번의 녹음. 서버 음성 턴(POST /api/sessions/{id}/turns/audio) 본문으로 그대로 보낸다 */
export interface RecordedAudio {
  bytes: Uint8Array<ArrayBuffer>
  mimeType: string // 'audio/webm;codecs=opus' 또는 대체 형식 'audio/wav'
  durationMs: number
}

export type AudioInputErrorCode = 'mic_denied' | 'mic_unavailable' | 'vad_failed'

// speech_start는 말소리가 minSpeechMs 동안 이어진 뒤에 온다(더 짧은 소리는 이벤트 없이 버린다).
// stop·dispose 뒤에는 아무 이벤트도 오지 않는다
export type AudioInputEvent =
  | { type: 'speech_start' }
  | { type: 'speech_end'; audio: RecordedAudio }
  | { type: 'error'; code: AudioInputErrorCode }

/** 상태 머신 명령과 1:1: micOn → start, micOff → stop, setVadMode → setMode */
export interface AudioInput {
  start(): Promise<void>
  stop(): Promise<void>
  setMode(mode: VadMode): void
  dispose(): Promise<void>
}
