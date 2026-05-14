#!/bin/bash
# Dev-Booth multi-agent runtime — operator entry point (plan v3 Phase 5).
#
#   ./run.sh start  <session> <repo_url> [goal] [mode]   mode: dryrun (default) | live
#   ./run.sh stop   <session>
#   ./run.sh status <session>
#   ./run.sh logs   <session>
#   ./run.sh help
#
# `start` activates the venv and launches `python -m core.orchestrator`,
# recording the PID to <session>/orchestrator.pid. `stop` terminates the
# orchestrator and verifies no orphaned hermes subprocess remains.
set -euo pipefail

DEV_BOOTH_ROOT="/dev-booth"
VENV_ACTIVATE="${DEV_BOOTH_ROOT}/env/bin/activate"
SESSIONS_ROOT="${DEV_BOOTH_ROOT}/sessions"

COMMAND="${1:-help}"
SESSION="${2:-}"
REPO="${3:-}"
GOAL="${4:-코드 품질 개선 및 버그 수정}"
MODE="${5:-dryrun}"

usage() {
  cat <<'EOF'
Dev-Booth multi-agent runtime

  ./run.sh start  <session> <repo_url> [goal] [mode]
       mode: dryrun (default) — no real git push / gh pr create
             live            — real push + PR (operator-supervised)
  ./run.sh stop   <session>   graceful SIGINT, then verify no orphans
  ./run.sh status <session>   print <session>/status.json
  ./run.sh logs   <session>   tail -f <session>/log/messages.jsonl
  ./run.sh help

Examples:
  ./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정"
  ./run.sh start demo https://github.com/mooner92/firebase-chat-exp "버그 수정" live
  ./run.sh status demo
  ./run.sh logs demo
EOF
}

require_session() {
  if [[ -z "${SESSION}" ]]; then
    echo "error: <session> is required" >&2
    usage
    exit 2
  fi
}

cmd_start() {
  require_session
  if [[ -z "${REPO}" ]]; then
    echo "error: <repo_url> is required for 'start'" >&2
    exit 2
  fi
  local session_dir="${SESSIONS_ROOT}/${SESSION}"
  local pid_file="${session_dir}/orchestrator.pid"
  mkdir -p "${session_dir}"

  if [[ -f "${pid_file}" ]] && kill -0 "$(cat "${pid_file}")" 2>/dev/null; then
    echo "error: session '${SESSION}' already running (pid $(cat "${pid_file}"))" >&2
    exit 1
  fi

  # shellcheck disable=SC1090
  source "${VENV_ACTIVATE}"
  echo "[start] session=${SESSION} repo=${REPO} mode=${MODE}"
  cd "${DEV_BOOTH_ROOT}"
  nohup python -m core.orchestrator "${SESSION}" "${REPO}" \
    --goal "${GOAL}" --mode "${MODE}" \
    >"${session_dir}/orchestrator.out" 2>&1 &
  local pid=$!
  echo "${pid}" >"${pid_file}"
  echo "[start] orchestrator pid=${pid} (log: ${session_dir}/orchestrator.out)"
}

cmd_stop() {
  require_session
  local session_dir="${SESSIONS_ROOT}/${SESSION}"
  local pid_file="${session_dir}/orchestrator.pid"

  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}")"
    if kill -0 "${pid}" 2>/dev/null; then
      echo "[stop] sending SIGINT to orchestrator pid=${pid}"
      kill -INT "${pid}" 2>/dev/null || true
      for _ in $(seq 1 20); do
        kill -0 "${pid}" 2>/dev/null || break
        sleep 0.5
      done
      if kill -0 "${pid}" 2>/dev/null; then
        echo "[stop] still alive — sending SIGTERM"
        kill -TERM "${pid}" 2>/dev/null || true
        sleep 1
      fi
    fi
    rm -f "${pid_file}"
  else
    echo "[stop] no pid file for session '${SESSION}'"
  fi

  # verify no orphaned orchestrator / hermes subprocess for this session
  local orphans=0
  if pgrep -f "core.orchestrator ${SESSION} " >/dev/null 2>&1; then
    echo "[stop] WARNING: orphaned orchestrator process still running" >&2
    orphans=1
  fi
  if pgrep -f "hermes -z" >/dev/null 2>&1; then
    echo "[stop] WARNING: orphaned hermes subprocess still running" >&2
    orphans=1
  fi
  if [[ "${orphans}" -eq 0 ]]; then
    echo "[stop] session '${SESSION}' stopped — no orphans"
  fi
}

cmd_status() {
  require_session
  local status_file="${SESSIONS_ROOT}/${SESSION}/status.json"
  if [[ -f "${status_file}" ]]; then
    cat "${status_file}"
  else
    echo "error: no status.json for session '${SESSION}'" >&2
    exit 1
  fi
}

cmd_logs() {
  require_session
  local log_file="${SESSIONS_ROOT}/${SESSION}/log/messages.jsonl"
  if [[ -f "${log_file}" ]]; then
    tail -f "${log_file}"
  else
    echo "error: no log/messages.jsonl for session '${SESSION}'" >&2
    exit 1
  fi
}

case "${COMMAND}" in
  start)  cmd_start ;;
  stop)   cmd_stop ;;
  status) cmd_status ;;
  logs)   cmd_logs ;;
  help|-h|--help) usage ;;
  *)
    echo "error: unknown command '${COMMAND}'" >&2
    usage
    exit 2
    ;;
esac
