# Claude CLI 검증 스파이크 결과 (S0-04)

- 일시: 2026-10-12
- 대상: Claude Code CLI 2.1.296, 모델 별칭 `haiku`(claude-haiku-5-5)·`sonnet`(claude-sonnet-5-5)
- 인증: 1~7은 구독 로그인(macOS 키체인), 8은 `claude setup-token` 토큰(S0-05)
- 스크립트: [claude-cli/](claude-cli/) — 저장소 루트에서 `uv run --project server python docs/spikes/claude-cli/<스크립트>`로 실행
- 녹화 샘플: `server/tests/fixtures/claude_cli/*.jsonl` (경로·세션 ID 치환)

## 결론

설계서 4.9의 방식(세션마다 상주 CLI 프로세스 + stream-json 입출력)은 **그대로 쓸 수 있다**. 대체 방안(턴마다 `--resume`)은 필요 없다. 단, 1단계 구현에 반드시 반영할 조건이 다섯 가지 있다.

1. MCP 도구를 쓰려면 CLI 프로세스 환경에 `ENABLE_TOOL_SEARCH=false`를 넣는다. 기본값에서는 MCP 도구가 지연 로딩 대상이라, 내장 도구를 모두 끈 상태(`--tools ""`)에서는 모델이 도구를 호출하지 못한다.
2. 오류 판정은 `result.is_error`로 한다. 잘못된 모델명 오류에서도 `subtype`이 `success`로 온다.
3. 인터럽트는 stdin 제어 메시지로 한다. 시그널은 필요 없다.
4. 인터럽트 후에도 모델 맥락에는 생성된 부분 출력이 남는다. "들려준 문장까지만 기록"은 DB 기록 기준일 뿐, 모델은 더 들은 것처럼 이어 말할 수 있다.
5. 격리 옵션을 써도 계정 이메일과 실행 환경 정보(작업 폴더, OS, 날짜)가 자동으로 맥락에 붙는다. 키체인 로그인과 토큰 방식 모두 그렇다(4·8). 이를 끄는 옵션은 찾지 못했다.

## 항목별 결과

### 1. 다중 턴 스트리밍 — 통과

`check_multiturn.py`. 프로세스 1개에 3턴을 보냈고, 모두 같은 프로세스·같은 `session_id`로 처리됐다. 3턴째에 앞선 두 과일 이름을 기억했다.

```
턴1 첫 부분출력 1.72s, 전체 2.12s, delta 9개, result=success
턴2 첫 부분출력 0.76s, 전체 1.06s, delta 3개, result=success
턴3 첫 부분출력 0.60s, 전체 0.93s, delta 3개, result=success | '사과와 바나나입니다.'
```

턴 하나의 이벤트 순서:

| 순서 | 이벤트 | 쓰임 |
|---|---|---|
| 턴 시작 | `system/init` | 턴마다 다시 온다(프로세스 시작 시 1회가 아님). `session_id`, `tools`, `mcp_servers`, `model`. 턴 시작 표지로 쓸 수 있다 |
| | `system/status`(requesting) | 무시 |
| | `stream_event`: `message_start` → `content_block_start` → `content_block_delta`(`text_delta`) … | `text_delta`를 이어 붙여 문장 분할기에 넣는다 |
| | `assistant` | 완성된 메시지. `tool_use` 블록이 여기 들어온다. **블록 종료 이벤트보다 먼저 올 수 있다** |
| | `stream_event`: `content_block_stop` → `message_delta` → `message_stop` | 메시지 종료 |
| | `user` | 도구 결과(`tool_result`) |
| | `rate_limit_event` | 구독 한도 상태. 사용량 모니터링에 쓸 수 있다 |
| 턴 끝 | `result` | 턴 경계. `is_error`, `result`(최종 텍스트), `ttft_ms`, `usage` |

입력 형식: 한 줄에 하나씩 `{"type":"user","message":{"role":"user","content":"..."}}`.

### 2. 인터럽트 — 통과

`check_interrupt.py`. 1~200을 나열하는 도중 stdin으로 아래 메시지를 보냈다.

```json
{"type":"control_request","request_id":"req_xxxx","request":{"subtype":"interrupt"}}
```

```
control_response: success request_id 일치: True
인터럽트 후 result까지 0.02s: subtype=error_during_execution, is_error=True, terminal_reason=aborted_streaming
다음 턴 정상: result=success | '1부터 200까지 숫자를 쉼표로 구분해 나열하던 중이었는데, 37에서 중단되었습니다.'
```

- 즉시 멈추고(`terminal_reason=aborted_streaming`), 같은 프로세스로 다음 턴이 이어진다.
- 중단된 턴의 `result`는 `is_error=True`다. 서버는 이를 오류가 아닌 "중단됨"으로 처리해야 한다.
- 모델은 클라이언트가 읽어 간 부분(17 근처)보다 많은 37까지를 기억했다. 끼어들기 직후 제니가 "아까 말하던 거"를 언급하면 사용자가 듣지 못한 내용일 수 있다. 필요하면 다음 턴 입력 앞에 "(사용자는 N번째 문장까지만 들었다)" 같은 메모를 붙인다.

