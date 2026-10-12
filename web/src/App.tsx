import { useEffect, useState } from 'react'
import { fetchHealth } from './api/health'
import { ConversationScreen } from './screens/ConversationScreen'
import { JournalDetailScreen } from './screens/JournalDetailScreen'
import { JournalListScreen } from './screens/JournalListScreen'
import { SettingsScreen } from './screens/SettingsScreen'

const SCREENS = [
  { id: 'conversation', label: '대화', Component: ConversationScreen },
  { id: 'journal-list', label: '일지 목록', Component: JournalListScreen },
  { id: 'journal-detail', label: '일지 상세', Component: JournalDetailScreen },
  { id: 'settings', label: '설정', Component: SettingsScreen },
] as const

type ScreenId = (typeof SCREENS)[number]['id']
type ServerState = 'checking' | 'ok' | 'error'

const SERVER_LABELS: Record<ServerState, string> = {
  checking: '서버 확인 중',
  ok: '서버 연결됨',
  error: '서버 연결 안 됨',
}

function App() {
  const [screen, setScreen] = useState<ScreenId>('conversation')
  const [server, setServer] = useState<ServerState>('checking')

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then((ok) => setServer(ok ? 'ok' : 'error'))
      .catch(() => {
        if (!controller.signal.aborted) setServer('error')
      })
    return () => controller.abort()
  }, [])

  const Current = SCREENS.find((s) => s.id === screen)!.Component

  return (
    <div className="app">
      <header>
        <h1>TrailTalk</h1>
        <span className="server-status" data-state={server} role="status">
          {SERVER_LABELS[server]}
        </span>
      </header>
      <nav className="tabs" role="tablist">
        {SCREENS.map((s) => (
          <button
            key={s.id}
            role="tab"
            aria-selected={screen === s.id}
            onClick={() => setScreen(s.id)}
          >
            {s.label}
          </button>
        ))}
      </nav>
      <main>
        <Current />
      </main>
    </div>
  )
}

export default App
