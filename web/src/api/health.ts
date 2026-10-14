// 서버 상태 확인. 응답 타입은 서버 OpenAPI에서 생성한 schema.d.ts를 쓴다(npm run gen:api).
import type { paths } from './schema'

type HealthResponse = paths['/api/health']['get']['responses'][200]['content']['application/json']

export async function fetchHealth(signal?: AbortSignal): Promise<boolean> {
  const response = await fetch('/api/health', { signal })
  if (!response.ok) return false
  const body: HealthResponse = await response.json()
  return body.status === 'ok'
}
