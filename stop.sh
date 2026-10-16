#!/usr/bin/env bash
# TrailTalk 종료: ./run.sh(일반·--fake·--phone)가 띄운 서버(8000)·웹(5173)과 폰 모드의 Tailscale Serve를 끈다.
# 다른 터미널에서 띄웠거나 창을 닫아 남은 것을 정리할 때 쓴다.
#
#   ./stop.sh
#
# 이 저장소의 server/·web/ 폴더에서 실행 중인 프로세스만 끈다(같은 포트의 다른 프로젝트는 알리기만 한다).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd -P)" # lsof가 주는 실제 경로와 비교하므로 심볼릭 링크를 푼다
API_PORT="${API_PORT:-8000}"             # run.sh와 같은 기본값(시험할 때만 바꾼다)
WEB_PORT="${WEB_PORT:-5173}"

case "${1:-}" in
  -h | --help)
    sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "") ;;
  *)
    echo "알 수 없는 옵션: $1 (--help 참고)" >&2
    exit 2
    ;;
esac

DID=0 # 무엇이든 끈 것이 있는가

listeners() { lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }
command_of() { ps -o command= -p "$1" 2>/dev/null || true; }
parent_of() { ps -o ppid= -p "$1" 2>/dev/null | tr -d ' ' || true; }
cwd_of() { lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' || true; }

# run.sh는 서버를 server/에서, 웹을 web/에서 띄운다(작업 폴더로 이 저장소의 것인지 가린다)
is_ours() { [ "$(cwd_of "$1")" = "$ROOT/$2" ]; }
# 포트에서 듣고 있는 이 저장소의 프로세스
our_listeners() {
  local pid
  for pid in $(listeners "$1"); do
    if is_ours "$pid" "$2"; then echo "$pid"; fi
  done
}

# 1. 폰 모드의 HTTPS(Tailscale Serve). 443의 /가 이 서버(127.0.0.1:API_PORT)를 가리키고, 그 포트를
#    다른 프로젝트가 쓰고 있지 않을 때만 443 설정을 닫는다(run.sh --phone이 연 것과 같은 모양)
serve_is_ours() {
  command -v tailscale >/dev/null && command -v python3 >/dev/null || return 1
  tailscale serve status --json 2>/dev/null | python3 -c '
import json, sys
port = sys.argv[1]
try:
    web = json.load(sys.stdin).get("Web") or {}
except ValueError:
    sys.exit(1)
targets = [
    (h.get("Handlers") or {}).get("/", {}).get("Proxy")
    for host, h in web.items() if host.endswith(":443")
]
sys.exit(0 if f"http://127.0.0.1:{port}" in targets else 1)' "$API_PORT"
}
if serve_is_ours; then
  others=0
  for pid in $(listeners "$API_PORT"); do is_ours "$pid" server || others=1; done
  if [ "$others" = 1 ]; then
    echo "Tailscale Serve가 포트 $API_PORT 을(를) 가리키지만 다른 프로그램이 쓰고 있어 닫지 않았습니다." >&2
  elif tailscale serve --https=443 off >/dev/null 2>&1; then
    echo "Tailscale Serve(HTTPS)를 닫았습니다."
    DID=1
  else
    echo "Tailscale Serve를 닫지 못했습니다. 직접 실행하세요: tailscale serve --https=443 off" >&2
  fi
fi

# 2. 이 저장소의 run.sh. 종료 신호를 받으면 스스로 서버·웹·Serve를 정리한다(trap)
run_sh_pids=()
for pid in $(pgrep -f 'run\.sh' 2>/dev/null || true); do
  [ "$pid" = "$$" ] && continue
  cmd="$(command_of "$pid")"
  case "$cmd" in
    *bash*run.sh*) ;; # bash로 실행 중인 것만(run.sh를 연 편집기 등은 건드리지 않는다)
    *) continue ;;
  esac
  # 명령줄의 스크립트 경로(상대 경로면 그 프로세스의 작업 폴더 기준)가 이 저장소의 run.sh인가
  script=""
  for word in $cmd; do
    case "$word" in *run.sh) script="$word"; break ;; esac
  done
  case "$script" in
    /*) ;;
    *) script="$(cwd_of "$pid")/$script" ;;
  esac
  dir="$(cd "$(dirname "$script")" 2>/dev/null && pwd -P)" || continue
  [ "$dir/run.sh" = "$ROOT/run.sh" ] || continue
  if kill -TERM "$pid" 2>/dev/null; then
    echo "run.sh(pid $pid)에 종료를 알렸습니다."
    run_sh_pids+=("$pid")
    DID=1
  fi
done
# run.sh가 스스로 정리할 시간을 준다(최대 5초)
for _ in $(seq 1 10); do
  alive=0
  for pid in ${run_sh_pids[@]+"${run_sh_pids[@]}"}; do kill -0 "$pid" 2>/dev/null && alive=1; done
  [ "$alive" = 0 ] && break
  sleep 0.5
done

# 3. 남은 서버·웹(run.sh 없이 남은 것)
stop_port() {
  local port=$1 dir=$2 name=$3 pid parent
  for pid in $(listeners "$port"); do
    if ! is_ours "$pid" "$dir"; then
      echo "포트 $port 은(는) 다른 프로그램이 쓰고 있어 끄지 않았습니다: $(command_of "$pid")" >&2
      continue
    fi
    parent="$(parent_of "$pid")"
    kill -TERM "$pid" 2>/dev/null || true
    # 폰 모드는 서버를 caffeinate로 감싼다(uv 아래에 있어도 위로 올라가며 찾는다)
    while [ -n "$parent" ] && [ "$parent" != "1" ]; do
      case "$(command_of "$parent")" in
        caffeinate*) kill -TERM "$parent" 2>/dev/null || true; break ;;
        *uv\ run* | *uvicorn*) parent="$(parent_of "$parent")" ;;
        *) break ;;
      esac
    done
    echo "끄는 중: $name(포트 $port, pid $pid)"
    DID=1
  done
}
stop_port "$API_PORT" server "서버"
stop_port "$WEB_PORT" web "웹"

# 4. 이 저장소의 프로세스가 포트에서 사라질 때까지 최대 10초 기다리고, 남으면 강제로 끝낸다
for spec in "$API_PORT:server" "$WEB_PORT:web"; do
  port="${spec%%:*}" dir="${spec#*:}"
  for _ in $(seq 1 20); do
    [ -z "$(our_listeners "$port" "$dir")" ] && break
    sleep 0.5
  done
  for pid in $(our_listeners "$port" "$dir"); do
    kill -KILL "$pid" 2>/dev/null || true
    echo "포트 $port 의 프로세스(pid $pid)가 끝나지 않아 강제로 끝냈습니다." >&2
  done
done

if [ "$DID" = 0 ]; then
  echo "실행 중인 TrailTalk가 없습니다."
else
  echo "TrailTalk를 껐습니다."
fi
