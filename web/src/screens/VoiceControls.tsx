// 음성 대화의 큰 버튼과 상태 표시(계획서 S3-13, 설계서 4.1 웹 열).
// 한 번 누르기 = 시작·끼어들기·쉬기 재개(tap), 길게 누르기 = 종료(long_press).
import { useRef, type PointerEvent } from 'react'
import type { SessionStateName } from '../core'

const LONG_PRESS_MS = 700

const STATUS: Record<SessionStateName, { label: string; hint: string }> = {
  idle: { label: '대기', hint: '' },
  listening: { label: '듣고 있어요', hint: '말씀하세요. 길게 누르면 대화를 마쳐요.' },
  processing: { label: '생각하는 중…', hint: '누르면 이번 답변을 그만 듣고 다시 말할 수 있어요.' },
  speaking: { label: '말하는 중', hint: '누르거나 말을 시작하면 끊고 말할 수 있어요.' },
  paused: { label: '쉬는 중', hint: '누르면 다시 들어요. 30분 동안 말이 없으면 대화를 마쳐요.' },
  offline: { label: '연결이 끊겼어요', hint: '말은 보관해 두었다가 연결되면 보내요.' },
  closing: { label: '일지로 정리하는 중…', hint: '마무리 멘트를 기다리고 있어요.' },
}

export function VoiceControls({
  state,
  connecting,
  queued = 0,
  onTap,
  onLongPress,
}: {
  state: SessionStateName
  connecting: boolean // 시작 응답을 기다리는 중
  queued?: number // 연결이 끊겨 보관한 말 수(S3-12)
  onTap: () => void
  onLongPress: () => void
}) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const longFired = useRef(false)
  const status = connecting ? { label: '연결하는 중…', hint: '' } : STATUS[state]

  const cancelTimer = () => {
    clearTimeout(timer.current)
    timer.current = undefined
  }
  // 포인터는 길게 누르기만 판정한다. 한 번 누르기는 click으로 받는다(키보드·스크린리더도 click만 보낸다)
  const onPointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return
    longFired.current = false
    cancelTimer()
    timer.current = setTimeout(() => {
      timer.current = undefined
      longFired.current = true
      onLongPress()
    }, LONG_PRESS_MS)
  }
  const onClick = () => {
    if (longFired.current) {
      longFired.current = false // 길게 누르기 뒤에 오는 click은 무시한다
      return
    }
    onTap()
  }

  return (
    <div className="voice-controls" data-state={state}>
      <button
        type="button"
        className="voice-button"
        aria-label={`${status.label}. 누르기: 시작·끊기, 길게 누르기: 대화 끝내기`}
        disabled={state === 'closing'}
        onClick={onClick}
        onPointerDown={onPointerDown}
        onPointerUp={cancelTimer}
        onPointerLeave={cancelTimer}
        onPointerCancel={cancelTimer}
        onContextMenu={(event) => event.preventDefault()} // 휴대폰 길게 누르기 메뉴를 막는다
      >
        <span className="voice-dot" aria-hidden="true" />
      </button>
      <p className="voice-status" role="status" aria-live="polite">
        {status.label}
      </p>
      {status.hint && <p className="voice-hint">{status.hint}</p>}
      {queued > 0 && (
        <p className="voice-hint" data-testid="queued">
          보관한 말 {queued}개 · 연결되면 차례로 보내요
        </p>
      )}
      {/* 정리 중에는 끝내기 응답을 기다리지 않고 나오는 탈출구(서버 끝내기는 멱등이다) */}
      <button type="button" className="secondary" onClick={onLongPress}>
        {state === 'closing' ? '그만 기다리기' : '대화 끝내기'}
      </button>
    </div>
  )
}
