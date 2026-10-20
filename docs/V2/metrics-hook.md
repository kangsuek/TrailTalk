# 공통 계측 훅 (`window.__tt_metrics`)

V2-M0-05. V1 코드와 V2 코드가 **같은 정의**로 값을 내서 기준선(M0)과 개선 후(M1·M2)를 비교할 수 있게 한다. 구현은 `web/src/core/metrics.ts`(순수 TS), 브라우저 인스턴스는 `web/src/platform/metrics.ts`다. 평가는 Playwright에서 `page.evaluate(() => window.__tt_metrics)`로 읽는다.

## 형태

```ts
window.__tt_metrics = {
  frames: { t: number; p: number }[],   // VAD 프레임(약 32ms마다). p = 음성 확률 0~1. 최근 3000개
  marks:  { t: number; type: string; data?: Record<string, number|string|boolean|null> }[], // 최근 1000개
  frame(p), mark(type, data?), clear(),
}
```

- `t`는 `performance.now()`(단조 ms)로, 지연 측정(`speechEndedAt`, `requestAt`)과 같은 시계다.
- 넘치면 오래된 것부터 버린다. `clear()`는 같은 배열 객체를 비운다(이미 잡은 참조도 비워진다).

## 표식 (`marks.type`)

| type | 언제 | data |
|---|---|---|
| `vad_raw_start` | vad-web이 말소리를 처음 잡음(`onSpeechStart`, 확정 전) | `mode` |
| `vad_confirm` | 말소리 확정(`onSpeechRealStart`, V1은 누적 `min_speech_ms`) | `mode` |
| `vad_misfire` | 확정 전에 끝난 짧은 소리(`onVADMisfire`) | `mode` |
| `vad_end` | 발화 끝(`onSpeechEnd`, 무음 대기 뒤) | `mode`, `silence_ms`(적용된 무음 대기) |
| `vad_mode` | `setMode`로 임계값 모드 변경 | `mode`(`normal`·`playback`) |
| `playback_start` | 소리 하나의 재생 시작 | `index`(문장 번호, 없으면 null) |
| `source_stop` | 재생 중인 `AudioBufferSourceNode.stop()` 호출 직후 | `index` |
| `volume` | 재생 볼륨 변경(V2 ducking·페이드) | `gain`. **V1은 볼륨을 바꾸지 않아 기록하지 않는다** |

정지 지연 = (`vad_confirm` 시각, 재생 모드) → (이후 첫 `source_stop` 시각). 감지→확정 지연 = `vad_raw_start` → `vad_confirm`.

## 끼어들기 기록 (`barge_in_event`)

컨트롤러(`voiceController.ts`)가 **답변을 들려주는 중(`speaking`)에 말소리가 확정되면**(`speech_start`) 한 건을 만든다. 버튼으로 끼어들기는 기록하지 않는다.

| 필드 | 뜻 |
|---|---|
| `id` | 기기가 만든 UUID(다시 올려도 한 행) |
| `session_id`, `turn_id` | 대화와 끊긴 답변 턴 |
| `occurred_at` | 확정 시각(기기 시계, ISO) |
| `probe_to_confirm_ms` | `vad_raw_start` → 확정. V1에는 probe가 없어 vad-web의 첫 프레임 감지 시각을 쓴다 |
| `stop_ms` | 확정 → `output.stop()` 반환. V1은 같은 흐름이라 보통 0~수 ms(블루투스 출력 지연은 포함하지 않는다) |
| `played_ratio` | 끊긴 문장을 들려준 비율. M2에서 채운다(M0은 null) |
| `result` | 아래 값. CHECK 없는 문자열(32자 이하) |
| `next_turn_id` | 끼어든 말이 만든 답변 턴. 답변이 오기 전에 대화가 끝나면 null |

`result` 값: `real`(기본), `suspected_false`(끼어든 말이 `no_speech`로 인식되지 않음 — 근사), `probe_reverted`(M2, 감지 뒤 되돌림), `user_marked_false`(M2, 사용자가 "방금 오작동" 표시).

**기기 큐**: 기록은 `localStorage`(`tt.bargeInEvents`, 최대 200개)에 모은 뒤 `POST /api/barge-in-events`로 올린다. 올리지 못하면 남겨 두고 기록을 만들 때·대화를 시작할 때 다시 올린다. 서버는 같은 `id`를 건너뛰므로 다시 올려도 안전하다. 저장소를 못 쓰면 이 탭이 열려 있는 동안만 메모리에 모은다.

## 알려진 한계

- `stop_ms`는 확정 직후 `d.now() - confirmAt`이다. 컨트롤러가 다른 이벤트를 처리하는 중이면 이벤트가 큐에 들어가 `output.stop()` 전에 재므로 0에 가깝게 나올 수 있다(드묾). 정확한 정지 시각은 훅의 `source_stop` 표식을 쓴다.
- `next_turn_id`는 끼어든 뒤 처음 시작된 턴에 붙인다. 끼어든 말이 아니라 그 전에 큐에 있던 말이 먼저 턴을 만들면 어긋날 수 있다(M0 통계용 근사). 끼어든 말이 오프라인·인식 실패 외의 오류로 끝나면 다음 끼어들기나 대화 종료 때 `next_turn_id` 없이 `real`로 확정된다.
- 서버가 형식을 거절(4xx)한 배치는 기기에서 버린다. `window.__tt_metrics`는 운영 빌드에도 노출된다(메모리 상한 안에서만 쌓는다).
