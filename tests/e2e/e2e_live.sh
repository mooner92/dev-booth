#!/usr/bin/env bash
# Dev-Booth E2E — LIVE run (operator-gated, plan v4 OT2).
#
# LIVE mode does REAL git push + REAL gh pr create against CrownClownCrowd /
# mooner92. It is gated behind an explicit acknowledgement flag and is NOT run
# by the automated suite. The dryrun gate (token scrub + pre-push hook + PATH
# wrappers) is DISABLED in live mode by design.
#
# Usage: tests/e2e/e2e_live.sh --i-understand-this-is-live [session] [repo_url]
set -euo pipefail

if [[ "${1:-}" != "--i-understand-this-is-live" ]]; then
  cat <<'EOF'
[e2e_live] REFUSING TO RUN — live mode is operator-gated.

Live mode performs REAL git push + REAL gh pr create. Re-run with the explicit
acknowledgement flag, supervised by a human operator:

  tests/e2e/e2e_live.sh --i-understand-this-is-live [session] [repo_url]

To abort a live run:  ./run.sh stop <session>  (archives the board's tasks)
EOF
  exit 2
fi

SESSION="${2:-e2e-kanban-live}"
REPO="${3:-https://github.com/mooner92/firebase-chat-exp}"

echo "[e2e_live] OPERATOR-SUPERVISED LIVE RUN — session=$SESSION repo=$REPO"
echo "[e2e_live] real git push + gh pr create WILL happen."
sleep 3
exec /dev-booth/run.sh start "$SESSION" "$REPO" "코드 품질 개선 및 버그 수정" live
