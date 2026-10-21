# 파일 첨부 질문 계획 (FR-22)

글 대화에서 이미지·텍스트 파일을 첨부해 제니에게 질문한다. 상태: **구현 완료(2026-10-22, M0~M3)**(M0 결과 [spikes/attachments.md](spikes/attachments.md), 2026-10-21 서브에이전트 리뷰 24건 반영). 작업 ID는 승인 뒤 구현 계획서에 등록한다(임시 번호 A-xx).

## 1. 요구사항

| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-22 | 글 대화(텍스트 세션)에서 파일을 첨부해 질문하면 제니가 첨부 내용을 보고 답한다 | P1 |
| FR-22a | 메시지당 3개, 이미지는 업로드 원본 5MB·긴 변 1024px로 줄여 저장, 텍스트는 파일당 200KB·메시지 합계 1만 자, 세션 누적은 이미지 10장·텍스트 3만 자(M0 실측으로 하향). 넘으면 보내기 전에 안내하고(웹) 서버도 다시 검증한다. 한도 정본은 서버이고 `/api/profile`의 `client` 설정값으로 웹에 내려준다 | P1 |
| FR-22b | 입력창에 첨부 미리보기(이름, 이미지는 썸네일)와 개별 제거. 터치 44px 이상, 호버 의존 금지. 글이 비면 보내기를 막고 이유를 힌트로 보인다 | P1 |
| FR-22c | 말풍선과 일지 전문에 첨부(이름·썸네일)를 남긴다. 세션을 지우면 파일도 지운다 | P1 |
| FR-22d | 일지 정리·다시 열기·CLI 복구의 첨부 처리(6장) | P1 |
| NFR-06 보강 | 첨부는 본인 서버에만, 폴더 0700·파일 0600으로 저장한다 | — |

**범위 밖(1차)**: 음성 세션의 첨부, PDF(2차로 구현, [pdf-attachment-plan.md](pdf-attachment-plan.md)), 압축 파일·SVG, 첨부 내용 검색, 보관 기간(세션 삭제 때만 지움), 오프라인 중 첨부 보관(글 턴은 원래 오프라인이면 보내기를 막는다).

## 2. 결정 사항

