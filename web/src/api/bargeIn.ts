// 끼어들기 기록 업로드(POST /api/barge-in-events, V2-M0-05). 타입은 schema.d.ts(npm run gen:api).
import type { components } from './schema'
import { ApiError, request } from './http'

export type BargeInRecord = components['schemas']['BargeInEventIn']

/** 기기에 모은 기록을 올린다. 서버는 id가 같은 기록을 건너뛰므로 다시 올려도 안전하다 */
export async function uploadBargeInEvents(events: BargeInRecord[], signal?: AbortSignal): Promise<void> {
  try {
    await request('/api/barge-in-events', 'POST', { events }, signal)
  } catch (error) {
    // 서버가 형식을 거절한 배치(4xx)는 다시 올려도 같다: 성공으로 보고 기기에서 지워 뒤 기록을 막지 않는다
    if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429) {
      return
    }
    throw error
  }
}
