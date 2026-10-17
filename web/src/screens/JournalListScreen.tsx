import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/http'
import { deleteJournal, listJournal, renameJournal, type JournalItem } from '../api/journal'
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

function errorMessage(error: unknown, fallback = '일지를 불러오지 못했어요.'): string {
  return error instanceof ApiError ? error.message : fallback
}

function titleOf(item: JournalItem): string {
  return item.title ?? (item.journal_status === 'pending' ? '정리 중인 대화' : '제목 없는 대화')
}

const DELETE_CONFIRM = '이 대화와 노트·전문을 모두 지울까요?'
const ACTIVE_DELETE = '진행 중인 대화는 끝낸 뒤 지울 수 있어요.'
const bulkConfirm = (n: number) => `선택한 ${n}개 대화와 노트·전문을 모두 지울까요?`

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6" />
    </svg>
  )
}

// 터치 화면에는 호버가 없으므로 제목을 고칠 수 있다는 표시를 늘 둔다
function PencilIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="journal-pencil">
      <path d="M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4" />
    </svg>
  )
}

/**
 * 날짜별 일지 목록(최근 30일). 항목을 누르면 onOpen으로 상세 화면을 연다.
 * 제목을 누르면 그 자리에서 고치고 포커스가 떠나면 저장한다. 쓰레기통은 확인 뒤 지운다.
 * "선택"을 누르면 여러 개를 골라 한 번에 지운다(항목별 DELETE를 차례로 부른다).
 */
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
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  // 처리 중인 항목. 확인은 ref로 한다(blur 저장 직후의 쓰레기통 클릭처럼 다시 그리기 전에 겹쳐 와도 막게)
  const busy = useRef(new Set<string>())
  const [busyIds, setBusyIds] = useState<ReadonlySet<string>>(new Set())
  const setBusy = (id: string, on: boolean) => {
    if (on) busy.current.add(id)
    else busy.current.delete(id)
    setBusyIds(new Set(busy.current))
  }
  const [errorFor, setErrorFor] = useState<{ id: string; message: string } | null>(null)
  // 선택 모드. selected에는 사라진 항목이 남을 수 있으므로 쓸 때 지금 목록과 맞춰 본다
  const [selecting, setSelecting] = useState(false)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [bulk, setBulk] = useState<{ done: number; total: number } | null>(null)
  const [bulkError, setBulkError] = useState<string | null>(null)
  const bulkRunning = useRef(false) // 다시 그리기 전에 삭제 버튼이 두 번 눌려도 한 번만 돈다
  const cancelEdit = useRef(false) // Esc로 닫을 때 blur 저장을 건너뛴다
  const editing = useRef<string | null>(null) // blur가 겹쳐 와도 한 번만 저장한다
  // 제목 수정·삭제 전에 떠난 불러오기 응답은 버린다(옛 제목이나 지운 항목을 되살리지 않게).
  // 다시 불러오기는 상태가 바뀌면 대개 취소되지만, 처음 불러오기는 그렇지 않다
  const edits = useRef(0)
  const loadItems = (signal: AbortSignal) => {
    const seen = edits.current
    return listJournal(signal).then((items) => {
      if (edits.current === seen) setState({ kind: 'ready', items })
    })
  }

  useEffect(() => {
    const controller = new AbortController()
    loadItems(controller.signal).catch((error) => {
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
      loadItems(controller.signal).catch(() => {
        if (!controller.signal.aborted) setFailures((n) => n + 1)
      })
    }, pollMs)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [state, pollMs, failures])

  const replaceItem = (id: string, update: (item: JournalItem) => JournalItem) =>
    setState((prev) =>
      prev.kind === 'ready' ? { kind: 'ready', items: prev.items.map((i) => (i.id === id ? update(i) : i)) } : prev,
    )

  const startEdit = (item: JournalItem) => {
    cancelEdit.current = false
    setErrorFor(null)
    setDraft(item.title ?? '')
    editing.current = item.id
    setEditingId(item.id)
  }

  // 바뀐 제목만 보낸다. 화면에는 바로 반영하고 실패하면 되돌린다
  const commitEdit = async (item: JournalItem) => {
    if (editing.current !== item.id) return
    editing.current = null
    setEditingId(null)
    const title = draft.trim()
    if (cancelEdit.current || !title || title === item.title) return
    setBusy(item.id, true)
    edits.current += 1
    replaceItem(item.id, (i) => ({ ...i, title }))
    try {
      const updated = await renameJournal(item.id, title)
      replaceItem(item.id, () => updated)
    } catch (error) {
      replaceItem(item.id, (i) => ({ ...i, title: item.title }))
      setErrorFor({ id: item.id, message: errorMessage(error, '제목을 바꾸지 못했어요.') })
    } finally {
      setBusy(item.id, false)
    }
  }

  const remove = async (item: JournalItem) => {
    if (busy.current.has(item.id)) return
    // 터치 화면에는 툴팁이 없으므로 지울 수 없는 이유를 글로 보인다
    if (item.status === 'active') return setErrorFor({ id: item.id, message: ACTIVE_DELETE })
    if (!window.confirm(DELETE_CONFIRM)) return
    setBusy(item.id, true)
    setErrorFor(null)
    try {
      await deleteJournal(item.id)
      edits.current += 1
      setState((prev) =>
        prev.kind === 'ready' ? { kind: 'ready', items: prev.items.filter((i) => i.id !== item.id) } : prev,
      )
    } catch (error) {
      setErrorFor({ id: item.id, message: errorMessage(error, '대화를 지우지 못했어요.') })
    } finally {
      setBusy(item.id, false)
    }
  }

  const items = state.kind === 'ready' ? state.items : []
  const selectableIds = items.filter((i) => i.status !== 'active').map((i) => i.id)
  const chosen = selectableIds.filter((id) => selected.has(id))
  const allChosen = selectableIds.length > 0 && chosen.length === selectableIds.length

  const startSelecting = () => {
    setErrorFor(null)
    setBulkError(null)
    setSelected(new Set())
    setSelecting(true)
  }

  const stopSelecting = () => {
    setSelecting(false)
    setSelected(new Set())
    setBulkError(null)
    setErrorFor(null)
  }

  const toggle = (item: JournalItem) => {
    if (bulk) return
    // 터치 화면에는 툴팁이 없으므로 고를 수 없는 이유를 글로 보인다
    if (item.status === 'active') return setErrorFor({ id: item.id, message: ACTIVE_DELETE })
    setErrorFor(null)
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(item.id)) next.delete(item.id)
      else next.add(item.id)
      return next
    })
  }

  // 차례로 지우고(동시에 보내지 않는다) 지운 항목은 바로 뺀다. 실패한 항목은 선택된 채 남긴다.
  // 화면을 떠나도 사용자가 확인한 삭제는 끝까지 보낸다
  const removeSelected = async () => {
    const ids = chosen
    if (bulkRunning.current || ids.length === 0 || !window.confirm(bulkConfirm(ids.length))) return
    bulkRunning.current = true
    setErrorFor(null)
    setBulkError(null)
    const failed: string[] = []
    let reason = ''
    for (const [index, id] of ids.entries()) {
      setBulk({ done: index + 1, total: ids.length })
      // 제목 저장처럼 처리 중인 항목은 건너뛰고 실패로 남긴다(말없이 빠지지 않게)
      if (busy.current.has(id)) {
        failed.push(id)
        reason ||= '처리 중인 대화가 있어요. 잠시 뒤 다시 지워 주세요.'
        continue
      }
      setBusy(id, true)
      try {
        await deleteJournal(id)
      } catch (error) {
        // 404는 이미 지워진 것이다(다른 기기에서 지웠거나 같은 요청이 겹침)
        if (!(error instanceof ApiError && error.status === 404)) {
          failed.push(id)
          reason ||= errorMessage(error, '대화를 지우지 못했어요.')
          continue
        }
      } finally {
        setBusy(id, false)
      }
      edits.current += 1
      setState((prev) =>
        prev.kind === 'ready' ? { kind: 'ready', items: prev.items.filter((i) => i.id !== id) } : prev,
      )
    }
    bulkRunning.current = false
    setBulk(null)
    setSelected(new Set(failed))
    if (failed.length > 0) setBulkError(`${failed.length}개는 지우지 못했어요. ${reason}`)
    else setSelecting(false)
  }

  const retry = () => {
    polls.current = 0
    setState({ kind: 'loading' })
    setAttempt((n) => n + 1)
  }

  return (
    <section className="journal">
      <div className="journal-head">
        <h2>일지 목록</h2>
        {items.length > 0 && !selecting && (
          <button type="button" className="secondary" onClick={startSelecting}>
            선택
          </button>
        )}
      </div>
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
                const title = titleOf(item)
                const meta = [counts, status].filter(Boolean).join(' · ')
                const error = errorFor?.id === item.id && (
                  <p className="journal-error" role="alert">
                    {errorFor.message}
                  </p>
                )
                if (selecting) {
                  const active = item.status === 'active'
                  return (
                    <li key={item.id} className="journal-entry selecting">
                      {/* 카드 전체가 체크박스의 label이라 어디를 눌러도 고른다 */}
                      <label
                        className="journal-card journal-select"
                        data-disabled={active || undefined}
                        onClick={active ? () => toggle(item) : undefined}
                      >
                        <input
                          type="checkbox"
                          aria-label={`선택: ${title}`}
                          aria-describedby={meta ? `journal-meta-${item.id}` : undefined}
                          checked={!active && selected.has(item.id)}
                          disabled={active || bulk !== null}
                          onChange={() => toggle(item)}
                        />
                        <span className="journal-select-body">
                          <span className="journal-select-title">{title}</span>
                          {item.summary[0] && <span className="journal-summary">{item.summary[0]}</span>}
                          {meta && (
                            <span className="journal-meta" id={`journal-meta-${item.id}`}>
                              {meta}
                            </span>
                          )}
                        </span>
                      </label>
                      {error}
                    </li>
                  )
                }
                return (
                  <li key={item.id} className="journal-entry">
                    <div className="journal-card">
                      {editingId === item.id ? (
                        <input
                          className="journal-title-input"
                          aria-label="대화 제목"
                          value={draft}
                          maxLength={200}
                          autoFocus
                          onChange={(event) => setDraft(event.target.value)}
                          onBlur={() => void commitEdit(item)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') event.currentTarget.blur()
                            if (event.key === 'Escape') {
                              cancelEdit.current = true
                              event.currentTarget.blur()
                            }
                          }}
                        />
                      ) : (
                        <button
                          type="button"
                          className="journal-title"
                          aria-label={`제목 수정: ${title}`}
                          disabled={busyIds.has(item.id)}
                          onClick={() => startEdit(item)}
                        >
                          <span>{title}</span>
                          <PencilIcon />
                        </button>
                      )}
                      <button
                        type="button"
                        className="journal-item"
                        aria-label={[title, item.summary[0], meta].filter(Boolean).join(' ')}
                        disabled={busyIds.has(item.id)}
                        onClick={() => onOpen(item.id)}
                      >
                        {item.summary[0] && <span className="journal-summary">{item.summary[0]}</span>}
                        {meta && <span className="journal-meta">{meta}</span>}
                      </button>
                    </div>
                    <button
                      type="button"
                      className="journal-trash"
                      aria-label={`삭제: ${title}`}
                      aria-disabled={item.status === 'active'}
                      disabled={busyIds.has(item.id)}
                      onClick={() => void remove(item)}
                    >
                      <TrashIcon />
                    </button>
                    {error}
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      {selecting && state.kind === 'ready' && (
        <div className="journal-bulk" role="group" aria-label="선택한 일지">
          {bulkError && (
            <p className="journal-error" role="alert">
              {bulkError}
            </p>
          )}
          <div className="journal-bulk-row">
            <span className="journal-bulk-count" aria-live="polite">
              {bulk ? `지우는 중… ${bulk.done}/${bulk.total}` : `${chosen.length}개 선택`}
            </span>
            <button
              type="button"
              className="secondary"
              disabled={bulk !== null || selectableIds.length === 0}
              onClick={() => setSelected(allChosen ? new Set() : new Set(selectableIds))}
            >
              {allChosen ? '전체 해제' : '전체 선택'}
            </button>
            <button
              type="button"
              className="danger"
              disabled={bulk !== null || chosen.length === 0}
              onClick={() => void removeSelected()}
            >
              삭제{chosen.length > 0 ? ` (${chosen.length})` : ''}
            </button>
            <button type="button" className="secondary" disabled={bulk !== null} onClick={stopSelecting}>
              취소
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