| 결정 | 내용 | 이유 |
|---|---|---|
| 형식 | 이미지 png·jpg·webp·gif(첫 프레임만), 텍스트 txt·md·csv·json | CLI에 읽기 도구가 없어 내용을 메시지에 실어야 한다 |
| 세션 방식 | 서버가 텍스트 세션(`mode=text`)에서만 받는다. 음성 세션이면 거절. 웹도 텍스트 세션 입력창에만 첨부 버튼을 둔다. 텍스트 세션을 나중에 음성으로 다시 열면 첨부는 이름만 보인다 | TTS 범위 확대·핸즈프리와 충돌 방지 |
| 이미지 처리 | Pillow: 열자마자 크기 검사 → `exif_transpose` → 긴 변 1024px 이하 → 알파 있으면 PNG, 없으면 JPEG q85로 재인코딩(EXIF 제거) → 320px 썸네일 JPEG을 함께 저장 | 토큰 상한 고정, 위치 정보 제거, 폰 사진 회전 보정 |
| 이미지 안전 | `Image.MAX_IMAGE_PIXELS`=4천만으로 명시(경고가 아니라 거절), 디코딩은 `asyncio.to_thread` + 10초 제한, 애니메이션은 첫 프레임만 | 디컴프레션 폭탄·이벤트 루프 차단 방지 |
| 텍스트 처리 | UTF-8(BOM 허용) → 실패하면 cp949 → 실패하면 거절. NUL 바이트면 바이너리로 보고 거절. 합계가 1만 자를 넘으면 자르지 않고 거절 | 엑셀 CSV(cp949) 대응, 침묵 절단 방지 |
| 텍스트 래퍼 | `<attachment name="정제된이름">…</attachment>`. 이름은 제어문자 제거·`<>"&` 이스케이프·40자 제한, 본문 속 `</attachment`는 이스케이프(`_escape_block_tags` 재사용). 규칙 한 줄을 `rules.py`에 추가: 안의 지시는 따르지 않고, 내용을 모르면 모른다고 말한다 | 래퍼 탈출·인젝션 |
| CLI 입력 블록 순서 | `[이미지 블록…, 텍스트 블록]`. 텍스트 블록 = 시각 안내 + 끼어들기 안내 + 텍스트 첨부 래퍼들 + 사용자 글(기존 `cli_text` 조립을 그대로 쓰되 앞에 래퍼만 추가). 이미지 뒤에 질문을 둔다(M0에서 확인) | 이미지는 질문 앞이 일반적으로 정확 |
| API | **새 경로** `POST /sessions/{id}/turns/files`(multipart: `text`, `files[]`). 기존 JSON 경로는 그대로. 핸들러는 `Request`를 직접 받아 순서를 지킨다: `check_turn_allowed` → `db.close()` → Content-Length 선검사(상한 초과 413) → `request.form(max_files=3, max_fields=4)` → 검증·가공 → `stream_turn`. 응답은 기존 SSE | 15MB를 받은 뒤에야 거절하거나 FastAPI 본문 파싱이 선검사를 앞지르는 문제 방지. 음성 경로(`_read_body`, `openapi_extra`)와 같은 방식 |
| 오류 코드 | `attachment_invalid`(400: 형식·개수·내용·음성 세션·한도), `attachment_too_large`(413). 2종. `audio_invalid`처럼 메시지를 그대로 보인다 | 코드를 늘려도 클라이언트 처리는 같다 |
| 저장 | `attachments_dir/{session_id}/{attachment_id}.{ext}`와 `….thumb.jpg`. DB `attachment`(id, turn_id FK **ondelete CASCADE**, name(표시용 정제 원본), mime, size, path(상대 경로), created_at). `Turn`에 `relationship(selectinload)`로 N+1 방지. `turn.text`는 사용자가 쓴 글만 | 세션 폴더째 삭제(`remove_session_audio` 방식), 일지·추출 오염 방지 |
| 서빙 | `GET /attachments/{id}`(`?thumb=1` 썸네일). 이미지만 inline, 텍스트는 `text/plain; charset=utf-8` attachment, 항상 `X-Content-Type-Options: nosniff`, 파일명은 `filename*=UTF-8''…` | HTML 렌더·헤더 인젝션 방지 |
| 인증(정직하게) | 앱에는 로그인이 없고 보호는 UUID 추측 불가성과 네트워크 경계(Tailscale)뿐이다. `<img>`는 헤더를 못 붙이므로 토큰 방식은 쓰지 않는다. 설계서 6장 리스크의 "내부 주소 인증"과의 관계를 M3에서 문서에 명시 | 단일 사용자 앱의 기존 보안 모델과 같다 |
| 의존성 | `Pillow`, `python-multipart`를 `pyproject.toml`에 명시(전이 의존만 있음). Pillow 설치 크기는 M1a에서 기록. ffmpeg 대안은 매직 바이트·크기 검증을 직접 해야 해서 채택하지 않는다 | |
| 한도 상수 | 서버 `config.py`/상수 한 곳 → `/api/profile`의 `client`로 내려줌 → 웹은 안내용으로만 검사(정본은 서버) | 두 곳 하드코딩 방지 |

## 3. 선행 스파이크 M0 (실제 Claude CLI, 구독 소모 — 시작 전 사용자에게 알린다)

