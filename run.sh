#!/usr/bin/env bash
# TrailTalk 앱 실행: 서버(FastAPI, 8000)와 웹(Vite, 5173)을 함께 띄우고 브라우저를 연다.
#
#   ./run.sh            실제 Claude CLI로 실행(구독 사용량 사용, DB는 server/trailtalk.db)
#   ./run.sh --fake     가짜 CLI(녹화 재생)로 실행. 사용량 없이 화면 확인용, 임시 DB(.run-fake/)
#   ./run.sh --no-open  브라우저를 열지 않는다
#   ./run.sh --phone    폰에서 쓰기: 웹을 빌드해 서버(8000)가 함께 서빙하고, Tailscale Serve로
#                       tailnet 안에만 HTTPS로 연다(docs/phone.md). Mac이 잠들지 않게 한다
#
# Ctrl+C로 둘 다 종료한다.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
API_PORT=8000
WEB_PORT=5173
FAKE=0
OPEN=1
PHONE=0

for arg in "$@"; do
  case "$arg" in
    --fake) FAKE=1 ;;
    --no-open) OPEN=0 ;;
    --phone) PHONE=1 ;;
    -h | --help)
      sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "알 수 없는 옵션: $arg (--help 참고)" >&2
      exit 2
      ;;
  esac
done

for cmd in uv npm curl; do
  command -v "$cmd" >/dev/null || { echo "$cmd 명령이 필요합니다." >&2; exit 1; }
done

# 폰 모드: Tailscale Serve(tailnet 안에서만, 공개 Funnel은 쓰지 않는다)의 HTTPS 주소를 먼저 확인한다
TS_HOST=""
if [ "$PHONE" = 1 ]; then
  command -v tailscale >/dev/null || {
    echo "tailscale 명령이 필요합니다. https://tailscale.com/download 에서 설치하고 로그인하세요." >&2
    exit 1
  }
  command -v python3 >/dev/null || { echo "python3 명령이 필요합니다(Tailscale 상태 읽기)." >&2; exit 1; }
  # "이름<탭>인증서도메인"(인증서를 켜지 않았으면 둘째 값이 비어 있다)
  IFS=$'\t' read -r TS_HOST TS_CERT < <(tailscale status --json | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d["Self"]["DNSName"].rstrip("."), (d.get("CertDomains") or [""])[0], sep="\t")') || true
  if [ -z "$TS_HOST" ]; then
    echo "Tailscale 상태를 읽지 못했습니다. Tailscale에 로그인돼 있는지 확인하세요(tailscale status)." >&2
    exit 1
  fi
  if [ -z "${TS_CERT:-}" ]; then
    echo "Tailscale HTTPS 인증서가 꺼져 있습니다. 관리 콘솔(https://login.tailscale.com/admin/dns)에서" >&2
    echo "MagicDNS와 HTTPS Certificates를 켠 뒤 다시 실행하세요(docs/phone.md)." >&2
    exit 1
  fi
fi

port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
PORTS=("$API_PORT")
[ "$PHONE" = 1 ] || PORTS+=("$WEB_PORT")  # 폰 모드는 Vite 없이 서버가 빌드본을 서빙한다
for port in "${PORTS[@]}"; do
  if port_in_use "$port"; then
    echo "포트 $port 이(가) 이미 사용 중입니다. 떠 있는 서버를 먼저 끄세요: lsof -nP -iTCP:$port -sTCP:LISTEN" >&2
    exit 1
  fi
done

# 의존성(처음 한 번)
(cd "$ROOT/server" && uv sync --quiet)
# node_modules가 없거나 package-lock.json이 마지막 설치보다 새로우면 다시 설치한다
if [ ! -f "$ROOT/web/node_modules/.package-lock.json" ] ||
  [ "$ROOT/web/package-lock.json" -nt "$ROOT/web/node_modules/.package-lock.json" ]; then
  (cd "$ROOT/web" && npm install)
fi

if [ "$FAKE" = 1 ]; then
  FAKE_DIR="$ROOT/.run-fake"
  rm -rf "$FAKE_DIR" && mkdir -p "$FAKE_DIR"
  export CLAUDE_CLI_PATH="$ROOT/server/tests/fakes/fake-claude"
  export FAKE_CLAUDE_FIXTURE="${FAKE_CLAUDE_FIXTURE:-web_search}"
  export FAKE_CLAUDE_ONESHOT="$ROOT/server/tests/fixtures/claude_cli/extract.jsonl"  # 일지 정리 결과
  export CLI_ENV_PASSTHROUGH='["FAKE_CLAUDE_*"]'
  export VOICE_BACKEND=fake  # 음성 인식·합성도 가짜(과금 없음, app/voice/fake.py)
  export DATABASE_URL="sqlite+aiosqlite:///$FAKE_DIR/fake.db"
  export CLI_WORK_DIR="$FAKE_DIR/cli"
  echo "가짜 CLI 모드(녹화 $FAKE_CLAUDE_FIXTURE): 답변은 녹화된 내용을 순서대로 재생합니다."
fi
export INTERNAL_BASE_URL="http://127.0.0.1:$API_PORT"
export VITE_API_TARGET="http://127.0.0.1:$API_PORT"  # 셸에 남은 다른 값(E2E 8100 등)을 쓰지 않게