### 3. 옵션 조합 — 통과(조건부)

`check_tools_mcp.py`(기본 `ENABLE_TOOL_SEARCH=false`, 비교하려면 `check_tools_mcp.py true`). 도구 호출이 있었을 때만 `tool_call.jsonl`을 녹화한다. 검증용 MCP 서버([notes_mcp.py](claude-cli/notes_mcp.py), `save_note` 하나)를 `--mcp-config`로 연결했다.

| 옵션 | 결과 |
|---|---|
| `--system-prompt` | 페르소나 반영됨("안녕하세요, 다니엘님! 저는 제니예요") |
| `--model haiku` / `--model sonnet` | `init.model`이 각각 `claude-haiku-5-5`, `claude-sonnet-5-5` |
| `--mcp-config` + `--strict-mcp-config` | `init.mcp_servers`에 `trailtalk`만 `connected` |
| `--tools ""` | 내장 도구 0개. `ls` 실행 요청에 "실행할 수 없다"고 답함 |
| `--allowedTools "mcp__trailtalk__*"` | 권한 거부 없이(`permission_denials: []`) 도구 실행 |
| 기본 환경 | **`save_note`를 호출하지 않음**("저장할 수 있는 도구가 없다"고 답함) |
| `ENABLE_TOOL_SEARCH=false` | `save_note(kind="idea", content="등산로에 쓰레기통 위치를 표시한 지도를 만드는 아이디어")` 호출, MCP 서버 기록 확인 |

참고: 시험용 페르소나에 이모지 금지 규칙이 없어 답변에 이모지가 섞였다. `jenny.yaml`의 `avoid: [이모지]`가 프롬프트에 들어가는지 S1-05·S1-11에서 확인한다.

### 4. 격리 — 부분 통과

`check_isolation.py`. 작업 폴더에 "비밀 단어는 블루베리42" CLAUDE.md를 두고 비교했다.

| 구분 | 프로젝트 CLAUDE.md | 사용자 전역 CLAUDE.md | 연결된 MCP 커넥터 |
|---|---|---|---|
| 격리 옵션 없음 | 읽힘(비밀 단어 존재를 언급) | 읽힘("Plan Mode", "Playwright" 언급) | 5개(Gmail, Claude Docs 등) |
| 격리 옵션 적용 | 차단 | 차단 | 0개 |

격리 옵션: `--restricted --strict-mcp-config --setting-sources ""` + 빈 임시 작업 폴더. `--tools ""`(내장 도구 0개)는 두 경우 모두 적용했다.

격리 후에도 남는 것:
- 계정 정보(이메일)와 실행 환경(작업 폴더, OS, 셸, 날짜)이 맥락에 붙는다. `check_account_context.py`로 "맥락에 이메일이 있으면 도메인만 답하라"고 물었을 때 키체인·토큰 방식 모두 2회씩 `gmail.com`을 답했다.
- `init`에 내장 플러그인 3개와 사용자 스킬 목록이 보이지만, 도구가 없어 호출할 수 없다.
- `--bare`는 OAuth·키체인을 읽지 않아(API 키 전용) 구독 방식에서는 쓸 수 없다.

판단: 계정 이메일은 사용자 본인의 것이므로 본인용 운영(설계서 4.9의 전제)에서는 허용 가능하다. 페르소나 프롬프트에 "사용자 개인정보·실행 환경 정보는 언급하지 않는다"를 넣는다. 서비스화(D6) 때는 API 키 방식(`--bare` 가능)으로 바꾸므로 해소된다.

### 5. 세션 복구 — 통과

`check_resume.py`. 세션 저장을 켠 첫 프로세스에서 숫자 7342를 기억시키고 종료한 뒤, `--resume <session_id>`로 새 프로세스를 띄웠다.

```
재개 후 session_id 동일: True
맥락 유지: True | 7342야.
다른 작업 폴더에서 재개: success | 7342야.
```

- 복구를 쓰려면 `--no-session-persistence`를 빼야 한다. 세션 파일은 `~/.claude/projects/` 아래에 쌓이므로, 1단계에서 세션 종료 후 정리 방식을 정한다.

### 6. 지연 — 통과

`check_latency.py`. 첫 `text_delta`까지의 시간이다. 콜드 스타트는 프로세스 기동부터, 상주는 메시지 전송부터 쟀다. 5회 측정의 중앙값이다.

| 모델 | 콜드 스타트 | 상주 프로세스 |
|---|---|---|
| haiku | 1.557s | 0.677s |
| sonnet | 1.619s | 0.740s |