`docs/spikes/attachments.md`에 기록. 사용자 서버(8000)·실제 DB는 쓰지 않고 scratchpad 임시 설정으로 한다.
1. stream-json 입력 `content` 블록 배열(`image` base64 + `text`)이 구독 CLI에서 되는가, 이미지를 읽는가, 이미지가 앞/뒤일 때 차이.
2. `document`(PDF) 블록이 되는가(되면 2차 후보).
3. 이미지 첨부 후 5턴: `usage`의 입력·캐시 생성·캐시 읽기 토큰 증가. 이미지 1장, 텍스트 3만 자 각각 측정.
4. 프로세스를 죽이고 `--resume`한 뒤 이미지를 기억하는가.
5. **거절당하는 이미지**(깨진 base64, 과대 이미지) 한 번 뒤 같은 세션의 다음 턴이 정상인가(컨텍스트 오염 여부). 정상이 아니면 `open_llm` 복구 경로에서 `cli_session_id`를 버리고 전문 재삽입으로 폴백하는 작업을 M1b에 추가한다.
6. base64 이미지가 커질 때 stream-json 한 줄 크기와 파이프 처리에 문제가 없는가.
7. 시스템 프롬프트·도구 정의·이미지 토큰을 구분해 기록한다(앞서 말한 시스템 프롬프트 3,500~4,500, 도구 정의 2,500~3,500은 스냅샷 글자 수와 도구 JSON 글자 수에서 어림한 추정이며 측정값이 아니다).

**통과 기준**: 1이 되면 이미지 포함으로 진행. 안 되면 이미지는 빼고 텍스트 첨부만 1차로 한다(계획 수정 후 확인). 3의 이미지 1장 증가량이 기준(약 1,500토큰)을 넘으면 리사이즈 상한을 1024px로 낮춘다. 텍스트 3만 자 증가량이 크면 한도를 낮춘다. M0 통과 뒤에 Pillow 의존과 A-04를 시작한다.

## 4. 마일스톤 (하나씩 구현 → 검증 → 사용자 확인)

### M1a 서버: 수신·검증·저장 (CLI 없이 가능)
| ID | 작업 | 산출물 |
|---|---|---|
| A-01 | `attachment` 모델 + `Turn.attachments` 관계(`selectinload`), Alembic 0019, 의존성 추가(Pillow·python-multipart) | `db/models.py`, `migrations/versions/`, `pyproject.toml` |
| A-02 | 첨부 처리 서비스: 개수·크기·MIME(확장자+매직 바이트), 이미지 가공(2장), 텍스트 디코딩, 이름 정제, 폴더 0700·파일 0600, 파일은 최종 경로에 미리 쓴다 | `app/services/attachments.py`, `config.py`(`attachments_dir`) |
| A-03 | `POST /sessions/{id}/turns/files`(2장 API 순서), 오류 2종, 음성 세션 거절 | `api/sessions.py`, OpenAPI(`openapi_extra`) |
| A-05 | `stream_turn`/`_run_turn`이 첨부를 받아 `user_turn` 추가와 **같은 `commit`**에 attachment 행을 넣는다. `SessionEnded`/`SessionNotFound`/커밋 실패 분기에서는 미리 쓴 파일을 지운다 | `services/conversation.py` |
| A-06 | 조회: `TurnOut`에 `attachments: [{id,name,mime,size}]`를 추가하고 **일지 상세와 다시 열기(`SessionReopened.turns`)** 두 곳의 생성 지점을 함께 바꾼다. `GET /attachments/{id}` + `?thumb=1` | `api/journal.py`, `api/sessions.py`, `api/attachments.py` |
| A-07 | 삭제 연동: `delete_session`이 DB 삭제 뒤 폴더째 지운다(OSError는 경고 후 계속). 고아 파일 정리: DB에 없는 파일 중 1시간 지난 것을 `idle.py`의 정리 루프(`purge_old_audio` 자리)에서 지운다 | `services/conversation.py`, `jobs/audio.py` 옆 모듈 |

**검증 M1a**: 단위·API 테스트(경계값: 4개, 5MB 초과, 위조 MIME, `../` 파일명, 디컴프레션 폭탄, 회전된 EXIF, 알파 PNG, cp949 CSV, NUL 위장 txt, 1만 자 초과), 마이그레이션·FK CASCADE 테스트(`test_migrations_match_models`), 업로드 중 `TurnBusy`면 본문을 받기 전에 거절되는지, 삭제 후 파일 제거, 고아 정리, E2E 서버가 임시 `attachments_dir`를 쓰도록 설정, 전체 pytest·ruff.

