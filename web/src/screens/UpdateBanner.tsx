// 새 버전 알림(계획서 S3-14). 서비스 워커가 새 앱을 받아 두면 버튼을 보이고, 누르면 새 버전으로 다시 연다.
// 대화 중에 페이지가 저절로 다시 열리면 안 되므로 자동으로 바꾸지 않는다(vite.config.ts의 registerType: 'prompt').
// 홈 화면 앱은 오래 열려 있으므로 한 시간마다 새 버전을 확인한다.
import { useRegisterSW } from 'virtual:pwa-register/react'

const CHECK_MS = 60 * 60 * 1000

export function UpdateBanner() {
  const {
    needRefresh: [needRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      if (registration) setInterval(() => void registration.update().catch(() => {}), CHECK_MS)
    },
  })
  if (!needRefresh) return null
  return (
    <div className="update-banner" role="status">
      <span>새 버전이 있어요. 대화를 마친 뒤 적용해 주세요.</span>
      <button type="button" className="secondary" onClick={() => void updateServiceWorker(true)}>
        새 버전 적용
      </button>
    </div>
  )
}
