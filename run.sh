#!/bin/bash
# Dev-Booth — Hermes Kanban 기반 자율 개발 시스템 (operator entry point).
#
# v2 architecture: this script seeds a Kanban board; the always-running
# `hermes gateway` dispatcher claims tasks and spawns the agent profiles.
# It does NOT run agents directly.
#
# NOTE (Phase 0 verified): the `--board <slug>` flag is a `hermes kanban`-LEVEL
# flag and must come BEFORE the subcommand.
set -euo pipefail

HERMES="/home/mooner92/.local/bin/hermes"
DEV_BOOTH_PATH="/dev-booth"
VENV="$DEV_BOOTH_PATH/env"
DRYRUN_BIN="$DEV_BOOTH_PATH/core/dryrun"

usage() {
  cat <<'EOF'
Dev-Booth — Hermes Kanban 기반 자율 개발 시스템

사용법:
  ./run.sh start  <세션명> <레포URL> [목표] [dryrun|live]   # 새 세션 시작 (보드 seed)
  ./run.sh stop   <세션명>                                  # 세션 중단 (게이트웨이는 유지)
  ./run.sh status <세션명>                                  # 세션 status.json
  ./run.sh board  <세션명>                                  # Kanban 태스크 목록
  ./run.sh watch  <세션명>                                  # Kanban 이벤트 실시간
  ./run.sh logs   <세션명>                                  # 세션 로그
  ./run.sh list                                             # 보드 + 세션 목록
  ./run.sh gateway [start|stop|status]                      # 게이트웨이 (B1 foreground)
  ./run.sh help

예시:
  ./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정"
  ./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정" live
  ./run.sh board demo
  ./run.sh watch demo
EOF
}

# --- gateway (B1: hermes gateway run, foreground process, detached) ---------
gateway_running() {
  $HERMES gateway status 2>/dev/null | grep -qiE "running|active"
}

gateway_start() {
  if gateway_running; then echo "[gateway] already running"; return 0; fi
  local mode="${1:-dryrun}"
  echo "[gateway] starting (B1, mode=$mode)..."
  mkdir -p "$DEV_BOOTH_PATH/sessions"
  if [[ "$mode" == "live" ]]; then
    # live: keep the token in env so real fork/push/PR can happen
    PATH="$DRYRUN_BIN:$PATH" DEV_BOOTH_DRYRUN=0 \
      setsid "$HERMES" gateway run >"$DEV_BOOTH_PATH/sessions/gateway.out" 2>&1 </dev/null &
  else
    # dryrun: scrub GITHUB_TOKEN/GH_TOKEN so workers have no push credential
    env -u GITHUB_TOKEN -u GH_TOKEN DEV_BOOTH_DRYRUN=1 PATH="$DRYRUN_BIN:$PATH" \
      setsid "$HERMES" gateway run >"$DEV_BOOTH_PATH/sessions/gateway.out" 2>&1 </dev/null &
  fi
  disown
  sleep 6
  gateway_running && echo "[gateway] running" || { echo "[gateway] FAILED — see sessions/gateway.out" >&2; return 1; }
}

cmd_gateway() {
  case "${1:-status}" in
    start)  gateway_start "${2:-dryrun}" ;;
    stop)   pkill -f "hermes gateway run" 2>/dev/null && echo "[gateway] stopped" || echo "[gateway] not running" ;;
    status) $HERMES gateway status ;;
    *)      $HERMES gateway status ;;
  esac
}

# --- session lifecycle ------------------------------------------------------
cmd_start() {
  local SESSION="${1:?세션명 필요}"
  local REPO="${2:?레포 URL 필요}"
  local GOAL="${3:-코드 품질 개선 및 버그 수정}"
  local MODE="${4:-dryrun}"

  if [[ "$MODE" == "live" ]]; then
    echo "⚠️  LIVE 모드: 실제 git push / gh pr create 가 실행됩니다."
    read -r -p "계속하려면 'yes' 입력: " confirm
    [[ "$confirm" == "yes" ]] || { echo "취소됨"; exit 0; }
  fi

  gateway_start "$MODE"

  cd "$DEV_BOOTH_PATH"
  # seed runs in-process; DEV_BOOTH_DRYRUN governs the agents (via gateway env)
  DEV_BOOTH_DRYRUN=$([[ "$MODE" == "live" ]] && echo 0 || echo 1) \
    "$VENV/bin/python3.11" -m core.session "$SESSION" "$REPO" --goal "$GOAL"
}

cmd_stop() {
  local SESSION="${1:?세션명 필요}"
  # archive the session's tasks so the dispatcher stops claiming them
  $HERMES kanban --board "$SESSION" list --json 2>/dev/null \
    | "$VENV/bin/python3.11" -c "import sys,json,subprocess
try: tasks=json.load(sys.stdin)
except Exception: tasks=[]
for t in (tasks if isinstance(tasks,list) else tasks.get('tasks',[])):
    subprocess.run(['$HERMES','kanban','--board','$SESSION','archive',t['id']],capture_output=True)
print(f'archived {len(tasks)} task(s) on board $SESSION')" 2>/dev/null || echo "[stop] no board $SESSION"
}

cmd_status() {
  local SESSION="${1:?세션명 필요}"
  local f="$DEV_BOOTH_PATH/sessions/$SESSION/status.json"
  [[ -f "$f" ]] && cat "$f" || { echo "세션 없음: $SESSION" >&2; exit 1; }
}

cmd_board() {
  local SESSION="${1:?세션명 필요}"
  $HERMES kanban --board "$SESSION" list
}

cmd_watch() {
  local SESSION="${1:?세션명 필요}"
  $HERMES kanban --board "$SESSION" watch
}

cmd_logs() {
  local SESSION="${1:?세션명 필요}"
  local f="$DEV_BOOTH_PATH/sessions/$SESSION/log/messages.jsonl"
  [[ -f "$f" ]] && tail -f "$f" || echo "로그 없음: $SESSION" >&2
}

cmd_list() {
  echo "=== Kanban boards ==="
  $HERMES kanban boards list
  echo
  echo "=== sessions ==="
  ls "$DEV_BOOTH_PATH/sessions/" 2>/dev/null | grep -v '\.out$' || echo "(세션 없음)"
}

case "${1:-help}" in
  start)   shift; cmd_start "$@" ;;
  stop)    shift; cmd_stop "$@" ;;
  status)  shift; cmd_status "$@" ;;
  board)   shift; cmd_board "$@" ;;
  watch)   shift; cmd_watch "$@" ;;
  logs)    shift; cmd_logs "$@" ;;
  list)    cmd_list ;;
  gateway) shift; cmd_gateway "$@" ;;
  help|-h|--help) usage ;;
  *) echo "error: unknown command '${1}'" >&2; usage; exit 2 ;;
esac
