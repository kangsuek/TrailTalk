// 프로필 API(docs/client-contract.md 2절 "프로필 API", 5절 클라이언트 설정값).
import { request } from './http'
import type { components } from './schema'

export type Profile = components['schemas']['ProfileOut']
export type ClientConfig = components['schemas']['ClientConfig']

export async function getProfile(signal?: AbortSignal): Promise<Profile> {
  return (await request('/api/profile', 'GET', undefined, signal)).json()
}
