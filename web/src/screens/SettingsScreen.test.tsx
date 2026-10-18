import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SettingsScreen } from './SettingsScreen'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const PROFILE = {
  nickname: '다니엘님',
  interests: ['등산'],
  persona_id: 'jenny',
  voice: null,
  speaking_rate: null,
  keep_audio: false,
  chat_model: null,
  default_chat_model: 'sonnet',
  client: {},
}
const VOICES = { voices: ['coral', 'nova', 'sage'], default_voice: 'nova', default_rate: 1.05, min_rate: 0.75, max_rate: 1.5 }

function stubServer(put: (body: Record<string, unknown>) => Response = (body) => new Response(JSON.stringify({ ...PROFILE, ...body }))) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/profile' && init?.method === 'PUT') return put(JSON.parse(init.body as string))
    if (url === '/api/profile') return new Response(JSON.stringify(PROFILE))
    if (url === '/api/voices') return new Response(JSON.stringify(VOICES))
    throw new Error(`unexpected ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const putBodies = (fetchMock: ReturnType<typeof vi.fn>) =>
  (fetchMock.mock.calls as unknown as [string, RequestInit | undefined][])
    .filter(([, init]) => init?.method === 'PUT')
    .map(([, init]) => JSON.parse(init!.body as string))

describe('SettingsScreen', () => {
  it('불러온 값을 보이고 바뀐 필드만 저장한다', async () => {
    const fetchMock = stubServer()
    render(<SettingsScreen />)
    const nickname = await screen.findByRole('textbox', { name: '호칭' })
    expect(nickname).toHaveValue('다니엘님')
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled()

    fireEvent.change(screen.getByRole('combobox', { name: '보이스' }), { target: { value: 'coral' } })
    fireEvent.click(screen.getByRole('radio', { name: '느리게' }))
    fireEvent.click(screen.getByRole('checkbox', { name: /음성 원본 보관/ }))
    expect(screen.getByRole('radio', { name: '기본(sonnet)' })).toBeChecked() // 서버 기본 모델
    fireEvent.click(screen.getByRole('radio', { name: '똑똑함(opus)' }))
    fireEvent.click(screen.getByRole('button', { name: '저장' }))

    expect(await screen.findByRole('status')).toHaveTextContent('저장했어요')
    expect(putBodies(fetchMock)).toEqual([{ voice: 'coral', speaking_rate: 0.85, keep_audio: true, chat_model: 'opus' }])
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled() // 저장한 값이 새 기준
  })

  it('관심사를 추가·삭제하고 중복은 알린다', async () => {
    const fetchMock = stubServer()
    render(<SettingsScreen />)
    const input = await screen.findByRole('textbox', { name: '새 관심사' })
    fireEvent.change(input, { target: { value: '등산' } })
    fireEvent.click(screen.getByRole('button', { name: '추가' }))
    expect(screen.getByText('이미 있는 관심사예요.')).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '전시' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    const list = screen.getByRole('list', { name: '관심사 목록' })
    expect(within(list).getByText('전시')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '관심사 삭제: 등산' }))
    fireEvent.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() => expect(putBodies(fetchMock)).toEqual([{ interests: ['전시'] }]))
  })

  it('호칭을 비우면 기본 호칭(null)으로 저장하고, 실패하면 이유를 보인다', async () => {
    stubServer(() => new Response(JSON.stringify({ error: { code: 'validation_error', message: '요청 형식이 올바르지 않습니다.' } }), { status: 422 }))
    render(<SettingsScreen />)
    fireEvent.change(await screen.findByRole('textbox', { name: '호칭' }), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('요청 형식이 올바르지 않습니다.')
    expect(screen.getByRole('button', { name: '저장' })).toBeEnabled() // 다시 저장할 수 있다
  })

  it('들어 보기는 고른 보이스·속도의 샘플을 재생한다(기본이면 캐릭터 보이스)', async () => {
    stubServer()
    const played: string[] = []
    vi.stubGlobal(
      'Audio',
      class {
        src: string
        onerror: (() => void) | null = null
        constructor(src: string) {
          this.src = src
        }
        play() {
          played.push(this.src)
          return Promise.resolve()
        }
        pause() {}
      },
    )
    render(<SettingsScreen />)
    fireEvent.click(await screen.findByRole('button', { name: '들어 보기' }))
    fireEvent.click(screen.getByRole('radio', { name: '빠르게' }))
    fireEvent.change(screen.getByRole('combobox', { name: '보이스' }), { target: { value: 'sage' } })
    fireEvent.click(await screen.findByRole('button', { name: '들어 보기' })) // 재생이 시작되면 다시 누를 수 있다
    expect(played).toEqual(['/api/voices/nova/sample', '/api/voices/sage/sample?rate=1.35'])
  })

  it('미리 듣기를 바꿔 누르면 지난 소리가 멈춰도 오류를 보이지 않는다', async () => {
    stubServer()
    const pending: { reject: (e: unknown) => void }[] = []
    vi.stubGlobal(
      'Audio',
      class {
        onerror: (() => void) | null = null
        play() {
          return new Promise<void>((_resolve, reject) => pending.push({ reject }))
        }
        pause() {
          pending.at(0)?.reject(new DOMException('interrupted', 'AbortError'))
        }
      },
    )
    render(<SettingsScreen />)
    const play = await screen.findByRole('button', { name: '들어 보기' })
    fireEvent.click(play)
    expect(screen.getByRole('button', { name: '불러오는 중…' })).toBeDisabled()
    fireEvent.change(screen.getByRole('combobox', { name: '보이스' }), { target: { value: 'sage' } })
    // 불러오는 동안은 막혀 있으므로, 지난 소리를 직접 끊어 본다(다른 화면으로 가는 경우와 같다)
    pending[0].reject(new DOMException('interrupted', 'AbortError'))
    await Promise.resolve()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('추가하지 않은 관심사가 있으면 저장 전에 알리고, 되돌리기는 입력도 비운다', async () => {
    const fetchMock = stubServer()
    render(<SettingsScreen />)
    fireEvent.change(await screen.findByRole('textbox', { name: '호칭' }), { target: { value: '민수' } })
    fireEvent.change(screen.getByRole('textbox', { name: '새 관심사' }), { target: { value: '전시' } })
    fireEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(screen.getByRole('alert')).toHaveTextContent('"추가"로 넣거나 지운 뒤')
    expect(putBodies(fetchMock)).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: '되돌리기' }))
    expect(screen.getByRole('textbox', { name: '새 관심사' })).toHaveValue('')
    expect(screen.getByRole('textbox', { name: '호칭' })).toHaveValue('다니엘님')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('불러오기에 실패하면 다시 불러올 수 있다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    render(<SettingsScreen />)
    expect(await screen.findByRole('alert')).toHaveTextContent('서버에 연결할 수 없어요.')
    stubServer()
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }))
    expect(await screen.findByRole('textbox', { name: '호칭' })).toHaveValue('다니엘님')
  })
})
