// 음성 대화 훅(계획서 S3-13): 컨트롤러를 화면 수명에 맞춰 만들고 정리하며,
// 대화 중에는 화면이 꺼지지 않게 하고(Screen Wake Lock) 이어폰 버튼을 버튼 한 번으로 받는다(Media Session).
import { useCallback, useEffect, useRef, useState } from 'react'
import { initialSession, type SessionState } from '../core'
import type { ConversationAction } from '../core/conversation'
import { preloadPlatform } from './lazyPlatform'
import { createVoiceController, type VoiceController, type VoiceDeps } from './voiceController'

/** 대화 중(대기 외 상태)에는 화면을 켜 둔다. 화면이 다시 보이면 다시 요청한다(가려지면 풀린다) */
function useWakeLock(active: boolean) {
  useEffect(() => {
    if (!active || !('wakeLock' in navigator)) return
    let lock: WakeLockSentinel | null = null
    let released = false
    const request = () => {
      if (document.visibilityState !== 'visible') return
      navigator.wakeLock
        .request('screen')
        .then((sentinel) => {
          if (released) void sentinel.release()
          else lock = sentinel
        })
        .catch(() => {}) // 배터리 절약 모드 등에서는 거절된다
    }
    request()
    document.addEventListener('visibilitychange', request)
    return () => {
      released = true
      document.removeEventListener('visibilitychange', request)
      void lock?.release().catch(() => {})
    }
  }, [active])
}

/** 이어폰·잠금 화면의 재생/일시정지 버튼을 버튼 한 번(tap)으로 받는다. 재생 중에만 브라우저가 넘겨준다 */
function useMediaSession(active: boolean, onTap: () => void) {
  useEffect(() => {
    if (!active || !('mediaSession' in navigator)) return
    const session = navigator.mediaSession
    for (const action of ['play', 'pause'] as const) {
      try {
        session.setActionHandler(action, onTap)
      } catch {
        // 지원하지 않는 동작
      }
    }
    return () => {
      for (const action of ['play', 'pause'] as const) {
        try {
          session.setActionHandler(action, null)
        } catch {
          // 지원하지 않는 동작
        }
      }
    }
  }, [active, onTap])
}

export function useVoiceConversation(
  dispatch: (action: ConversationAction) => void,
  deps?: Partial<VoiceDeps>,
) {
  const [machine, setMachine] = useState<SessionState>(initialSession)
  const controller = useRef<VoiceController | null>(null)
  const [initialDeps] = useState(deps) // 처음 받은 의존성으로 고정한다(테스트용)
  // 음성 모듈을 불러왔는지(null: 불러오는 중, false: 실패). 다 불러오기 전에는 시작 버튼을 막는다
  const [ready, setReady] = useState<boolean | null>(null)

  useEffect(() => {
    let alive = true
    void preloadPlatform().then((loaded) => alive && setReady(loaded))
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    const current = createVoiceController({ dispatch, onState: setMachine, deps: initialDeps })
    controller.current = current
    return () => {
      controller.current = null
      setMachine(initialSession)
      void current.dispose()
    }
  }, [dispatch, initialDeps])

  const tap = useCallback(() => controller.current?.tap(), [])
  const longPress = useCallback(() => controller.current?.longPress(), [])
  const active = machine.name !== 'idle'
  useWakeLock(active)
  useMediaSession(active, tap)
  return { machine, tap, longPress, ready }
}
