// 서버 API 클라이언트. 1단계부터 OpenAPI 스키마에서 생성한 타입으로 교체한다(계획서 S1-10).
export async function fetchHealth(signal?: AbortSignal): Promise<boolean> {
  const response = await fetch('/api/health', { signal })
  if (!response.ok) return false
  const body: { status?: string } = await response.json()
  return body.status === 'ok'
}
