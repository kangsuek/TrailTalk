import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/http'
import {
  getJournal,
  retryJournal,
  updateNote,
  type JournalDetail,
  type NoteOut,
  type NotePatch,
} from '../api/journal'
import { dateLabel, MAX_POLLS, POLL_MS } from '../core/journal'
import { boldSegments, citeLabel, isWebUrl, searchUrl } from '../core/report'

type DetailState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; detail: JournalDetail }

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

/** 일지 상세: 요약, 아이디어 별표, 할 일 체크, 메모, 대화 전문. 다른 세션을 열 때는 key로 새로 그린다(App). */
export function JournalDetailScreen({
  sessionId = null,
  onBack = () => {},
  pollMs = POLL_MS,
}: {
  sessionId?: string | null
  onBack?: () => void
  pollMs?: number
}) {
  const [state, setState] = useState<DetailState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (sessionId === null) return
    const controller = new AbortController()
    getJournal(sessionId, controller.signal)
      .then((detail) => setState({ kind: 'ready', detail }))
      .catch((error) => {
        if (!controller.signal.aborted) {
          setState({ kind: 'error', message: errorMessage(error, '일지를 불러오지 못했어요.') })
        }
      })
    return () => controller.abort()
  }, [sessionId, attempt])

  // 정리 중이면 끝날 때까지 다시 불러온다(목록과 같은 간격·한도)
  const polls = useRef(0)
  const [failures, setFailures] = useState(0) // 실패해도 다음 차례에 다시 보도록 이펙트를 다시 돌린다
  useEffect(() => {
    if (state.kind !== 'ready' || state.detail.session.journal_status !== 'pending') return
    if (sessionId === null || polls.current >= MAX_POLLS) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      polls.current += 1
      getJournal(sessionId, controller.signal)
        .then((detail) => setState({ kind: 'ready', detail }))
        .catch(() => {
          if (!controller.signal.aborted) setFailures((n) => n + 1)
        })
    }, pollMs)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [state, sessionId, pollMs, failures])

  const reload = () => {
    polls.current = 0
    setState({ kind: 'loading' })
    setSaveError(null)
    setAttempt((n) => n + 1)
  }

  const replaceNote = (note: NoteOut) =>
    setState((current) =>
      current.kind === 'ready'
        ? {
            kind: 'ready',
            detail: {
              ...current.detail,
              notes: current.detail.notes.map((n) => (n.id === note.id ? note : n)),
            },
          }
        : current,
    )

  // 노트별 마지막 요청 번호. 빠르게 여러 번 바꿀 때 옛 요청의 응답·되돌림이 최신 화면을 덮지 않게 한다
  const latest = useRef(new Map<string, number>())

  /** 화면을 먼저 바꾸고 저장한다. 실패하면 되돌리고 알린다. */
  const change = (note: NoteOut, patch: NotePatch) => {
    const seq = (latest.current.get(note.id) ?? 0) + 1
    latest.current.set(note.id, seq)
    const isLatest = () => latest.current.get(note.id) === seq
    setSaveError(null)
    replaceNote({ ...note, ...patch } as NoteOut)
    updateNote(note.id, patch)
      .then((saved) => {
        if (isLatest()) replaceNote(saved)
      })
      .catch((error) => {
        if (!isLatest()) return
        replaceNote(note)
        setSaveError(errorMessage(error, '저장하지 못했어요. 다시 해 주세요.'))
      })
  }

  /** 정리 실패한 일지를 다시 정리한다. 정리 중으로 바뀌면 자동 새로고침이 끝을 본다. */
  const [retrying, setRetrying] = useState(false)
  const retry = () => {
    if (sessionId === null || retrying) return
    setSaveError(null)
    setRetrying(true)
    retryJournal(sessionId)
      .finally(() => setRetrying(false))
      .then((session) => {
        polls.current = 0
        setState((current) =>
          current.kind === 'ready' ? { kind: 'ready', detail: { ...current.detail, session } } : current,
        )
      })
      .catch((error) => setSaveError(errorMessage(error, '다시 정리하지 못했어요.')))
  }

  if (sessionId === null) {
    return (
      <section className="journal">
        <h2>일지 상세</h2>
        <p className="journal-note">일지 목록에서 볼 대화를 골라 주세요.</p>
        <button type="button" onClick={onBack}>
          일지 목록으로
        </button>
      </section>
    )
  }

  return (
    <section className="journal">
      <h2>일지 상세</h2>
      <button type="button" className="secondary" onClick={onBack} aria-label="목록으로">
        <span aria-hidden="true">←</span> 목록
      </button>
      {state.kind === 'loading' && <p className="journal-note">불러오는 중…</p>}
      {state.kind === 'error' && (
        <div className="journal-note">
          <p role="alert">{state.message}</p>
          <button type="button" onClick={reload}>
            다시 불러오기
          </button>
        </div>
      )}
      {state.kind === 'ready' && (
        <Detail
          detail={state.detail}
          onChange={change}
          onReload={reload}
          onRetry={retry}
          retrying={retrying}
        />
      )}
      {saveError && (
        <p className="journal-error" role="alert">
          {saveError}
        </p>
      )}
    </section>
  )
}

