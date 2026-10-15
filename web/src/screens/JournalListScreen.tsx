import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/http'
import { listJournal, type JournalItem } from '../api/journal'
import {
  countsLabel,
  dateLabel,
  groupByDate,
  journalStatusLabel,
  MAX_POLLS,
  POLL_MS,
} from '../core/journal'

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; items: JournalItem[] }

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '일지를 불러오지 못했어요.'
}

/** 날짜별 일지 목록(최근 30일). 항목을 누르면 onOpen으로 상세 화면을 연다. */
/** pollMs: 정리 중인 일지를 다시 불러오는 간격(테스트에서 줄인다). */
export function JournalListScreen({
  onOpen = () => {},
  pollMs = POLL_MS,
}: {
  onOpen?: (sessionId: string) => void
  pollMs?: number
}) {
  const [state, setState] = useState<ListState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    listJournal(controller.signal)
      .then((items) => setState({ kind: 'ready', items }))
      .catch((error) => {
        if (!controller.signal.aborted) setState({ kind: 'error', message: errorMessage(error) })
      })
    return () => controller.abort()
  }, [attempt])

  // 정리 중인 일지가 끝나면 목록에 반영한다(조용히 다시 불러오고, 실패해도 다음 차례에 다시 본다)
  const polls = useRef(0)
  const [failures, setFailures] = useState(0) // 실패해도 다음 차례에 다시 보도록 이펙트를 다시 돌린다
  useEffect(() => {
    if (state.kind !== 'ready' || !state.items.some((i) => i.journal_status === 'pending')) return
    if (polls.current >= MAX_POLLS) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      polls.current += 1
      listJournal(controller.signal)
        .then((items) => setState({ kind: 'ready', items }))
        .catch(() => {
          if (!controller.signal.aborted) setFailures((n) => n + 1)
        })
    }, pollMs)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [state, pollMs, failures])

  const retry = () => {
    polls.current = 0
    setState({ kind: 'loading' })
    setAttempt((n) => n + 1)
  }

  return (
    <section className="journal">
      <h2>일지 목록</h2>
      {state.kind === 'loading' && <p className="journal-note">불러오는 중…</p>}
      {state.kind === 'error' && (
        <div className="journal-note">
          <p role="alert">{state.message}</p>
          <button type="button" onClick={retry}>
            다시 불러오기
          </button>
        </div>
      )}
      {state.kind === 'ready' && state.items.length === 0 && (
        <p className="journal-note">아직 일지가 없어요. 대화를 나누면 여기에 정리돼요.</p>
      )}
      {state.kind === 'ready' &&
        groupByDate(state.items).map((group) => (
          <section key={group.date} className="journal-day" aria-label={dateLabel(group.date)}>
            <h3>{dateLabel(group.date)}</h3>
            <ul>
              {group.items.map((item) => {
                const status = journalStatusLabel(item.journal_status, item.status)
                const counts = countsLabel(item.counts)
                return (
                  <li key={item.id}>
                    <button type="button" className="journal-item" onClick={() => onOpen(item.id)}>
                      <span className="journal-title">
                        {item.title ?? (item.journal_status === 'pending' ? '정리 중인 대화' : '제목 없는 대화')}
                      </span>
                      {item.summary[0] && <span className="journal-summary">{item.summary[0]}</span>}
                      {(counts || status) && (
                        <span className="journal-meta">
                          {[counts, status].filter(Boolean).join(' · ')}
                        </span>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
    </section>
  )
}
