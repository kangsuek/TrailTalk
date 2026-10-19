import { describe, expect, it } from 'vitest'
import { addInterest, changedFields, draftOf, isValidEmail, MAX_INTERESTS, type ProfileFields } from './settings'

const PROFILE: ProfileFields = {
  nickname: '다니엘님',
  email: null,
  interests: ['등산'],
  voice: null,
  speaking_rate: null,
  keep_audio: false,
  chat_model: null,
}

describe('설정 규칙', () => {
  it('바뀐 필드만 담는다(호칭을 비우면 기본 호칭 null)', () => {
    expect(changedFields(PROFILE, draftOf(PROFILE))).toEqual({})
    const draft = { ...draftOf(PROFILE), nickname: '  ', voice: 'coral', speakingRate: 1.2, keepAudio: true }
    expect(changedFields(PROFILE, draft)).toEqual({ nickname: null, voice: 'coral', speaking_rate: 1.2, keep_audio: true })
    expect(changedFields(PROFILE, { ...draftOf(PROFILE), interests: ['등산', '앱'] })).toEqual({ interests: ['등산', '앱'] })
    expect(changedFields(PROFILE, { ...draftOf(PROFILE), nickname: ' 다니엘님 ' })).toEqual({})
    expect(changedFields(PROFILE, { ...draftOf(PROFILE), chatModel: 'opus' })).toEqual({ chat_model: 'opus' })
    const opus = { ...PROFILE, chat_model: 'opus' as const }
    expect(changedFields(opus, { ...draftOf(opus), chatModel: null })).toEqual({ chat_model: null }) // 기본으로
  })

  it('이메일은 앞뒤 공백을 빼고 비우면 null로 보낸다', () => {
    expect(changedFields(PROFILE, { ...draftOf(PROFILE), email: ' me@example.com ' })).toEqual({ email: 'me@example.com' })
    const saved = { ...PROFILE, email: 'me@example.com' }
    expect(changedFields(saved, draftOf(saved))).toEqual({})
    expect(changedFields(saved, { ...draftOf(saved), email: '  ' })).toEqual({ email: null })
  })

  it('이메일 모양을 확인한다(빈 값은 설정 안 함이라 통과)', () => {
    for (const ok of ['', '  ', 'me@example.com', 'a.b+c@mail.example.co.kr']) expect(isValidEmail(ok)).toBe(true)
    for (const bad of ['plain', 'a@b', 'a b@example.com', '@example.com', 'a@example.com,b@example.com', '한글@example.com']) {
      expect(isValidEmail(bad)).toBe(false)
    }
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
