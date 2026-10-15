import { describe, expect, it } from 'vitest'
import { countsLabel, dateLabel, groupByDate, journalStatusLabel } from './journal'

describe('journal', () => {
  it('같은 날짜끼리 받은 순서대로 묶는다', () => {
    const items = [
      { id: 'a', date: '2026-10-15' },
      { id: 'b', date: '2026-10-15' },
      { id: 'c', date: '2026-10-13' },
    ]
    expect(groupByDate(items)).toEqual([
      { date: '2026-10-15', items: [items[0], items[1]] },
      { date: '2026-10-13', items: [items[2]] },
    ])
    expect(groupByDate([])).toEqual([])
  })

  it('날짜를 월·일·요일로 보인다(시간대와 무관)', () => {
    expect(dateLabel('2026-10-15')).toBe('10월 15일 (목)')
    expect(dateLabel('2026-01-04')).toBe('1월 4일 (일)')
    expect(dateLabel('엉뚱한 값')).toBe('엉뚱한 값')
  })

  it('종류별 개수는 있는 것만 보인다', () => {
    expect(countsLabel({ idea: 2, todo: 0, memo: 1 })).toBe('아이디어 2 · 메모 1')
    expect(countsLabel({ idea: 0, todo: 0, memo: 0 })).toBe('')
  })

  it('정리 상태 안내', () => {
    expect(journalStatusLabel('done', 'ended')).toBeNull()
    expect(journalStatusLabel('pending', 'ended')).toBe('정리 중')
    expect(journalStatusLabel('failed', 'ended')).toBe('정리 실패')
    expect(journalStatusLabel(null, 'active')).toBe('대화 중')
  })
})
