import { usageView, type UsageLimits } from '../core/usage'

const WINDOW_NAMES = { five_hour: '5시간', seven_day: '7일' } as const

/** 헤더 아래 "Claude 남은 토큰" 막대(디자인 시안). 첫 답변 전에는 값이 없어 막대를 비운다 */
export function UsageMeter({ limits, now }: { limits: UsageLimits | null; now: Date }) {
  const view = usageView(limits, now)
  const known = view.remaining !== null
  const valueText = known
    ? `${WINDOW_NAMES[view.window!]} 한도 ${view.remaining}% 남음${view.reset ? `, ${view.reset}` : ''}`
    : '대화하면 표시'
  return (
    <div
      className="usage-meter"
      data-level={view.level}
      role="meter"
      aria-label="Claude 남은 토큰"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={view.remaining ?? undefined}
      aria-valuetext={valueText}
    >
      <span className="usage-label">Claude 남은 토큰</span>
      <span className="usage-bar" aria-hidden="true">
        <span style={{ width: `${view.remaining ?? 0}%` }} />
      </span>
      {known ? (
        <>
          <span className="usage-value">{view.remaining}%</span>
          {view.reset && <span className="usage-reset">{view.reset}</span>}
        </>
      ) : (
        <span className="usage-reset">대화하면 표시</span>
      )}
    </div>
  )
}
