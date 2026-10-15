import { useEffect, useState } from 'react'
import { ApiError } from '../api/http'
import { listJournal, type JournalItem } from '../api/journal'
import { countsLabel, dateLabel, groupByDate, journalStatusLabel } from '../core/journal'

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; items: JournalItem[] }

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '일지를 불러오지 못했어요.'
}

/** 날짜별 일지 목록(최근 30일). 항목을 누르면 onOpen으로 상세 화면을 연다. */
export function JournalListScreen({ onOpen = () => {} }: { onOpen?: (sessionId: string) => void }) {
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

  const retry = () => {
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
