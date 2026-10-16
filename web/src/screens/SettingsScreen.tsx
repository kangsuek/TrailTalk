// 설정 화면(계획서 S3-18, 설계서 FR-17): 호칭, 관심사, 보이스(미리 듣기), 말 속도, 음성 원본 보관.
// 바뀐 필드만 저장한다(core/settings). 호칭·관심사는 다음 대화의 프롬프트에, 보이스·말 속도는 다음 답변부터 쓴다.
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError } from '../api/http'
import { getProfile, getVoices, updateProfile, voiceSampleUrl, type Profile, type Voices } from '../api/profile'
import {
  addInterest,
  changedFields,
  draftOf,
  MAX_INTEREST_LENGTH,
  MAX_INTERESTS,
  MAX_NICKNAME_LENGTH,
  RATE_CHOICES,
  type SettingsDraft,
} from '../core/settings'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; profile: Profile; voices: Voices }

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

export function SettingsScreen() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([getProfile(controller.signal), getVoices(controller.signal)])
      .then(([profile, voices]) => setState({ kind: 'ready', profile, voices }))
      .catch((error) => {
        if (!controller.signal.aborted) {
          setState({ kind: 'error', message: errorMessage(error, '설정을 불러오지 못했어요.') })
        }
      })
    return () => controller.abort()
  }, [attempt])

  return (
    <section className="settings">
      <h2>설정</h2>
      {state.kind === 'loading' && <p className="settings-note">불러오는 중…</p>}
      {state.kind === 'error' && (
        <div className="settings-note">
          <p role="alert">{state.message}</p>
          <button
            type="button"
            onClick={() => {
              setState({ kind: 'loading' })
              setAttempt((n) => n + 1)
            }}
          >
            다시 불러오기
          </button>
        </div>
      )}
      {state.kind === 'ready' && (
        <SettingsForm
          profile={state.profile}
          voices={state.voices}
          onSaved={(profile) => setState({ ...state, profile })}
        />
      )}
    </section>
  )
}

