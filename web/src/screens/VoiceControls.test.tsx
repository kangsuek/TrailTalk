import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { SessionStateName } from '../core'
import { VoiceControls } from './VoiceControls'

afterEach(cleanup)

function renderControls(state: SessionStateName, onPause = vi.fn()) {
  render(
    <VoiceControls state={state} connecting={false} onTap={vi.fn()} onLongPress={vi.fn()} onPause={onPause} />,
  )
  return onPause
}

describe('VoiceControls 일시 중단 버튼', () => {
  it('듣는 중에 누르면 일시 중단을 알린다', () => {
    const onPause = renderControls('listening')
    fireEvent.click(screen.getByRole('button', { name: '일시 중단' }))
    expect(onPause).toHaveBeenCalledTimes(1)
  })

  it.each<SessionStateName>(['idle', 'processing', 'speaking', 'paused', 'offline', 'closing'])(
    '%s 상태에서는 보이지 않는다',
    (state) => {
      renderControls(state)
      expect(screen.queryByRole('button', { name: '일시 중단' })).toBeNull()
    },
  )
})
