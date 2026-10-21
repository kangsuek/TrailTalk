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

/** 대화 제목을 고치고 바뀐 목록 항목을 돌려준다. 고친 제목은 일지를 다시 정리해도 남는다. */
export async function renameJournal(sessionId: string, title: string, signal?: AbortSignal): Promise<JournalItem> {
  return (await request(`/api/journal/${encodeURIComponent(sessionId)}`, 'PATCH', { title }, signal)).json()
}

/** 대화를 지운다(노트·전문 포함). 진행 중인 대화는 409 session_active. */
export async function deleteJournal(sessionId: string, signal?: AbortSignal): Promise<void> {
  await request(`/api/journal/${encodeURIComponent(sessionId)}`, 'DELETE', undefined, signal)
}

/** 보낸 필드만 바꾸고 바뀐 노트를 돌려준다. */
export async function updateNote(noteId: string, patch: NotePatch, signal?: AbortSignal): Promise<NoteOut> {
  return (await request(`/api/notes/${encodeURIComponent(noteId)}`, 'PATCH', patch, signal)).json()
}

/** 정리에 실패한(또는 정리 기록이 없는) 끝난 대화를 다시 정리한다. 정리 중이면 pending 항목이 온다. */
export async function retryJournal(sessionId: string, signal?: AbortSignal): Promise<JournalItem> {
  return (await request(`/api/journal/${encodeURIComponent(sessionId)}/retry`, 'POST', undefined, signal)).json()
}

export type OpenIdea = components['schemas']['OpenIdea']

/** 대화 시작 화면 목록의 지난 아이디어(완료하지 않은 것, 만든 날짜 역순). 없으면 빈 목록(S3-39). */
export async function fetchOpenIdeas(signal?: AbortSignal): Promise<OpenIdea[]> {
  return (await request('/api/notes/open-ideas', 'GET', undefined, signal)).json()
}
