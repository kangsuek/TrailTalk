import { describe, expect, it } from 'vitest'
import { addInterest, changedFields, draftOf, MAX_INTERESTS, type ProfileFields } from './settings'

const PROFILE: ProfileFields = {
  nickname: '다니엘님',
  interests: ['등산'],
  voice: null,
  speaking_rate: null,
  keep_audio: false,
}

describe('설정 규칙', () => {
  it('바뀐 필드만 담는다(호칭을 비우면 기본 호칭 null)', () => {
    expect(changedFields(PROFILE, draftOf(PROFILE))).toEqual({})
    const draft = { ...draftOf(PROFILE), nickname: '  ', voice: 'coral', speakingRate: 1.2, keepAudio: true }
    expect(changedFields(PROFILE, draft)).toEqual({ nickname: null, voice: 'coral', speaking_rate: 1.2, keep_audio: true })
    expect(changedFields(PROFILE, { ...draftOf(PROFILE), interests: ['등산', '앱'] })).toEqual({ interests: ['등산', '앱'] })
    expect(changedFields(PROFILE, { ...draftOf(PROFILE), nickname: ' 다니엘님 ' })).toEqual({})
  })

  it('관심사는 빈 값·중복·길이·개수를 막는다', () => {
    expect(addInterest(['등산'], '  앱 ')).toEqual({ interests: ['등산', '앱'] })
    expect(addInterest(['등산'], ' ')).toHaveProperty('error')
    expect(addInterest(['등산'], '등산')).toHaveProperty('error')
    expect(addInterest([], '가'.repeat(31))).toHaveProperty('error')
    const full = Array.from({ length: MAX_INTERESTS }, (_, i) => `관심${i}`)
    expect(addInterest(full, '하나 더')).toHaveProperty('error')
  })
})
