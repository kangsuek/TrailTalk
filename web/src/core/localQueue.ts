// 오프라인 큐(LocalQueue) 약속과 메모리 구현(설계서 4.1·4.8, 계획서 S3-12, 클라이언트 규약 4절).
// 연결이 끊긴 동안 한 말을 보관했다가 연결되면 순서대로 보낸다. 브라우저 구현은 src/platform/localQueue.ts
// (IndexedDB). UI·브라우저 API에 의존하지 않는다.

export interface QueuedUtterance {
  id: string
  sessionId: string // 이 말을 한 대화. 다른 대화의 남은 말은 대답 없이 기록만 남긴다
  mimeType: string
  bytes: Uint8Array<ArrayBuffer>
  createdAt: number // 보관한 시각(ms, 순서를 정한다)
  attempts: number // 보내다 실패한 횟수
  recordOnly?: boolean // 대답을 포기하고 기록만 남길 말(보통 전송에서 뺀다)
  recordAttempts?: number // 기록만 남기기에 실패한 횟수
}

export interface LocalQueue {
  add(item: QueuedUtterance): Promise<void>
  /** 이 대화에서 가장 먼저 보관한 말(기록만 남길 말은 빼고) */
  oldest(sessionId: string): Promise<QueuedUtterance | null>
  remove(id: string): Promise<void>
  /** 이 대화에서 보낼 말 수(기록만 남길 말은 빼고) */
  count(sessionId: string): Promise<number>
  /** 기록만 남길 말: 이 대화가 아닌(이전 대화의) 남은 말과 기록만 표시한 말, 오래된 것부터.
   * sessionId가 null이면 전부 */
  others(sessionId: string | null): Promise<QueuedUtterance[]>
  update(id: string, change: Partial<Pick<QueuedUtterance, 'attempts' | 'recordOnly' | 'recordAttempts'>>): Promise<void>
}

/** 보통 전송(캐릭터가 대답)할 이 대화의 말인가 */
export function sendable(item: QueuedUtterance, sessionId: string): boolean {
  return item.sessionId === sessionId && !item.recordOnly
}

/** 기록만 남길 말인가 */
export function recordable(item: QueuedUtterance, exclude: string | null): boolean {
  return item.sessionId !== exclude || Boolean(item.recordOnly)
}

/** 보관 순서: 보관 시각, 같으면 id */
export function byCreated(a: QueuedUtterance, b: QueuedUtterance): number {
  return a.createdAt - b.createdAt || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
}

/** 메모리 큐. 새로 고치면 사라진다(저장소를 쓸 수 없을 때의 대체, 테스트) */
export function createMemoryQueue(): LocalQueue {
  const items = new Map<string, QueuedUtterance>()
  const sorted = () => [...items.values()].sort(byCreated)
  return {
    async add(item) {
      items.set(item.id, item)
    },
    async oldest(sessionId) {
      return sorted().find((item) => sendable(item, sessionId)) ?? null
    },
    async remove(id) {
      items.delete(id)
    },
    async count(sessionId) {
      return sorted().filter((item) => sendable(item, sessionId)).length
    },
    async others(sessionId) {
      return sorted().filter((item) => recordable(item, sessionId))
    },
    async update(id, change) {
      const item = items.get(id)
      if (item) items.set(id, { ...item, ...change })
    },
  }
}
