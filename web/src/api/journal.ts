// 일지·노트 API(docs/client-contract.md 2절 "일지 API"). 타입은 서버 OpenAPI에서 생성한 schema.d.ts를 쓴다.
import { request } from './http'
import type { components } from './schema'

export type JournalItem = components['schemas']['JournalItem']
export type JournalDetail = components['schemas']['JournalDetail']
export type NoteOut = components['schemas']['NoteOut']
export type NotePatch = components['schemas']['NotePatch']

/** 일지 목록(최신순). 날짜를 주지 않으면 서버 기본값(최근 30일)이다. */
export async function listJournal(signal?: AbortSignal): Promise<JournalItem[]> {
  return (await request('/api/journal', 'GET', undefined, signal)).json()
}

export async function getJournal(sessionId: string, signal?: AbortSignal): Promise<JournalDetail> {
  return (await request(`/api/journal/${encodeURIComponent(sessionId)}`, 'GET', undefined, signal)).json()
}

/** 보낸 필드만 바꾸고 바뀐 노트를 돌려준다. */
export async function updateNote(noteId: string, patch: NotePatch, signal?: AbortSignal): Promise<NoteOut> {
  return (await request(`/api/notes/${encodeURIComponent(noteId)}`, 'PATCH', patch, signal)).json()
}

/** 정리에 실패한(또는 정리 기록이 없는) 끝난 대화를 다시 정리한다. 정리 중이면 pending 항목이 온다. */
export async function retryJournal(sessionId: string, signal?: AbortSignal): Promise<JournalItem> {
  return (await request(`/api/journal/${encodeURIComponent(sessionId)}/retry`, 'POST', undefined, signal)).json()
}
