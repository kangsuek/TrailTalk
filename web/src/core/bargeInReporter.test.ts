import { describe, expect, it, vi } from 'vitest'
import { createBargeInReporter, MAX_STORED, STORAGE_KEY, type BargeInRecord, type KeyValueStore } from './bargeInReporter'

const rec = (id: string): BargeInRecord => ({
  id,
  session_id: 's1',
  turn_id: 't1',
  occurred_at: '2026-10-20T05:00:00.000Z',
  result: 'real',
})

function memoryStore(): KeyValueStore & { data: Map<string, string> } {
  const data = new Map<string, string>()
  return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v) }
}
const stored = (store: ReturnType<typeof memoryStore>): BargeInRecord[] =>
  JSON.parse(store.data.get(STORAGE_KEY) ?? '[]')

describe('createBargeInReporter', () => {
  it('기록을 올리고 올린 것은 기기에서 지운다', async () => {
    const store = memoryStore()
    const upload = vi.fn().mockResolvedValue(undefined)
    const reporter = createBargeInReporter(store, upload)
    reporter.record(rec('a'))
    await reporter.flush()
    expect(upload).toHaveBeenCalledWith([rec('a')])
    expect(stored(store)).toEqual([])
  })

  it('올리지 못하면 남겨 두고 다음 flush에 다시 올린다', async () => {
    const store = memoryStore()
    const upload = vi.fn().mockRejectedValue(new Error('offline'))
    const reporter = createBargeInReporter(store, upload)
    reporter.record(rec('a'))
    await reporter.flush()
    expect(stored(store).map((r) => r.id)).toEqual(['a'])
    upload.mockResolvedValue(undefined) // 연결이 돌아왔다
    reporter.record(rec('b'))
    await reporter.flush()
    expect(upload).toHaveBeenLastCalledWith([rec('a'), rec('b')])
    expect(stored(store)).toEqual([])
  })

  it('올리는 중에 모인 기록은 남겼다가 이어서 올린다', async () => {
    const store = memoryStore()
    let release: () => void = () => {}
    const upload = vi
      .fn()
      .mockImplementationOnce(() => new Promise<void>((resolve) => (release = resolve)))
      .mockResolvedValue(undefined)
    const reporter = createBargeInReporter(store, upload)
    reporter.record(rec('a'))
    reporter.record(rec('b'))
    expect(upload).toHaveBeenCalledTimes(1)
    release()
    await reporter.flush()
    expect(upload.mock.calls.map(([batch]) => batch.map((r: BargeInRecord) => r.id))).toEqual([['a'], ['b']])
    expect(stored(store)).toEqual([])
  })

  it('저장소가 없거나 깨졌어도 메모리로 동작한다', async () => {
    const upload = vi.fn().mockRejectedValue(new Error('offline'))
    const reporter = createBargeInReporter(null, upload)
    reporter.record(rec('a'))
    await reporter.flush()
    upload.mockResolvedValue(undefined)
    await reporter.flush()
    expect(upload).toHaveBeenLastCalledWith([rec('a')])
    const broken: KeyValueStore = {
      getItem: () => '{not json',
      setItem: () => {
        throw new Error('quota')
      },
    }
    const other = createBargeInReporter(broken, vi.fn().mockResolvedValue(undefined))
    expect(() => other.record(rec('x'))).not.toThrow()
    await other.flush()
  })

  it(`${MAX_STORED}개를 넘으면 오래된 것부터 버린다`, async () => {
    const store = memoryStore()
    const reporter = createBargeInReporter(store, () => Promise.reject(new Error('offline')))
    for (let i = 0; i < MAX_STORED + 5; i++) reporter.record(rec(`e${i}`))
    await reporter.flush()
    const ids = stored(store).map((r) => r.id)
    expect(ids).toHaveLength(MAX_STORED)
    expect(ids[0]).toBe('e5')
  })
})