- 상주 프로세스가 턴당 약 0.9초 빠르다. 설계서의 상주 방식을 유지한다.
- 1단계 완료 기준인 "첫 `sentence` 이벤트 2초 이내"는 상주 sonnet 0.74s에 첫 문장이 완성되기까지의 시간을 더해도 달성 가능하다고 본다.

### 7. 녹화 — 완료

| 파일 | 내용 |
|---|---|
| `multiturn.jsonl` | 3턴 정상 대화 |
| `interrupt.jsonl` | 생성 중 인터럽트 → 다음 턴 |
| `tool_call.jsonl` | 페르소나 인사, `save_note` 도구 호출·결과, 내장 도구가 없어 `ls` 실행 요청을 말로 거절 |
| `error_invalid_model.jsonl` | 잘못된 모델명(`is_error=true`, `subtype=success`, 종료 코드 1) |

공개 저장소용으로 홈 경로, 임시 폴더 경로, 세션 ID, 개인 스킬·플러그인 목록을 치환했다.

### 8. 토큰 인증 — 통과 (S0-05)

`check_token.py`. 사용자가 `claude setup-token`으로 발급한 토큰을 저장소 루트 `.env`(git 무시 대상)에 넣고, 스크립트가 이 값을 읽어 CLI 자식 프로세스의 환경 변수로만 넘겼다. 토큰 값은 출력하지 않는다.

```
apiKeySource: none | model: claude-haiku-5-5
result: success is_error: False | 토큰 인증 확인
잘못된 토큰: is_error= True | Failed to authenticate. API Error: 401 OAuth access token is invalid.
```

- 잘못된 토큰이면 401로 실패하므로, `CLAUDE_CODE_OAUTH_TOKEN`이 키체인 로그인보다 우선한다. 서버는 키체인 없이 토큰만으로 동작한다.
- 토큰 방식에서도 계정 이메일은 맥락에 붙는다(4절 `check_account_context.py`). 처음에 예/아니오로 물었을 때 토큰 쪽이 "모름"이라고 답한 적이 있었지만, 같은 질문을 다시 하면 "알고 있음"으로 답이 흔들렸다. 실제 값(도메인)을 묻는 방식으로 다시 확인해 바로잡았다.

비밀값 관리 방식:
- 토큰은 저장소 루트 `.env`의 `CLAUDE_CODE_OAUTH_TOKEN`에만 둔다. `.gitignore`가 `.env*`를 막고 `.env.example`만 커밋한다.
- 서버는 pydantic-settings로 읽어 CLI 프로세스를 띄울 때 환경 변수로만 전달한다. 로그·오류 응답·SSE에 절대 넣지 않는다.
- 배포 서버(결정 D1)에서는 같은 방식으로 서버 전용 `.env`를 두고 파일 권한을 소유자 읽기 전용(600)으로 한다.
- 토큰은 장기 토큰이므로, 유출이 의심되면 claude.ai 설정에서 폐기하고 다시 발급한다.

## 1단계 반영 사항

| 대상 | 반영 내용 |
|---|---|
| S1-03 `ClaudeCliBackend` | 실행 인자: `-p --input-format stream-json --output-format stream-json --include-partial-messages --verbose --model <m> --tools "" --restricted --strict-mcp-config --setting-sources "" --system-prompt <p> --mcp-config <c> --allowedTools "mcp__trailtalk__*"`. 환경: `ENABLE_TOOL_SEARCH=false`, `CLAUDE_CODE_OAUTH_TOKEN`. 작업 폴더: 세션별 빈 폴더 |
| S1-03 파서 | 턴 경계는 `result`. `system/init`은 턴마다 오고 `assistant`는 블록 종료보다 먼저 올 수 있다. 오류는 `is_error`로 판정. 중단은 `terminal_reason=aborted_streaming`. JSON이 아닌 줄은 건너뛴다 |
| S1-03 프로세스 | stderr는 백그라운드로 계속 읽어 로그로 보낸다(파이프에 쌓이지 않게). 예외 시에도 프로세스와 임시 작업 폴더를 정리한다 |
| S1-03 인터럽트 | `control_request`/`interrupt` 전송 후 `result`까지 읽고 버림 |
| S1-03 복구 | 세션 저장을 켜고 `session_id`를 DB에 보관, 프로세스가 죽으면 `--resume` |
| S1-05 프롬프트 | 개인정보·환경 정보 언급 금지 규칙, 이모지 금지 규칙 반영 확인 |
| S1-06 MCP | 공식 Python SDK 2.x는 `FastMCP`가 `MCPServer`(`mcp.server.mcpserver`)로 바뀌었다 |
| 운영 | CLI 자동 업데이트 끄기(`DISABLE_AUTOUPDATER=1`), 버전 2.1.296 기준. 업데이트 시 녹화 샘플로 파서 테스트 재확인 |
