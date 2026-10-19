// 일지 화면의 표시 규칙. 날짜(date)는 서버가 현지 날짜로 주므로 여기서는 시간대 계산을 하지 않는다.
// UI·브라우저 API에 의존하지 않는다.

const WEEKDAYS = '일월화수목금토'

// 정리 중(pending)인 일지가 있으면 이 간격으로 다시 불러온다(화면마다 최대 MAX_POLLS번, 약 2분)
export const POLL_MS = 3_000
export const MAX_POLLS = 40

export interface DateGroup<T> {
  date: string
  items: T[]
}

/** 받은 순서(최신순)를 지키며 같은 날짜끼리 묶는다. */
export function groupByDate<T extends { date: string }>(items: T[]): DateGroup<T>[] {
  const groups: DateGroup<T>[] = []
  for (const item of items) {
    const last = groups.at(-1)
    if (last && last.date === item.date) last.items.push(item)
    else groups.push({ date: item.date, items: [item] })
  }
  return groups
}

/** 'YYYY-MM-DD' → '10월 15일 (목)'. 형식이 다르면 그대로 돌려준다. */
export function dateLabel(date: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  if (!match) return date
  const [year, month, day] = match.slice(1).map(Number)
  const weekday = WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()]
  return `${month}월 ${day}일 (${weekday})`
}

export interface NoteCounts {
  idea: number
  todo: number
  memo: number
}

/** 종류별 개수 한 줄. 없는 종류는 뺀다(모두 없으면 빈 문자열). */
export function countsLabel(counts: NoteCounts): string {
  const parts: [string, number][] = [
    ['아이디어', counts.idea],
    ['할 일', counts.todo],
    ['메모', counts.memo],
  ]
  return parts
    .filter(([, n]) => n > 0)
    .map(([label, n]) => `${label} ${n}`)
    .join(' · ')
}

export type JournalStatus = 'pending' | 'done' | 'failed' | null

/** 일지 정리 상태 안내. 정상(done)이면 null. */
export function journalStatusLabel(status: JournalStatus, sessionStatus: string): string | null {
  if (status === null) return sessionStatus === 'ended' ? null : '대화 중'
  if (status === 'pending') return '정리 중'
  if (status === 'failed') return '정리 실패'
  return null
}