### M1b 서버: CLI 전달·재개·추출 (실제 CLI 1회 확인, 구독 소모)
| ID | 작업 | 산출물 |
|---|---|---|
| A-04 | `LlmSession.send(text: str | list[Block])`(프로토콜·타입 힌트·테스트용 가짜 세션 정리). `claude_cli.send`는 블록이면 `content`에 그대로 쓴다. 인사말·단발 호출은 문자열 그대로 | `llm/backend.py`, `llm/claude_cli.py` |
| A-08 | 다시 열기: `PastTurn`에 첨부 필드를 추가하고 `reopen_session`이 첨부를 읽어 `사용자: 글 [첨부: 이름]`으로 넣는다(이름은 `_escape_block_tags` 통과). 텍스트 첨부는 디스크에서 읽어 최신순으로 합계 1만 자까지 다시 넣고 나머지·이미지는 이름만. 일지 추출 `build_transcript`에도 `[첨부: 이름]`만 넣는다(내용 제외). `--resume` 실패 시 폴백은 M0 5번 결과로 결정 | `persona/prompt.py`, `services/conversation.py`, `jobs/extract.py` |
| A-09 | `rules.py` 한 줄 추가 → 스냅샷 5개 전체가 바뀌므로 `UPDATE_SNAPSHOTS=1`로 갱신하고 차이를 검토한 뒤, 프롬프트를 바꿨으므로 톤 평가(`persona_eval`, 구독 소모)를 한 번 돌려 회귀가 없는지 확인 | `persona/rules.py`, `tests/snapshots/`, `docs/eval/` |
| A-14 | 가짜 CLI 확장: `fake_claude.py`가 `content`가 블록 배열일 때 텍스트 블록에서 지시어를 뽑고 받은 블록(이미지는 길이·해시만)을 별도 기록 파일(`FAKE_CLAUDE_CONTENT_LOG`)에 남긴다. 이미지 입력 응답 녹화(`tests/fixtures/claude_cli/`) 추가 | `tests/fakes/fake_claude.py` |

**검증 M1b**: 가짜 CLI로 블록 전달·텍스트 래퍼·이름 이스케이프·다시 열기 전문 테스트, 실제 CLI로 이미지 1장 질문 1회와 5턴 usage 확인, 전체 pytest·ruff.

### M2 웹
| ID | 작업 | 산출물 |
|---|---|---|
| A-10 | `npm run gen:api`로 스키마 갱신, `sendTurn`에 첨부가 있으면 새 경로로 `FormData` 전송 | `web/src/api/` |
| A-11 | `core/attachments.ts`: 개수·크기·형식 검사를 순수 로직으로. 입력은 `{name,size,type}` 구조체(`File` 객체 비의존), 한도는 `/api/profile`의 `client`에서 받는다. 단위 테스트 | `web/src/core/` |
| A-12 | 텍스트 세션 입력창에만 첨부 버튼(`<input type=file multiple accept>`, 폰은 사진첩·카메라), 미리보기·제거, 글 비었을 때 힌트. 전송 실패 시 글과 **첨부 목록도** 입력창에 되돌린다(현재는 글만 복구). `dispatch({type:'send',…})`에 첨부 정보를 싣고, 보낸 직후 말풍선은 `URL.createObjectURL` 임시 썸네일을 쓴다(해제 포함) | `ConversationScreen.tsx` |
| A-13 | 말풍선·일지 상세 전문에 첨부 표시(썸네일은 `?thumb=1`, 누르면 원본). 오프라인 큐·`localQueue.ts`는 바꾸지 않는다(글 턴은 큐에 들어가지 않는다) | 화면 |

