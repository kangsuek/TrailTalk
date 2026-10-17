import { describe, expect, it } from 'vitest'
import { boldSegments, citeLabel, isWebUrl, searchUrl } from './report'

describe('report', () => {
  it('**굵게** 짝만 굵게 나누고 나머지는 글자로 둔다', () => {
    expect(boldSegments('**A**가 **3월**부터 바뀜')).toEqual([
      { text: 'A', bold: true },
      { text: '가 ', bold: false },
      { text: '3월', bold: true },
      { text: '부터 바뀜', bold: false },
    ])
    expect(boldSegments('별표 * 하나와 **닫히지 않음')).toEqual([{ text: '별표 * 하나와 **닫히지 않음', bold: false }])
    expect(boldSegments('')).toEqual([])
  })

  it('출처 번호와 검색 주소를 만든다', () => {
    expect(citeLabel([1, 2])).toBe('[1][2]')
    expect(citeLabel([])).toBe('')
    expect(isWebUrl('https://a.example/b')).toBe(true)
    expect(isWebUrl('javascript:alert(1)')).toBe(false)
    expect(searchUrl('Claude Code & uv')).toBe('https://www.google.com/search?q=Claude%20Code%20%26%20uv')
  })
})