type Report = NonNullable<JournalDetail['report']>
type ReportLine = Report['key_points'][number]

/** 핵심 수치·명칭은 굵게, 문장 끝에 출처 번호 */
function Sentence({ text, cites }: { text: string; cites: number[] }) {
  return (
    <>
      {boldSegments(text).map((part, i) => (part.bold ? <strong key={i}>{part.text}</strong> : part.text))}
      {cites.length > 0 && <sup className="journal-cite">{citeLabel(cites)}</sup>}
    </>
  )
}

function ReportLines({ title, lines }: { title: string; lines: ReportLine[] }) {
  if (lines.length === 0) return null
  return (
    <section aria-label={title}>
      <h4>{title}</h4>
      <ul className="journal-report-lines">
        {lines.map((line, i) => (
          <li key={i}>
            <Sentence text={line.text} cites={line.cites} />
          </li>
        ))}
      </ul>
    </section>
  )
}

/** 일지 보고서(S3-22): 결론 → 핵심 내용 → 세부 내용 → 인용 → 검색어 */
function ReportView({ report, tags }: { report: Report; tags: string[] }) {
  return (
    <div className="journal-report">
      <p className="journal-conclusion">
        <Sentence text={report.conclusion} cites={report.conclusion_cites} />
      </p>
      <ReportLines title="핵심 내용" lines={report.key_points} />
      <ReportLines title="세부 내용" lines={report.details} />
      {report.citations.length > 0 && (
        <section aria-label="인용" className="journal-citations">
          <p className="journal-citations-label">인용:</p>
          <ol>
            {report.citations.map((c) => (
              <li key={c.n}>
                [{c.n}]{' '}
                {isWebUrl(c.url) ? (
                  <a href={c.url} target="_blank" rel="noopener noreferrer">
                    {c.title}
                  </a>
                ) : (
                  c.title
                )}{' '}
                <span className="journal-url">{c.url}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
      <SearchTerms tags={tags} />
    </div>
  )
}

/** 검색어: 누르면 새 탭에서 웹 검색 */
function SearchTerms({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null
  return (
    <p className="journal-tags" aria-label="검색어">
      {tags.map((tag, i) => (
        <span key={tag}>
          {i > 0 && ', '}
          <a href={searchUrl(tag)} target="_blank" rel="noopener noreferrer">
            #{tag}
          </a>
        </span>
      ))}
    </p>
  )
}

function Detail({
  detail,
  onChange,
  onReload,
  onRetry,
  retrying,
}: {
  detail: JournalDetail
  onChange: (note: NoteOut, patch: NotePatch) => void
  onReload: () => void
  onRetry: () => void
  retrying: boolean
}) {
  const { session, notes, turns } = detail
  const report = detail.report ?? null // 예전 서버 응답에는 없다
  // 예전 형식(요약 줄만)으로 정리된 일지는 새 형식으로 다시 정리할 수 있다
  const oldFormat = session.status === 'ended' && session.journal_status === 'done' && report === null && session.summary.length > 0
  const ideas = notes.filter((n) => n.kind === 'idea')
  const todos = notes.filter((n) => n.kind === 'todo')
  const memos = notes.filter((n) => n.kind === 'memo')
  return (
    <article className="journal-detail">
      <h3>{session.title ?? '제목 없는 대화'}</h3>
      <p className="journal-date">{dateLabel(session.date)}</p>
      {session.status !== 'ended' && (
        <p className="journal-note">아직 진행 중인 대화예요. 대화를 끝내면 일지로 정리돼요.</p>
      )}
      {session.journal_status === 'pending' && (
        <div className="journal-note" aria-live="polite">
          <p>일지를 정리하는 중이에요. 끝나면 자동으로 보여 드려요.</p>
          <button type="button" className="secondary" onClick={onReload}>
            다시 불러오기
          </button>
        </div>
      )}
      {session.status === 'ended' &&
        (session.journal_status === 'failed' || session.journal_status === null) && (
          <div className="journal-note">
            <p>
              {session.journal_status === 'failed'
                ? '일지 정리에 실패했어요. 대화 전문은 아래에서 볼 수 있어요.'
                : '아직 정리하지 않은 대화예요.'}
            </p>
            <button type="button" className="secondary" onClick={onRetry} disabled={retrying}>
              다시 정리
            </button>
          </div>
        )}
      {oldFormat && (
        <div className="journal-note">
          <p>예전 형식으로 정리된 일지예요. 결론·핵심 내용·출처 형식으로 다시 정리할 수 있어요.</p>
          <button type="button" className="secondary" onClick={onRetry} disabled={retrying}>
            다시 정리
          </button>
        </div>
      )}
      {report !== null ? (
        <ReportView report={report} tags={session.tags} />
      ) : (
        <>
          {session.summary.length > 0 && (
            <ul className="journal-summary-lines" aria-label="요약">
              {session.summary.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          )}
          <SearchTerms tags={session.tags} />
        </>
      )}

      {ideas.length > 0 && (
        <section aria-label="아이디어">
          <h4>아이디어</h4>
          <ul className="journal-notes">
            {ideas.map((note) => (
              <li key={note.id} data-done={note.done}>
                <button
                  type="button"
                  className="star"
                  aria-pressed={note.starred}
                  aria-label={`별표: ${note.content}`}
                  onClick={() => onChange(note, { starred: !note.starred })}
                >
                  {note.starred ? '★' : '☆'}
                </button>
                <span>{note.content}</span>
                {/* 다 했거나 접은 아이디어는 닫는다(다음 대화의 기억에서 빠진다) */}
                <button
                  type="button"
                  className="secondary idea-done"
                  aria-pressed={note.done}
                  aria-label={`완료: ${note.content}`}
                  onClick={() => onChange(note, { done: !note.done })}
                >
                  {note.done ? '완료됨' : '완료'}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {todos.length > 0 && (
        <section aria-label="할 일">
          <h4>할 일</h4>
          <ul className="journal-notes">
            {todos.map((note) => (
              <li key={note.id} data-done={note.done}>
                <label>
                  <input
                    type="checkbox"
                    checked={note.done}
                    onChange={() => onChange(note, { done: !note.done })}
                  />
                  <span>{note.content}</span>
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}
      {memos.length > 0 && (
        <section aria-label="메모">
          <h4>메모</h4>
          <ul className="journal-notes">
            {memos.map((note) => (
              <li key={note.id}>{note.content}</li>
            ))}
          </ul>
        </section>
      )}
      {notes.length === 0 && session.status === 'ended' && session.journal_status !== 'pending' && (
        <p className="journal-note">저장한 아이디어·할 일·메모가 없어요.</p>
      )}

      <details className="journal-transcript">
        <summary>대화 전문 보기 ({turns.length})</summary>
        <ol>
          {turns.map((turn) => (
            <li key={turn.id} className={turn.role}>
              <span className="speaker">{turn.role === 'user' ? '나' : detail.persona_name}</span>
              <p>
                {turn.text}
                {turn.interrupted && <span className="journal-cut"> (말이 끊김)</span>}
              </p>
            </li>
          ))}
        </ol>
      </details>
    </article>
  )
}