function SettingsForm({
  profile,
  voices,
  onSaved,
}: {
  profile: Profile
  voices: Voices
  onSaved: (profile: Profile) => void
}) {
  const [draft, setDraft] = useState<SettingsDraft>(() => draftOf(profile))
  const [interest, setInterest] = useState('')
  const [interestError, setInterestError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [sampleError, setSampleError] = useState<string | null>(null)
  const [sampleLoading, setSampleLoading] = useState(false)
  const player = useRef<HTMLAudioElement | null>(null)

  const patch = changedFields(profile, draft)
  const dirty = Object.keys(patch).length > 0
  const change = (next: Partial<SettingsDraft>) => {
    setDraft((current) => ({ ...current, ...next }))
    setResult(null)
  }

  // 화면을 떠나면 미리 듣기를 멈춘다(멈춘 소리의 결과는 아래 핸들러가 무시한다)
  useEffect(
    () => () => {
      const audio = player.current
      player.current = null
      audio?.pause()
    },
    [],
  )

  const add = () => {
    const added = addInterest(draft.interests, interest)
    if ('error' in added) return setInterestError(added.error)
    setInterestError(null)
    setInterest('')
    change({ interests: added.interests })
  }
  const onInterestKey = (event: KeyboardEvent<HTMLInputElement>) => {
    const composing = event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229
    if (event.key === 'Enter' && !composing) {
      event.preventDefault()
      add()
    }
  }

  const playSample = () => {
    setSampleError(null)
    const previous = player.current
    const audio = new Audio(voiceSampleUrl(draft.voice ?? voices.default_voice, draft.speakingRate))
    player.current = audio
    previous?.pause()
    // 처음 합성은 몇 초 걸린다. 그동안 버튼을 막고, 바꿔 누른 뒤 온 지난 소리의 결과는 무시한다
    setSampleLoading(true)
    const current = () => player.current === audio
    const failed = (error?: unknown) => {
      if (!current() || (error instanceof DOMException && error.name === 'AbortError')) return
      setSampleLoading(false)
      setSampleError('지금은 목소리를 들려줄 수 없어요.')
    }
    audio.onerror = () => failed()
    audio
      .play()
      .then(() => current() && setSampleLoading(false))
      .catch(failed)
  }

  const save = (event: FormEvent) => {
    event.preventDefault()
    if (!dirty || saving) return
    if (interest.trim()) {
      // 입력만 하고 "추가"를 누르지 않은 관심사를 말없이 버리지 않는다
      setInterestError('입력한 관심사를 "추가"로 넣거나 지운 뒤 저장해 주세요.')
      return
    }
    setSaving(true)
    setResult(null)
    updateProfile(patch)
      .then((saved) => {
        onSaved(saved)
        setDraft(draftOf(saved))
        setResult({
          ok: true,
          message: '저장했어요. 호칭·관심사는 다음 대화부터, 보이스·말 속도는 다음 답변부터 적용돼요.',
        })
      })
      .catch((error) => setResult({ ok: false, message: errorMessage(error, '저장하지 못했어요. 다시 해 주세요.') }))
      .finally(() => setSaving(false))
  }

  // 선택지에 없는 말 속도(API로 정한 값)도 보이게 한다
  const rateChoices = RATE_CHOICES.some((c) => c.value === draft.speakingRate)
    ? RATE_CHOICES
    : [...RATE_CHOICES, { label: `${draft.speakingRate}배`, value: draft.speakingRate }]

  return (
    <form className="settings-form" onSubmit={save}>
      {/* 저장하는 동안 고친 값이 저장 결과에 덮어써지지 않게 입력을 막는다 */}
      <fieldset className="settings-fields" disabled={saving}>
        <label className="settings-field">
          <span className="settings-label">호칭</span>
          <input
            type="text"
            value={draft.nickname}
            maxLength={MAX_NICKNAME_LENGTH}
            placeholder="비워 두면 기본 호칭"
            onChange={(e) => change({ nickname: e.target.value })}
          />
        </label>

        <fieldset className="settings-field">
          <legend className="settings-label">관심사</legend>
          <p className="settings-note">대화와 지난 이야기 기억에 참고해요(최대 {MAX_INTERESTS}개).</p>
          {draft.interests.length > 0 && (
            <ul className="settings-chips" aria-label="관심사 목록">
              {draft.interests.map((item) => (
                <li key={item}>
                  <span>{item}</span>
                  <button
                    type="button"
                    className="chip-remove"
                    aria-label={`관심사 삭제: ${item}`}
                    onClick={() => change({ interests: draft.interests.filter((i) => i !== item) })}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="settings-row">
            <input
              type="text"
              aria-label="새 관심사"
              value={interest}
              maxLength={MAX_INTEREST_LENGTH}
              placeholder="예: 등산"
              onChange={(e) => setInterest(e.target.value)}
              onKeyDown={onInterestKey}
            />
            <button type="button" className="secondary" onClick={add} disabled={draft.interests.length >= MAX_INTERESTS}>
              추가
            </button>
          </div>
          {interestError && (
            <p className="settings-error" role="alert">
              {interestError}
            </p>
          )}
        </fieldset>

        <div className="settings-field">
          <label className="settings-label" htmlFor="settings-voice">
            보이스
          </label>
          <div className="settings-row">
            <select
              id="settings-voice"
              value={draft.voice ?? ''}
              onChange={(e) => change({ voice: e.target.value || null })}
            >
              <option value="">캐릭터 기본({voices.default_voice})</option>
              {voices.voices.map((voice) => (
                <option key={voice} value={voice}>
                  {voice}
                </option>
              ))}
            </select>
            <button type="button" className="secondary" onClick={playSample} disabled={sampleLoading}>
              {sampleLoading ? '불러오는 중…' : '들어 보기'}
            </button>
          </div>
          {sampleError && (
            <p className="settings-error" role="alert">
              {sampleError}
            </p>
          )}
        </div>

        <fieldset className="settings-field">
          <legend className="settings-label">말 속도</legend>
          <div className="settings-row">
            {rateChoices.map((choice) => (
              <label key={choice.label} className="settings-choice">
                <input
                  type="radio"
                  name="speaking-rate"
                  checked={draft.speakingRate === choice.value}
                  onChange={() => change({ speakingRate: choice.value })}
                />
                {choice.label}
              </label>
            ))}
          </div>
        </fieldset>

        <label className="settings-field settings-toggle">
          <input type="checkbox" checked={draft.keepAudio} onChange={(e) => change({ keepAudio: e.target.checked })} />
          <span>
            <span className="settings-label">음성 원본 보관</span>
            <span className="settings-note">
              켜면 음성 대화의 녹음을 서버에 30일 동안 보관했다가 지워요(본인만 읽을 수 있게 저장).
            </span>
          </span>
        </label>
      </fieldset>

      <div className="settings-actions">
        <button type="submit" disabled={!dirty || saving}>
          {saving ? '저장하는 중…' : '저장'}
        </button>
        {dirty && !saving && (
          <button
            type="button"
            className="secondary"
            onClick={() => {
              change(draftOf(profile))
              setInterest('')
              setInterestError(null)
            }}
          >
            되돌리기
          </button>
        )}
      </div>
      {result && (
        <p className={result.ok ? 'settings-note' : 'settings-error'} role={result.ok ? 'status' : 'alert'}>
          {result.message}
        </p>
      )}
    </form>
  )
}
