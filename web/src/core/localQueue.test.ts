import { describe, expect, it } from 'vitest'
import { createMemoryQueue, type QueuedUtterance } from './localQueue'

const item = (id: string, sessionId: string, createdAt: number): QueuedUtterance => ({
  id,
  sessionId,
  mimeType: 'audio/webm',
  bytes: new Uint8Array([1]),
  createdAt,
  attempts: 0,
})

describe('메모리 큐', () => {
  it('대화마다 보관한 순서대로 꺼내고, 다른 대화의 말은 따로 모은다', async () => {
    const queue = createMemoryQueue()
    await queue.add(item('b', 's1', 2))
    await queue.add(item('a', 's1', 1))
    await queue.add(item('x', 's0', 0))
    expect((await queue.oldest('s1'))?.id).toBe('a')
    expect(await queue.count('s1')).toBe(2)
    expect((await queue.others('s1')).map((i) => i.id)).toEqual(['x'])
    expect((await queue.others(null)).map((i) => i.id)).toEqual(['x', 'a', 'b'])

    await queue.update('a', { attempts: 1 })
    expect((await queue.oldest('s1'))?.attempts).toBe(1)
    // 기록만 남길 말은 보통 전송에서 빠지고 기록 쪽으로 간다
    await queue.update('b', { recordOnly: true })
    expect(await queue.count('s1')).toBe(1)
    expect((await queue.others('s1')).map((i) => i.id)).toEqual(['x', 'b'])
    await queue.update('b', { recordOnly: false })
    await queue.remove('a')
    expect((await queue.oldest('s1'))?.id).toBe('b')
    expect(await queue.oldest('none')).toBeNull()
  })
})
