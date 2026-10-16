// 프로필 API(docs/client-contract.md 2절 "프로필 API", 5절 클라이언트 설정값).
import type { ProfilePatch } from '../core/settings'
import { request } from './http'
import type { components } from './schema'

export type Profile = components['schemas']['ProfileOut']
export type ClientConfig = components['schemas']['ClientConfig']

export async function getProfile(signal?: AbortSignal): Promise<Profile> {
  return (await request('/api/profile', 'GET', undefined, signal)).json()
}

export type Voices = components['schemas']['VoicesOut']

/** 보낸 필드만 바꾼다(null이면 기본값으로, 보이스는 getVoices 목록 안의 이름) */
export async function updateProfile(patch: ProfilePatch, signal?: AbortSignal): Promise<Profile> {
  return (await request('/api/profile', 'PUT', patch, signal)).json()
}

/** 설정 화면에서 고를 수 있는 보이스와 캐릭터 기본값 */
export async function getVoices(signal?: AbortSignal): Promise<Voices> {
  return (await request('/api/voices', 'GET', undefined, signal)).json()
}

/** 보이스 미리 듣기 MP3 주소(rate가 null이면 캐릭터 기본 속도) */
export function voiceSampleUrl(voice: string, rate: number | null): string {
  const query = rate === null ? '' : `?rate=${rate}`
  return `/api/voices/${encodeURIComponent(voice)}/sample${query}`
}

