import { useEffect, useRef, useState } from 'react'
import { endSession } from '../api/conversation'
import { ApiError } from '../api/http'
import {
  deleteJournal,
  getJournal,
  retryJournal,
  updateNote,
  type JournalDetail,
  type NoteOut,
  type NotePatch,
} from '../api/journal'
import { citeLabel, isWebUrl } from '../core/citations'
import { dateLabel, MAX_POLLS, POLL_MS } from '../core/journal'

type DetailState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'deleted' } // 없는 일지(지운 뒤 대화 탭의 "일지 보기"나 오래된 목록 항목으로 열었다)
  | { kind: 'ready'; detail: JournalDetail }

// 대화가 없다(지웠다). 경로 설정 오류 같은 다른 404와 구분하려고 오류 코드까지 본다
const isGone = (error: unknown) =>
  error instanceof ApiError && error.status === 404 && error.code === 'session_not_found'

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

type ContinueMode = 'text' | 'voice'
/** 이어서 하기 결과(App이 대화 화면에 맡긴다): 시작함, 다른 대화가 진행 중, 음성 기능을 못 씀 */
type ContinueResult = 'ok' | 'busy' | 'voice_loading' | 'voice_unavailable'

// 목록(JournalListScreen)의 삭제와 같은 문구
const DELETE_CONFIRM = '이 대화와 노트·전문을 모두 지울까요?'
const ACTIVE_DELETE = '진행 중인 대화는 끝낸 뒤 지울 수 있어요.'

const CONTINUE_MESSAGES: Record<Exclude<ContinueResult, 'ok'>, string> = {
  busy: '진행 중인 대화를 끝낸 뒤 이어서 할 수 있어요.',
  voice_loading: '음성 기능을 준비하는 중이에요. 잠시 뒤 다시 눌러 주세요.',
  voice_unavailable: '음성 기능을 불러오지 못했어요. 글로 이어서 하거나 새로 고침해 주세요.',
}

/** 일지 상세: 요약, 아이디어 별표, 할 일 체크, 메모, 대화 전문. 다른 세션을 열 때는 key로 새로 그린다(App).
 * onContinue: 끝난 대화를 대화 화면에서 이어서 한다(S3-26). 대화 화면에서 진행 중인 대화면 그 화면으로 옮긴다.
 * onDeleted: 대화를 지운 뒤(S3-29, App이 목록으로 옮긴다).
 * liveSessionId: 대화 화면에서 진행 중인 대화. 진행 중인데 거기 열려 있지 않은 대화(앱을 닫았거나 다른 기기)는
 * 여기서 이어서 하거나 끝낼 수 있다(끝내야 지울 수 있다). */
