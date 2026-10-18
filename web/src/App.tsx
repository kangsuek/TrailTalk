import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { fetchHealth } from './api/health'
import { fetchUsage } from './api/usage'
import type { UsageLimits } from './core/usage'
import { ConversationScreen, type ConversationHandle, type ContinueResult } from './screens/ConversationScreen'
import { JournalDetailScreen } from './screens/JournalDetailScreen'
import { JournalListScreen } from './screens/JournalListScreen'
import { SettingsScreen } from './screens/SettingsScreen'
import { UpdateBanner } from './screens/UpdateBanner'
import { UsageMeter } from './screens/UsageMeter'

// 하단 탭(S3-32 디자인 시안). 일지 상세는 탭이 아니라 일지 탭 안의 화면이다
const TABS = [
  { id: 'conversation', label: '대화', icon: <ChatIcon /> },
  { id: 'journal', label: '일지', icon: <BookIcon /> },
  { id: 'settings', label: '설정', icon: <GearIcon /> },
] as const

type TabId = (typeof TABS)[number]['id']

function ChatIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
    </svg>
  )
}

function BookIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z" />
      <path d="M5 17a3 3 0 0 1 3-3h11" />
    </svg>
  )
}

function GearIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" />
    </svg>
  )
}

const HEALTH_INTERVAL_MS = 30_000
type ServerState = 'checking' | 'ok' | 'error'

const SERVER_LABELS: Record<ServerState, string> = {
  checking: '서버 확인 중',
  ok: '서버 연결됨',
  error: '서버 연결 안 됨',
}

function App() {
  const [tab, setTab] = useState<TabId>('conversation')
  // 일지 탭 안에서 목록과 상세 중 무엇을 보일지
  const [journalView, setJournalView] = useState<'list' | 'detail'>('list')
  const [server, setServer] = useState<ServerState>('checking')
  // Claude 남은 토큰(S3-36). 서버는 답변이 올 때마다 값을 새로 받는다. 못 불러오면 앞의 값을 둔다
  const [usage, setUsage] = useState<UsageLimits | null>(null)
  const [now, setNow] = useState(() => new Date())

  // 서버 상태와 남은 토큰은 앱을 열 때와 30초마다, 탭이 다시 보일 때 확인한다(서버가 꺼졌다 켜져도 반영)
  useEffect(() => {
    const controller = new AbortController()
    const check = () => {
      setNow(new Date())
      fetchUsage(controller.signal).then(setUsage, () => {})
      return fetchHealth(controller.signal)
        .then((ok) => setServer(ok ? 'ok' : 'error'))
        .catch(() => {
          if (!controller.signal.aborted) setServer('error')
        })
    }
    void check()
    const timer = setInterval(check, HEALTH_INTERVAL_MS)
    const onVisible = () => document.visibilityState === 'visible' && void check()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      controller.abort()
    }
  }, [])

  const [journalId, setJournalId] = useState<string | null>(null)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])

  // 탭 고르기. 일지 탭에 있을 때 일지 탭을 다시 누르면 목록으로 돌아간다(다른 탭에서 오면 보던 화면 그대로)
  const selectTab = (id: TabId) => {
    if (id === 'journal' && tab === 'journal') setJournalView('list')
    setTab(id)
  }

  // 탭 목록 키보드 이동(WAI-ARIA 탭 패턴): 화살표로 옆 탭, Home·End로 처음·끝 탭을 고르고 포커스한다
  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = TABS.length - 1
    const next =
      event.key === 'ArrowRight'
        ? (index + 1) % TABS.length
        : event.key === 'ArrowLeft'
          ? (index - 1 + TABS.length) % TABS.length
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? last
              : null
    if (next === null) return
    event.preventDefault()
    selectTab(TABS[next].id)
    tabs.current[next]?.focus()
  }

  const openJournal = (sessionId: string) => {
    setJournalId(sessionId)
    setJournalView('detail')
    setTab('journal')
  }

  // 일지 상세의 "이어서" 버튼(S3-26). 버튼을 누른 동작 안에서 바로 대화 화면을 불러 음성이 소리 나게 한다
  const conversation = useRef<ConversationHandle>(null)
  const continueSession = (sessionId: string, mode: 'text' | 'voice'): ContinueResult => {
    const result = conversation.current?.continueWith(sessionId, mode) ?? 'busy'
    if (result === 'ok') setTab('conversation')
    return result
  }

  const panel = (id: TabId) => {
    switch (id) {
      case 'journal':
        return journalView === 'list' ? (
          <JournalListScreen onOpen={openJournal} />
        ) : (
          <JournalDetailScreen
            key={journalId ?? ''}
            sessionId={journalId}
            onBack={() => setJournalView('list')}
            onContinue={continueSession}
            liveSessionId={() => conversation.current?.liveSession() ?? null}
            onDeleted={() => {
              setJournalId(null)
              setJournalView('list')
            }}
          />
        )
      case 'settings':
        return <SettingsScreen />
      default:
        return null
    }
  }

  return (
    <div className="app">
      {/* 헤더와 남은 토큰 막대는 화면 위에 고정한다(스크롤해도 보이게) */}
      <div className="app-top">
        <header>
          <h1>TrailTalk</h1>
          <span className="server-status" data-state={server} role="status">
            {SERVER_LABELS[server]}
          </span>
        </header>
        <UsageMeter limits={usage} now={now} />
      </div>
      <UpdateBanner />
      <main>
        {TABS.map((t) => (
          <div
            key={t.id}
            id={`panel-${t.id}`}
            role="tabpanel"
            aria-labelledby={`tab-${t.id}`}
            hidden={tab !== t.id}
          >
            {/* 대화 화면은 탭을 옮겨도 언마운트하지 않는다(진행 중인 대화와 답변을 유지).
                나머지는 열 때마다 새로 그려 최신 내용을 불러온다 */}
            {t.id === 'conversation' ? (
              <ConversationScreen
                ref={conversation}
                visible={tab === 'conversation'}
                onOpenJournal={openJournal}
              />
            ) : (
              tab === t.id && panel(t.id)
            )}
          </div>
        ))}
      </main>
      <nav className="tabs" role="tablist" aria-label="화면">
        {TABS.map((t, index) => (
          <button
            key={t.id}
            ref={(el) => {
              tabs.current[index] = el
            }}
            id={`tab-${t.id}`}
            role="tab"
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => selectTab(t.id)}
            onKeyDown={(event) => onTabKey(event, index)}
          >
            <span className="tab-icon">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </nav>
    </div>
  )
}

export default App
