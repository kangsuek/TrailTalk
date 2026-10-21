import { describe, expect, it } from 'vitest'
import {
  DEFAULT_ATTACHMENT_LIMITS as L,
  attachmentHint,
  attachmentKind,
  attachmentUrl,
  checkAttachments,
} from './attachments'

describe('attachments', () => {
  it('classifies by extension, case-insensitively', () => {
    expect(attachmentKind('A.JPG', L)).toBe('image')
    expect(attachmentKind('notes.md', L)).toBe('text')
    expect(attachmentKind('run.exe', L)).toBeNull()
    expect(attachmentKind('noext', L)).toBeNull()
  })

  it('accepts files within limits', () => {
    expect(checkAttachments([{ name: 'a.png', size: 1000 }, { name: 'b.txt', size: 10 }], L)).toBeNull()
  })

  it('rejects too many files', () => {
    const files = Array.from({ length: 4 }, (_, i) => ({ name: `${i}.txt`, size: 1 }))
    expect(checkAttachments(files, L)).toContain('3개')
  })

  it('rejects unsupported types and oversize files', () => {
    expect(checkAttachments([{ name: 'a.exe', size: 1 }], L)).toContain('지원하지 않는')
    expect(checkAttachments([{ name: 'a.png', size: 6 * 1024 * 1024 }], L)).toContain('5MB')
    expect(checkAttachments([{ name: 'a.txt', size: 201 * 1024 }], L)).toContain('200KB')
  })

  it('hints when files are attached without a question', () => {
    expect(attachmentHint('  ', 1)).not.toBeNull()
    expect(attachmentHint('질문', 1)).toBeNull()
    expect(attachmentHint('', 0)).toBeNull()
  })

  it('builds urls', () => {
    expect(attachmentUrl('abc')).toBe('/api/attachments/abc')
    expect(attachmentUrl('abc', true)).toBe('/api/attachments/abc?thumb=1')
  })
})