export function JournalDetailScreen({
  sessionId = null,
  onBack = () => {},
  onContinue,
  onDeleted = () => {},
  liveSessionId = () => null,
  pollMs = POLL_MS,
}: {
  sessionId?: string | null
  onBack?: () => void
  onContinue?: (sessionId: string, mode: ContinueMode) => ContinueResult
  onDeleted?: () => void
  liveSessionId?: () => string | null
  pollMs?: number
}) {
  const [state, setState] = useState<DetailState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [saveError, setSaveError] = useState<string | null>(null)
  // 지워진 대화로 바꾼다. 남아 있던 저장 오류는 지우고, 사라진 버튼 대신 목록 버튼으로 포커스를 옮긴다
  const goneButton = useRef<HTMLButtonElement>(null)
  const markDeleted = () => {
    setSaveError(null)
    setState({ kind: 'deleted' })
  }
  useEffect(() => {
    if (state.kind === 'deleted') goneButton.current?.focus()
  }, [state.kind])

  useEffect(() => {
    if (sessionId === null) return
    const controller = new AbortController()
    getJournal(sessionId, controller.signal)
      .then((detail) => setState({ kind: 'ready', detail }))
      .catch((error) => {
        if (controller.signal.aborted) return
        if (isGone(error)) markDeleted()
        else setState({ kind: 'error', message: errorMessage(error, '일지를 불러오지 못했어요.') })
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
        .catch((error) => {
          if (controller.signal.aborted) return
          if (isGone(error)) markDeleted() // 정리 중에 다른 곳에서 지웠다
          else setFailures((n) => n + 1)
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
      .catch((error) =>
        isGone(error) ? markDeleted() : setSaveError(errorMessage(error, '다시 정리하지 못했어요.')),
      )
  }

  const continueIn = (mode: ContinueMode) => {
    if (sessionId === null || !onContinue) return
    setSaveError(null)
    const result = onContinue(sessionId, mode)
    if (result !== 'ok') setSaveError(CONTINUE_MESSAGES[result])
  }

  // 확인 뒤 지우고 목록으로 돌아간다. 404는 이미 지워진 것이다(다른 기기에서 지웠거나 요청이 겹침)
  const [deleting, setDeleting] = useState(false)
  // 지우는 사이 사용자가 다른 화면으로 옮겼으면 응답이 와도 화면을 바꾸지 않는다
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  // 상세를 보는 사이 대화 화면의 대화가 끝났을 수 있어 누를 때 다시 본다(끝났으면 다시 열지 않고 새로 불러온다)
  const backToConversation = () => {
    if (sessionId === null) return
    if (liveSessionId() !== sessionId) return reload()
    continueIn('text')
  }

  // 대화 화면에 열려 있지 않은 진행 중 대화를 끝낸다. 서버는 일지 정리를 잠깐 기다린 뒤 답하므로
  // 대화 화면의 끝내기처럼 그동안 정리 중이라고 보인다. 끝나면 다시 불러온다(정리가 남았으면 자동 새로고침)
  const [ending, setEnding] = useState(false)
  const endHere = async () => {
    if (sessionId === null || ending || deleting) return
    setSaveError(null)
    setEnding(true)
    try {
      await endSession(sessionId)
    } catch (error) {
      if (!mounted.current) return
      setEnding(false)
      return isGone(error) ? markDeleted() : setSaveError(errorMessage(error, '대화를 끝내지 못했어요.'))
    }
    if (!mounted.current) return
    setEnding(false)
    reload()
  }

  const remove = async () => {
    if (sessionId === null || deleting || ending || state.kind !== 'ready') return
    // 터치 화면에는 툴팁이 없으므로 지울 수 없는 이유를 글로 보인다
    if (state.detail.session.status !== 'ended') return setSaveError(ACTIVE_DELETE)
    if (!window.confirm(DELETE_CONFIRM)) return
    setSaveError(null)
    setDeleting(true)
    try {
      await deleteJournal(sessionId)
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) {
        setDeleting(false)
        return setSaveError(errorMessage(error, '대화를 지우지 못했어요.'))
      }
    }
    if (mounted.current) onDeleted()
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
      <div className="journal-head journal-detail-head">
        <button type="button" className="journal-back" onClick={onBack} aria-label="목록으로">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M15 6l-6 6 6 6" />
          </svg>
          목록
        </button>
        <h2>일지 상세</h2>
      </div>
      {state.kind === 'loading' && <p className="journal-note">불러오는 중…</p>}
      {state.kind === 'error' && (
        <div className="journal-note">
          <p role="alert">{state.message}</p>
          <button type="button" onClick={reload}>
            다시 불러오기
          </button>
        </div>
      )}
      {state.kind === 'deleted' && (
        <div className="journal-note">
          <p role="status">지워진 대화예요. 일지 목록에서 다른 대화를 골라 주세요.</p>
          <button type="button" className="journal-gone" ref={goneButton} onClick={onBack}>
            일지 목록으로
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
          deleting={deleting}
          onContinue={onContinue ? continueIn : undefined}
          live={liveSessionId() === sessionId}
          onReturn={onContinue ? backToConversation : undefined}
          ending={ending}
          onEnd={() => void endHere()}
        />
      )}
      {state.kind === 'ready' && (
        <button
          type="button"
          className="journal-delete"
          aria-disabled={state.detail.session.status !== 'ended'}
          disabled={deleting || ending}
          onClick={() => void remove()}
        >
          {deleting ? '지우는 중…' : '이 대화 삭제'}
        </button>
      )}
      {saveError && (
        <p className="journal-error" role="alert">
          {saveError}
        </p>
      )}
    </section>
  )
}

/** 문장 끝 출처 번호(없으면 아무것도 그리지 않는다) */
function Cites({ cites }: { cites: readonly number[] | undefined }) {
  if (!cites || cites.length === 0) return null
  return <sup className="journal-cite">{citeLabel(cites)}</sup>
}

/** 인용: [n] 기사 제목(링크) + URL */
function Citations({ citations }: { citations: JournalDetail['citations'] }) {
  if (citations.length === 0) return null
  return (
    <section aria-label="인용" className="journal-citations">
      <h4>인용:</h4>
      <ol>
        {citations.map((c) => (
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
  )
}

function Detail({
  detail,
  onChange,
  onReload,
  onRetry,
  retrying,
  deleting,
  onContinue,
  live,
  onReturn,
  ending,
  onEnd,
}: {
  detail: JournalDetail
  onChange: (note: NoteOut, patch: NotePatch) => void
  onReload: () => void
  onRetry: () => void
  retrying: boolean
  deleting: boolean // 지우는 동안 이어서·다시 정리를 막는다(지운 대화를 다시 열거나 정리하지 않게)
  onContinue?: (mode: ContinueMode) => void
  live: boolean // 대화 화면에서 진행 중인 대화다(거기서 이어 가고 끝낸다)
  onReturn?: () => void
  ending: boolean
  onEnd: () => void
}) {
  const { session, notes, turns } = detail
  const ideas = notes.filter((n) => n.kind === 'idea')
  const todos = notes.filter((n) => n.kind === 'todo')
  const memos = notes.filter((n) => n.kind === 'memo')
  // 새 형식(S3-24): 요약 첫 줄이 결론, 나머지가 '알게 된 것'이고 확인할 것이 따로 온다.
  // checks가 null이면 예전 형식(요약 줄만)이다
  const checks = detail.checks ?? null
  const newFormat = checks !== null
  const cites = (i: number) => detail.summary_cites?.[i]
  const oldFormat =
    !newFormat && session.status === 'ended' && session.journal_status === 'done' && session.summary.length > 0
  const tags = session.tags.length > 0 && (
    <p className="journal-tags">{session.tags.map((tag) => `#${tag}`).join(' ')}</p>
  )
  return (
    <article className="journal-detail">
      <h3>{session.title ?? '제목 없는 대화'}</h3>
      <p className="journal-date">{dateLabel(session.date)}</p>
      {session.status !== 'ended' && (
        <p className="journal-note" aria-live="polite">
          {ending ? '대화를 끝내고 일지로 정리하는 중이에요…' : '아직 진행 중인 대화예요. 대화를 끝내면 일지로 정리돼요.'}
        </p>
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
            <button type="button" className="secondary" onClick={onRetry} disabled={retrying || deleting}>
              다시 정리
            </button>
          </div>
        )}
      {oldFormat && (
        <div className="journal-note">
          <p>예전 형식으로 정리된 일지예요. 결론·알게 된 것·확인할 것으로 다시 정리할 수 있어요.</p>
          <button type="button" className="secondary" onClick={onRetry} disabled={retrying || deleting}>
            다시 정리
          </button>
        </div>
      )}
      {newFormat ? (
        <>
          {session.summary.length > 0 && (
            <p className="journal-conclusion" aria-label="결론">
              <strong>{session.summary[0]}</strong>
              <Cites cites={cites(0)} />
            </p>
          )}
          {session.summary.length > 1 && (
            <section aria-label="알게 된 것">
              <h4>알게 된 것</h4>
              <ul className="journal-summary-lines">
                {session.summary.slice(1).map((line, i) => (
                  <li key={i}>
                    {line}
                    <Cites cites={cites(i + 1)} />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {checks.length > 0 && (
            <section aria-label="확인할 것">
              <h4>확인할 것</h4>
              <ul className="journal-summary-lines journal-checks">
                {checks.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      ) : (
        <>
          {session.summary.length > 0 && (
            <ul className="journal-summary-lines" aria-label="요약">
              {session.summary.map((line, i) => (
                <li key={i}>
                  {line}
                  <Cites cites={cites(i)} />
                </li>
              ))}
            </ul>
          )}
          {tags}
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
              <li key={note.id}>
                <span>
                  {note.content}
                  <Cites cites={note.cites} />
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {notes.length === 0 && session.status === 'ended' && session.journal_status !== 'pending' && (
        <p className="journal-note">저장한 아이디어·할 일·메모가 없어요.</p>
      )}

      <Citations citations={detail.citations ?? []} />
      {newFormat && tags /* 새 형식은 태그를 맨 아래에 */}
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
      {session.status !== 'ended' && live ? (
        onReturn && (
          <div className="journal-continue single">
            <button type="button" onClick={onReturn}>
              대화로 돌아가기
            </button>
          </div>
        )
      ) : (
        // 끝난 대화, 또는 대화 화면에 열려 있지 않은 진행 중 대화(앱을 닫았거나 다른 기기)는 이어서 한다.
        // 진행 중인 대화는 서버가 지금 CLI를 닫고 이어받는다(S3-37)
        onContinue && (
          <div className="journal-continue" role="group" aria-label="이어서 대화하기">
            <button type="button" className="secondary" disabled={deleting || ending} onClick={() => onContinue('text')}>
              글로 이어서
            </button>
            <button type="button" disabled={deleting || ending} onClick={() => onContinue('voice')}>
              음성으로 이어서
            </button>
          </div>
        )
      )}
      {session.status !== 'ended' && !live && (
        <button type="button" className="secondary journal-end" disabled={ending || deleting} onClick={onEnd}>
          {ending ? '끝내는 중…' : '대화 끝내기'}
        </button>
      )}
    </article>
  )
}
