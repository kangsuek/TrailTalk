// 끼어들기 기록을 기기에 모았다가 서버에 올린다(V2-M0-05). 올리지 못하면 남겨 두고 다음에 다시 올린다.
// 저장소(localStorage)·업로드는 주입받는다(브라우저 API 비의존). 서버는 id가 같은 기록을 건너뛴다.
export interface BargeInRecord {
  id: string
  session_id: string
  turn_id: string
  occurred_at: string // ISO 시각(기기 시계)
  probe_to_confirm_ms?: number | null
  stop_ms?: number | null
  played_ratio?: number | null
  result: string // real·suspected_false·probe_reverted·user_marked_false (docs/V2/metrics-hook.md)
  next_turn_id?: string | null
}

export interface KeyValueStore {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export interface BargeInReporter {
  /** 기록을 기기에 모으고 올려 본다 */
  record(record: BargeInRecord): void
  /** 모인 기록을 올려 본다(대화를 시작할 때 이전에 못 올린 것을 올린다) */
  flush(): Promise<void>
}

export const STORAGE_KEY = 'tt.bargeInEvents'
export const MAX_STORED = 200 // 서버 배치 상한과 같다. 넘치면 오래된 것부터 버린다

export function createBargeInReporter(
  store: KeyValueStore | null,
  upload: (events: BargeInRecord[]) => Promise<void>,
): BargeInReporter {
  let memory: BargeInRecord[] = [] // 저장소를 못 쓸 때(시크릿 창 등)는 이 탭이 열려 있는 동안만 모은다
  let flushing: Promise<void> | null = null
  let again = false

  // 저장소(다른 탭이 넣은 기록 포함)와 이 탭의 메모리를 id로 합친다: 저장소 쓰기가 실패해도 기록이 사라지지 않는다
  const load = (): BargeInRecord[] => {
    let stored: BargeInRecord[] = []
    if (store !== null) {
      try {
        const parsed: unknown = JSON.parse(store.getItem(STORAGE_KEY) ?? '[]')
        if (Array.isArray(parsed)) stored = parsed as BargeInRecord[]
      } catch {
        // 깨진 값은 메모리로 대신한다
      }
    }
    const ids = new Set(stored.map((item) => item.id))
    return [...stored, ...memory.filter((item) => !ids.has(item.id))].slice(-MAX_STORED)
  }

  const save = (records: BargeInRecord[]) => {
    memory = records
    if (store === null) return
    try {
      store.setItem(STORAGE_KEY, JSON.stringify(records))
    } catch {
      // 저장소가 가득 찼거나 막혔다: 메모리에만 둔다
    }
  }

  const run = async () => {
    const batch = load().slice(0, MAX_STORED)
    if (batch.length === 0) return
    try {
      await upload(batch)
    } catch {
      return // 남겨 두고 다음에 다시 올린다
    }
    const sent = new Set(batch.map((item) => item.id))
    save(load().filter((item) => !sent.has(item.id))) // 올리는 사이 새로 모인 기록은 남긴다
  }

  const flush = (): Promise<void> => {
    if (flushing !== null) {
      again = true // 올리는 중에 모인 기록은 이번 업로드 뒤에 한 번 더
      return flushing
    }
    flushing = (async () => {
      try {
        do {
          again = false
          await run()
        } while (again)
      } finally {
        flushing = null
      }
    })()
    return flushing
  }

  return {
    record(record) {
      save([...load(), record].slice(-MAX_STORED))
      void flush()
    },
    flush,
  }
}
