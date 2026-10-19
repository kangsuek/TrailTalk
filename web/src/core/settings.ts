// 설정 화면 규칙(계획서 S3-18). UI·브라우저 API에 의존하지 않는다.
// 서버 프로필(GET /api/profile)과 화면에서 고친 값을 비교해 바뀐 필드만 PUT으로 보낸다.

/** 대화 모델(S3-31, 서버 CLI --model 별칭) */
export type ChatModel = 'haiku' | 'sonnet' | 'opus'

export interface SettingsDraft {
  nickname: string // 빈 문자열이면 기본 호칭(null)
  interests: string[]
  voice: string | null // null이면 캐릭터 기본 보이스
  speakingRate: number | null // null이면 캐릭터 기본 말 속도
  keepAudio: boolean
  chatModel: ChatModel | null // null이면 서버 기본 모델
}

export interface ProfileFields {
  nickname: string | null
  interests: string[]
  voice: string | null
  speaking_rate: number | null
  keep_audio: boolean
  chat_model: ChatModel | null
}

export type ProfilePatch = Partial<ProfileFields>

export const MAX_INTERESTS = 10
export const MAX_INTEREST_LENGTH = 30
export const MAX_NICKNAME_LENGTH = 20

/** 말 속도 선택지. null은 캐릭터 기본(보통). 실제 TTS 측정(2026-10-17): 느리게 +34%, 빠르게 -21% 길이 */
export const RATE_CHOICES: { label: string; value: number | null }[] = [
  { label: '느리게', value: 0.85 },
  { label: '보통', value: null },
  { label: '빠르게', value: 1.35 },
]

/** 대화 모델 선택지. null은 서버 기본값(화면에 "기본(sonnet)"처럼 보인다) */
export const MODEL_CHOICES: { label: string; value: ChatModel | null }[] = [
  { label: '기본', value: null },
  { label: '빠름(haiku)', value: 'haiku' },
  { label: '균형(sonnet)', value: 'sonnet' },
  { label: '똑똑함(opus)', value: 'opus' },
]

export function draftOf(profile: ProfileFields): SettingsDraft {
  return {
    nickname: profile.nickname ?? '',
    interests: [...profile.interests],
    voice: profile.voice,
    speakingRate: profile.speaking_rate,
    keepAudio: profile.keep_audio,
    chatModel: profile.chat_model,
  }
}

/** 서버 값과 다른 필드만 담는다(없으면 빈 객체) */
export function changedFields(saved: ProfileFields, draft: SettingsDraft): ProfilePatch {
  const patch: ProfilePatch = {}
  const nickname = draft.nickname.trim() || null
  if (nickname !== saved.nickname) patch.nickname = nickname
  if (draft.interests.join('\n') !== saved.interests.join('\n')) patch.interests = [...draft.interests]
  if (draft.voice !== saved.voice) patch.voice = draft.voice
  if (draft.speakingRate !== saved.speaking_rate) patch.speaking_rate = draft.speakingRate
  if (draft.keepAudio !== saved.keep_audio) patch.keep_audio = draft.keepAudio
  if (draft.chatModel !== saved.chat_model) patch.chat_model = draft.chatModel
  return patch
}

/** 관심사를 하나 더한다. 넣을 수 없으면(빈 값·중복·개수 초과) 이유를, 넣었으면 새 목록을 돌려준다 */
export function addInterest(
  interests: string[],
  value: string,
): { interests: string[] } | { error: string } {
  const item = value.trim()
  if (!item) return { error: '관심사를 입력해 주세요.' }
  if (item.length > MAX_INTEREST_LENGTH) return { error: `관심사는 ${MAX_INTEREST_LENGTH}자까지예요.` }
  if (interests.includes(item)) return { error: '이미 있는 관심사예요.' }
  if (interests.length >= MAX_INTERESTS) return { error: `관심사는 ${MAX_INTERESTS}개까지예요.` }
  return { interests: [...interests, item] }
}
