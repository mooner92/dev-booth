#!/usr/bin/env bash
# Dev-Booth E2E — confirm the dashboard surfaces the live Kanban board.
# Run while (or after) e2e_dryrun.sh has seeded a board.
# Usage: tests/e2e/verify_dashboard.sh [board_slug]
set -euo pipefail

API="http://localhost:7000/api"
BOARD="${1:-e2e-kanban-dryrun}"

echo "[verify] board=$BOARD api=$API"
fail=0
chk() { if [ "$2" -eq 0 ]; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi; }

curl -s -m5 "$API/health" | grep -q '"ok":true'; chk "dashboard healthy" $?
curl -s -m5 "$API/kanban/boards" | grep -q "\"$BOARD\""; chk "board listed in /api/kanban/boards" $?
curl -s -m5 "$API/kanban/boards/$BOARD/tasks" | grep -q '"tasks"'; chk "tasks endpoint returns JSON" $?
curl -s -m5 "$API/kanban/boards/$BOARD/stats" | grep -qE '"(todo|ready|running|done)"'; chk "stats endpoint returns status counts" $?

echo
echo "[verify] live board stats:"
curl -s -m5 "$API/kanban/boards/$BOARD/stats"
echo
[ "$fail" -eq 0 ] && echo "[verify] PASSED" || echo "[verify] FAILED"
exit "$fail"
