// 서버 API 공통 요청. 실패는 서버 공통 오류 형식(클라이언트 규약 7절) 또는 네트워크 오류로 바꿔 던진다.

/** 서버 공통 오류 형식 또는 네트워크 오류. */
export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

const NETWORK_ERROR = '서버에 연결할 수 없어요.'
const GATEWAY_STATUSES = new Set([502, 503, 504])

/** 서버 API 요청(본문이 있으면 JSON). 응답이 실패면 ApiError를 던진다. */
export async function request(
  path: string,
  method: 'GET' | 'POST' | 'PATCH',
  body?: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError('network_error', NETWORK_ERROR, 0)
  }
  if (!response.ok) throw await errorOf(response)
  return response
}

async function errorOf(response: Response): Promise<ApiError> {
  try {
    const body = await response.json()
    if (body?.error?.code) {
      return new ApiError(body.error.code, body.error.message, response.status)
    }
  } catch {
    // 본문이 JSON이 아니면 상태 코드로만 알린다
  }
  // 개발 프록시·배포 터널은 서버가 꺼져 있으면 JSON 없이 502·503·504를 준다
  if (GATEWAY_STATUSES.has(response.status)) {
    return new ApiError('network_error', NETWORK_ERROR, response.status)
  }
  return new ApiError('http_error', `요청이 실패했어요(${response.status}).`, response.status)
}

