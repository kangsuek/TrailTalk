import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function stubFetch(response: () => Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(response))
}

function stubHealth(ok: boolean) {
  stubFetch(async () => new Response(JSON.stringify({ status: ok ? 'ok' : 'down' })))
}

describe('App', () => {
  it('탭을 눌러 4개 화면을 전환한다', async () => {
    stubHealth(true)
    render(<App />)
    for (const name of ['대화', '일지 목록', '일지 상세', '설정']) {
      fireEvent.click(screen.getByRole('tab', { name }))
      expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument()
    }
    expect(await screen.findByText('서버 연결됨')).toBeInTheDocument()
  })

  it('서버 헬스체크 결과를 표시한다', async () => {
    stubHealth(true)
    render(<App />)
    expect(await screen.findByText('서버 연결됨')).toBeInTheDocument()
  })

  it.each([
    ['네트워크 오류', () => Promise.reject(new TypeError('network'))],
    ['HTTP 500', async () => new Response('', { status: 500 })],
    ['status가 ok가 아님', async () => new Response(JSON.stringify({ status: 'down' }))],
  ])('서버 상태가 비정상이면 오류를 표시한다: %s', async (_case, response) => {
    stubFetch(response)
    render(<App />)
    expect(await screen.findByText('서버 연결 안 됨')).toBeInTheDocument()
  })
})
