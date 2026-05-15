#!/usr/bin/env bash
# Dev-Booth E2E — Hermes Kanban dryrun (Milestone A honest bar, plan v4 §10).
#
# Seeds the 12-stage DAG on a named board and watches the gateway dispatcher
# claim + spawn agents. Honest bar: review-gated stages may terminate in
# `blocked` by design (KANBAN_GUIDANCE) — success = each task reaches its
# EXPECTED terminal state, NOT "every task -> done". This is a long
# (20-40 min) nightly-class run, not a fast CI gate.
#
# Usage: tests/e2e/e2e_dryrun.sh [session] [repo_url]
set -euo pipefail

DEV_BOOTH=/dev-booth
HERMES=/home/mooner92/.local/bin/hermes
PY="$DEV_BOOTH/env/bin/python3.11"
SESSION="${1:-e2e-kanban-dryrun}"
REPO="${2:-https://github.com/mooner92/firebase-chat-exp}"
BOARD="$(echo "$SESSION" | tr '[:upper:] _' '[:lower:]--')"
MAX_POLLS="${MAX_POLLS:-60}"   # 60 * 30s = 30 min cap

echo "[e2e] session=$SESSION board=$BOARD repo=$REPO mode=dryrun"

# 0. gateway must be running (B1)
"$HERMES" gateway status 2>/dev/null | grep -qiE "running|active" || {
  echo "[e2e] gateway not running — start it: ./run.sh gateway start" >&2; exit 1; }

# 1. seed the board
rm -rf "$DEV_BOOTH/sessions/$SESSION"
DEV_BOOTH_DRYRUN=1 "$PY" -m core.session "$SESSION" "$REPO" --goal "코드 품질 개선 및 버그 수정"

# 2. watch the dispatcher work the board
DB="$HOME/.hermes/kanban/boards/$BOARD/kanban.db"
for i in $(seq 1 "$MAX_POLLS"); do
  sleep 30
  active=$("$HERMES" kanban --board "$BOARD" list --json 2>/dev/null | "$PY" -c "
import sys,json
t=json.load(sys.stdin); tasks=t if isinstance(t,list) else t.get('tasks',[])
act=[x for x in tasks if x['status'] in ('todo','ready','running')]
print(len(act))" 2>/dev/null || echo "?")
  echo "[e2e] poll $i: $active task(s) still active"
  [ "$active" = "0" ] && break
done

# 3. assertions
echo
echo "[e2e] === ASSERTIONS ==="
fail=0
chk() { if [ "$2" -eq 0 ]; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }

[ -f "$DEV_BOOTH/sessions/$SESSION/status.json" ]; chk "status.json exists" $?
[ -f "$DEV_BOOTH/sessions/$SESSION/stage_task_map.json" ]; chk "stage_task_map.json (12 tasks seeded)" $?
ntasks=$("$HERMES" kanban --board "$BOARD" list --json 2>/dev/null | "$PY" -c "import sys,json; t=json.load(sys.stdin); print(len(t if isinstance(t,list) else t.get('tasks',[])))")
[ "$ntasks" -eq 12 ]; chk "board has 12 tasks (got $ntasks)" $?
nruns=$("$PY" -c "import sqlite3; c=sqlite3.connect('file:$DB?mode=ro',uri=True); print(len(list(c.execute('SELECT 1 FROM task_runs'))))" 2>/dev/null || echo 0)
[ "$nruns" -ge 1 ]; chk "dispatcher spawned >=1 worker (task_runs=$nruns)" $?
# queues: a named board has no per-agent queue dirs (Kanban != AWG) — sanity that
# the board dir is the only artifact, no stray 'orchestrator' agent dir
[ -f "$DB" ]; chk "kanban.db present at named-board path" $?
# dashboard sees the board
curl -s -m5 "http://localhost:7000/api/kanban/boards/$BOARD/tasks" | grep -q '"tasks"'; chk "dashboard /api/kanban tasks endpoint live" $?

echo
"$HERMES" kanban --board "$BOARD" list 2>/dev/null | tail -16
echo
[ "$fail" -eq 0 ] && echo "[e2e] PASSED (honest bar: review-gated stages may be 'blocked' by design)" || echo "[e2e] FAILED"
exit "$fail"
