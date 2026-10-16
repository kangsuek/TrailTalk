// LocalQueue 브라우저 구현(계획서 S3-12): IndexedDB에 녹음을 보관한다. 새로 고치거나 브라우저를 다시
// 열어도 남는다. IndexedDB를 쓸 수 없으면(사생활 보호 모드 등) 메모리로 대신한다(새로 고치면 사라진다).
import {
  byCreated,
  createMemoryQueue,
  recordable,
  sendable,
  type LocalQueue,
  type QueuedUtterance,
} from '../core/localQueue'

const DB_NAME = 'trailtalk'
const STORE = 'utterances'

function promised<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: 'id' })
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('IndexedDB blocked'))
  })
}

function indexedQueue(db: IDBDatabase): LocalQueue {
  const store = (mode: IDBTransactionMode) => db.transaction(STORE, mode).objectStore(STORE)
  const all = async () => ((await promised(store('readonly').getAll())) as QueuedUtterance[]).sort(byCreated)
  return {
    async add(item) {
      await promised(store('readwrite').put(item))
    },
    async oldest(sessionId) {
      return (await all()).find((item) => sendable(item, sessionId)) ?? null
    },
    async remove(id) {
      await promised(store('readwrite').delete(id))
    },
    async count(sessionId) {
      return (await all()).filter((item) => sendable(item, sessionId)).length
    },
    async others(sessionId) {
      return (await all()).filter((item) => recordable(item, sessionId))
    },
    async update(id, change) {
      const item = (await promised(store('readonly').get(id))) as QueuedUtterance | undefined
      if (item) await promised(store('readwrite').put({ ...item, ...change }))
    },
  }
}

/** IndexedDB 큐(못 쓰면 메모리 큐). 여는 동안 온 호출은 연 뒤에 실행한다.
 * 넣기가 실패하면(용량 초과 등) 그 말은 메모리에 둔다(말을 잃지 않게). 읽기·지우기·고치기는 두 곳을
 * 모두 본다(한 번의 오류로 IndexedDB에 남은 말이 안 보이거나, 지운 말이 남아 다시 보내지지 않게) */
export function createLocalQueue(): LocalQueue {
  const memory = createMemoryQueue()
  const indexed: Promise<LocalQueue | null> =
    typeof indexedDB === 'undefined' ? Promise.resolve(null) : open().then(indexedQueue, () => null)
  // IndexedDB 쪽 결과(실패하면 비어 있는 것으로 보고 메모리 쪽만 쓴다)
  const fromIndexed = async <R>(op: (queue: LocalQueue) => Promise<R>, empty: R): Promise<R> => {
    const queue = await indexed
    if (queue === null) return empty
    try {
      return await op(queue)
    } catch (error) {
      console.warn('보관함(IndexedDB) 오류', error)
      return empty
    }
  }
  const merged = async (sessionFilter: (queue: LocalQueue) => Promise<QueuedUtterance[]>) =>
    [...(await fromIndexed(sessionFilter, [])), ...(await sessionFilter(memory))].sort(byCreated)
  return {
    async add(item) {
      const queue = await indexed
      try {
        if (queue === null) throw new Error('IndexedDB 없음')
        await queue.add(item)
      } catch (error) {
        if (queue !== null) console.warn('보관함(IndexedDB)에 넣지 못해 메모리에 둡니다', error)
        await memory.add(item)
      }
    },
    async oldest(sessionId) {
      const candidates = [
        await fromIndexed((queue) => queue.oldest(sessionId), null),
        await memory.oldest(sessionId),
      ].filter((item): item is QueuedUtterance => item !== null)
      return candidates.sort(byCreated)[0] ?? null
    },
    async remove(id) {
      await Promise.all([fromIndexed((queue) => queue.remove(id), undefined), memory.remove(id)])
    },
    async count(sessionId) {
      return (await fromIndexed((queue) => queue.count(sessionId), 0)) + (await memory.count(sessionId))
    },
    others: (sessionId) => merged((queue) => queue.others(sessionId)),
    async update(id, change) {
      await Promise.all([fromIndexed((queue) => queue.update(id, change), undefined), memory.update(id, change)])
    },
  }
}