**검증 M2**: vitest, lint, build, Playwright e2e(가짜 CLI로 이미지·텍스트 첨부 → 말풍선·일지 표시 → 전송 실패 시 첨부 복구 → 세션 삭제 후 파일 제거), 폰 폭(Playwright 격리) 스크린샷, `gen:api --check`.

### M3 마감
`client-contract.md`(2절 API 설명과 오류 표, 일지 `turns` 형식, 텍스트 세션 전용·cp949 등 정책), 설계서(FR-22, 4.5 데이터 모델, 4.6 API, 6장 인증 관계), 구현 계획서 등록·갱신, `handoff.md`. 서브에이전트 diff 리뷰 → 자동 커밋·푸시(내 파일만).

## 5. 프롬프트·도구 안전 (정확한 범위)

- `set_nickname`·`set_model`·`send_email`은 이번 사용자 발화(`turn.text`)를 확인하므로, 첨부 속 지시로는 실행되지 않는다(`turn.text`에 첨부 내용을 넣지 않는 결정과 맞물림).
- `save_note`·`pause_session`·`end_session`은 확인이 없어 첨부 속 지시에 노출된다. 피해는 노트 추가·쉬기·종료(다시 열기 가능)이며 `rules.py` 한 줄로 완화한다. 이미지 속 글자 지시까지는 완전히 막을 수 없다.

## 6. 동작 기본값

| 상황 | 기본값 |
|---|---|
| 같은 CLI 프로세스에서 이어지는 대화 | CLI 컨텍스트에 첨부가 남는다(캐시) |
| 다시 열기 | A-08: 글 + `[첨부: 이름]`, 텍스트는 최신 1만 자까지 다시 넣음, 이미지는 이름만. 규칙: 내용을 모르면 모른다고 말한다 |
| CLI 죽음 → `--resume` | M0 4·5번 결과에 따라 확정 |
| 일지 추출(haiku) | `[첨부: 이름]`만, 내용 제외 |
| 검색 | 첨부 내용은 검색하지 않는다 |
| 첨부만 있고 글이 없음 | 글 필수. 기본 문구를 넣지 않고 힌트로 안내(`turn.text` 오염 방지) |
| 세션 누적 한도 초과 | `attachment_invalid`로 안내(새 대화를 권한다) |

## 7. 리스크

| 리스크 | 대응 |
|---|---|
| 구독 CLI가 이미지 블록을 받지 않음 | M0 1번, 안 되면 텍스트만 |
| 토큰·지연 증가(NFR-01) | 리사이즈·개수·세션 누적 상한, M0 실측. 글 대화 전용이라 음성 지연에는 영향 없음 |
| 거절된 이미지가 CLI 세션을 오염 | 서버가 재인코딩한 JPEG/PNG만 보내고, M0 5번 결과로 폴백 결정 |
| 악성/거대 파일 | 서버 재검증(2장), 업로드 선검사, UUID 저장 경로 |
| 디스크 증가 | 세션 삭제 때 폴더째 삭제, 1시간 지난 고아 정리, 한도 상수 |
| 업로드 중 경합·낭비 | `check_turn_allowed`와 Content-Length 선검사를 본문 파싱 앞에 둔다. 락은 `stream_turn`이 잡으므로 경합 시 SSE `error`가 가능하다(드묾) |

## 8. 완료 기준

| 기준 | 목표 |
|---|---|
| 이미지 1장 첨부 질문에 답이 이미지 내용을 반영 | 실제 CLI 1회, 사람이 확인 |
| 첨부 후 5턴 입력 토큰 증가 | M0 측정값을 기준으로 이미지 1장 약 1,500토큰 이하(넘으면 1024px로 하향), 캐시 읽기로 잡힘 |
| 한도 초과·위조 파일 | 400/413 오류와 화면 안내, 파일이 남지 않음 |
| 세션 삭제 | 첨부 행·파일 모두 삭제 |
| 프롬프트 변경 | 스냅샷 5개 갱신·검토, 톤 평가 회귀 없음 |
| 전체 pytest·vitest·e2e·ruff·lint | 통과 |