PIDS=()
# bash 3.2(macOS)는 set -u에서 빈 배열을 "${PIDS[@]}"로 펼치면 오류가 나므로 ${PIDS[@]+...}로 쓴다
stop_all() {
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
SERVING=0
SERVE_PID=""
serve_off() {
  # 허용 링크를 기다리며 멈춘 serve 명령이 남아 있으면 끝낸다(백그라운드 작업은 Ctrl+C를 받지 않는다)
  if [ -n "$SERVE_PID" ]; then kill "$SERVE_PID" 2>/dev/null || true; fi
  # 폰 모드에서 연 HTTPS를 닫는다(서버가 꺼진 뒤에도 tailnet에 열린 채 남지 않게)
  if [ "$SERVING" = 1 ]; then tailscale serve --https=443 off >/dev/null 2>&1 || true; fi
}
on_exit() {
  trap - INT TERM HUP EXIT
  serve_off
  stop_all
}
on_signal() {
  trap - INT TERM HUP EXIT
  echo
  echo "종료하는 중…"
  serve_off
  stop_all
  exit 130
}
trap on_signal INT TERM HUP
trap on_exit EXIT

SERVER_CMD=(uv run uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" --timeout-graceful-shutdown 5)
if [ "$PHONE" = 1 ]; then
  # 서버가 빌드본(web/dist)을 함께 서빙한다. 산책하는 동안 Mac이 잠들지 않게 caffeinate로 감싼다
  # (덮개를 닫고 배터리로 쓰면 그래도 잠들 수 있다)
  BUILD_LOG="$(mktemp)"
  if ! (cd "$ROOT/web" && npm run build) >"$BUILD_LOG" 2>&1; then
    cat "$BUILD_LOG" >&2
    rm -f "$BUILD_LOG"
    echo "웹 빌드에 실패했습니다(cd web && npm run build)." >&2
    exit 1
  fi
  rm -f "$BUILD_LOG"
  export WEB_DIST_DIR="$ROOT/web/dist"
  if command -v caffeinate >/dev/null; then SERVER_CMD=(caffeinate -is "${SERVER_CMD[@]}"); fi
fi
(cd "$ROOT/server" && exec "${SERVER_CMD[@]}") &
PIDS+=($!)
if [ "$PHONE" = 0 ]; then
  (cd "$ROOT/web" && exec npm run dev -- --host 127.0.0.1 --port "$WEB_PORT" --strictPort) &
  PIDS+=($!)
fi

wait_for() {
  local url=$1 name=$2
  for _ in $(seq 1 120); do
    curl -sf "$url" >/dev/null 2>&1 && return 0
    for pid in ${PIDS[@]+"${PIDS[@]}"}; do
      kill -0 "$pid" 2>/dev/null || { echo "$name 이(가) 시작하지 못했습니다." >&2; exit 1; }
    done
    sleep 0.5
  done
  echo "$name 이(가) 60초 안에 응답하지 않습니다." >&2
  exit 1
}
wait_for "http://127.0.0.1:$API_PORT/api/health" "서버"
if [ "$PHONE" = 1 ]; then
  # tailnet 기기에만 열린다(/internal/*은 서버가 프록시를 거친 요청이라 403으로 막는다)
  SERVING=1
  # Serve가 tailnet에서 허용되지 않았으면 명령이 허용 링크를 출력하고 기다리므로 15초로 끊는다
  SERVE_LOG="$(mktemp)"
  tailscale serve --bg --https=443 "http://127.0.0.1:$API_PORT" >"$SERVE_LOG" 2>&1 &
  SERVE_PID=$!
  for _ in $(seq 1 30); do kill -0 "$SERVE_PID" 2>/dev/null || break; sleep 0.5; done
  if kill -0 "$SERVE_PID" 2>/dev/null || ! wait "$SERVE_PID"; then
    kill "$SERVE_PID" 2>/dev/null || true
    echo "Tailscale Serve를 켜지 못했습니다. 아래 안내(허용 링크)를 따른 뒤 다시 실행하세요:" >&2
    cat "$SERVE_LOG" >&2
    rm -f "$SERVE_LOG"
    exit 1
  fi
  SERVE_PID=""
  rm -f "$SERVE_LOG"
  URL="https://$TS_HOST/"
  echo
  echo "TrailTalk 폰 모드 실행 중: $URL"
  echo "  폰에서 Tailscale을 켜고 위 주소를 Chrome으로 여세요. 종료: Ctrl+C(HTTPS도 닫힘)"
else
  wait_for "http://127.0.0.1:$WEB_PORT" "웹"
  URL="http://127.0.0.1:$WEB_PORT"
  echo
  echo "TrailTalk 실행 중: $URL  (서버 http://127.0.0.1:$API_PORT, 종료: Ctrl+C)"
fi
# 브라우저 열기에 실패해도(다른 OS의 open 등) 서버는 계속 띄워 둔다
if [ "$OPEN" = 1 ] && command -v open >/dev/null; then open "$URL" || true; fi

# 서버나 웹 중 하나가 죽으면 나머지도 끈다(bash 3.2에는 wait -n이 없어 상태를 살핀다)
while :; do
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "서버 또는 웹이 종료되어 나머지도 끕니다." >&2
      exit 1
    fi
  done
  sleep 1
done
