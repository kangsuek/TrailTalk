import { describe, expect, it } from 'vitest'
import { citeLabel, isWebUrl } from './citations'

describe('citations', () => {
  it('출처 번호를 [1][2]로 붙이고, 웹 주소만 링크로 연다', () => {
    expect(citeLabel([1, 2])).toBe('[1][2]')
    expect(citeLabel([])).toBe('')
    expect(isWebUrl('https://a.example/b')).toBe(true)
    expect(isWebUrl('HTTP://a.example')).toBe(true)
    expect(isWebUrl('javascript:alert(1)')).toBe(false)
  })
})
