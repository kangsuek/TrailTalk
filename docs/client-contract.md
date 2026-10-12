# 클라이언트 규약 (초안)

웹 앱과 안드로이드 앱이 함께 지키는 규약이다. 설계서 4.8을 기준으로 하며, 3단계([구현 계획서](implementation-plan.md) S3-15)에서 확정한다. 확정 전까지는 각 절이 비어 있을 수 있다.

## 1. API

- 모든 서버 API는 `/api` 아래에 둔다(예: `/api/health`, `/api/sessions`).
- 타입은 FastAPI OpenAPI 스키마에서 생성한다: 웹은 openapi-typescript, 안드로이드는 openapi-generator.

## 2. SSE 이벤트

`transcript`, `sentence`, `tool`, `done`, `error`. JSON 스키마는 1단계(S1-09)에서 초안, 3단계에서 확정.

## 3. 오디오 형식

업로드 16kHz 모노 Opus, 응답 문장별 MP3.

## 4. 세션 상태 머신

상태: 대기, 듣기, 처리 중, 말하기, 쉬기, 오프라인 보관, 정리. 전이 표는 `shared/fixtures/transitions.json`(S3-09).

## 5. 클라이언트 설정값

기본값은 `shared/client-defaults.json`, 실제 값은 서버 `/api/profile`이 내려준다.

## 6. 알림음·안내 문구

`shared/sounds/`의 효과음과 `shared/client-defaults.json`의 안내 문구를 사용한다.
