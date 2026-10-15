import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { fetchHealth } from './api/health'
import { ConversationScreen } from './screens/ConversationScreen'
import { JournalDetailScreen } from './screens/JournalDetailScreen'
import { JournalListScreen } from './screens/JournalListScreen'
import { SettingsScreen } from './screens/SettingsScreen'

const SCREENS = [
  { id: 'conversation', label: '대화' },
  { id: 'journal-list', label: '일지 목록' },
  { id: 'journal-detail', label: '일지 상세' },
  { id: 'settings', label: '설정' },
] as const

type ScreenId = (typeof SCREENS)[number]['id']

const HEALTH_INTERVAL_MS = 30_000
type ServerState = 'checking' | 'ok' | 'error'

const SERVER_LABELS: Record<ServerState, string> = {
  checking: '서버 확인 중',
  ok: '서버 연결됨',
  error: '서버 연결 안 됨',
}

function App() {
  const [screen, setScreen] = useState<ScreenId>('conversation')
  const [server, setServer] = useState<ServerState>('checking')

  // 서버 상태는 앱을 열 때와 30초마다, 탭이 다시 보일 때 확인한다(서버가 꺼졌다 켜져도 반영)
  useEffect(() => {
    const controller = new AbortController()
    const check = () =>
      fetchHealth(controller.signal)
        .then((ok) => setServer(ok ? 'ok' : 'error'))
        .catch(() => {
          if (!controller.signal.aborted) setServer('error')
        })
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

  // 탭 목록 키보드 이동(WAI-ARIA 탭 패턴): 화살표로 옆 탭, Home·End로 처음·끝 탭을 고르고 포커스한다
  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = SCREENS.length - 1
    const next =
      event.key === 'ArrowRight'
        ? (index + 1) % SCREENS.length
        : event.key === 'ArrowLeft'
          ? (index - 1 + SCREENS.length) % SCREENS.length
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? last
              : null
    if (next === null) return
    event.preventDefault()
    setScreen(SCREENS[next].id)
    tabs.current[next]?.focus()
  }

  const openJournal = (sessionId: string) => {
    setJournalId(sessionId)
    setScreen('journal-detail')
  }

  const panel = (id: ScreenId) => {
    switch (id) {
      case 'journal-list':
        return <JournalListScreen onOpen={openJournal} />
      case 'journal-detail':
        return (
          <JournalDetailScreen
            key={journalId ?? ''}
            sessionId={journalId}
            onBack={() => setScreen('journal-list')}
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
      <header>
        <h1>TrailTalk</h1>
        <span className="server-status" data-state={server} role="status">
          {SERVER_LABELS[server]}
        </span>
      </header>
      <nav className="tabs" role="tablist" aria-label="화면">
        {SCREENS.map((s, index) => (
          <button
            key={s.id}
            ref={(el) => {
              tabs.current[index] = el
            }}
            id={`tab-${s.id}`}
            role="tab"
            aria-selected={screen === s.id}
            aria-controls={`panel-${s.id}`}
            tabIndex={screen === s.id ? 0 : -1}
            onClick={() => setScreen(s.id)}
            onKeyDown={(event) => onTabKey(event, index)}
          >
            {s.label}
          </button>
        ))}
      </nav>
      <main>
        {SCREENS.map((s) => (
          <div
            key={s.id}
            id={`panel-${s.id}`}
            role="tabpanel"
            aria-labelledby={`tab-${s.id}`}
            hidden={screen !== s.id}
          >
            {/* 대화 화면은 탭을 옮겨도 언마운트하지 않는다(진행 중인 대화와 답변을 유지).
                나머지는 열 때마다 새로 그려 최신 내용을 불러온다 */}
            {s.id === 'conversation' ? (
              <ConversationScreen visible={screen === 'conversation'} />
            ) : (
              screen === s.id && panel(s.id)
            )}
          </div>
        ))}
      </main>
    </div>
  )
}

export default App
