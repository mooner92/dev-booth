#!/bin/bash
# US-008 — End-to-end LIVE run (operator-supervised, O5).
#
# LIVE mode performs REAL side effects: git push to the CrownClownCrowd fork and
# `gh pr create` against the upstream repo. It is gated behind an explicit
# acknowledgement flag and is NOT run by the automated suite.
#
# Usage:
#   tests/e2e/e2e_live.sh --i-understand-this-is-live [session] [repo_url]
set -euo pipefail

DEV_BOOTH_ROOT="/dev-booth"
GATE="${1:-}"

if [[ "${GATE}" != "--i-understand-this-is-live" ]]; then
  cat <<'EOF'
[e2e_live] REFUSING TO RUN — live mode is operator-gated.

Live mode does REAL git push + REAL gh pr create. Re-run with the explicit
acknowledgement flag, supervised by a human operator:

  tests/e2e/e2e_live.sh --i-understand-this-is-live [session] [repo_url]

Abort signal during a live run:  ./run.sh stop <session>
EOF
  exit 2
fi

SESSION="${2:-e2e-live}"
REPO="${3:-https://github.com/mooner92/firebase-chat-exp}"
GOAL="코드 품질 개선 및 버그 수정"

echo "[e2e_live] OPERATOR-SUPERVISED LIVE RUN — session=${SESSION} repo=${REPO}"
echo "[e2e_live] real git push + gh pr create WILL happen. Ctrl-C or"
echo "[e2e_live] './run.sh stop ${SESSION}' to abort."
sleep 3

"${DEV_BOOTH_ROOT}/run.sh" start "${SESSION}" "${REPO}" "${GOAL}" live
echo "[e2e_live] started in live mode — monitor with:  ./run.sh logs ${SESSION}"
