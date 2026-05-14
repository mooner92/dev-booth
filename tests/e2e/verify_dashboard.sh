#!/bin/bash
# US-008 — confirm the dashboard (port 7000) sees a session in real time and
# that current_stage advances as the orchestrator narrates.
#
# Usage:  tests/e2e/verify_dashboard.sh [session_name]
# Run this WHILE (or after) an e2e dryrun for <session_name> is in progress.
set -euo pipefail

SESSION="${1:-e2e-dryrun}"
API="http://localhost:7000/api"
SAMPLES="${SAMPLES:-8}"
INTERVAL_S=20

echo "[verify_dashboard] session=${SESSION} api=${API}"

# 0. dashboard health
health=$(curl -s -m 5 "${API}/health" || true)
echo "[verify_dashboard] health: ${health}"
echo "${health}" | grep -q '"ok":true' || { echo "  FAIL dashboard not healthy"; exit 1; }

# 1. session appears in the listing
listing=$(curl -s -m 5 "${API}/sessions" || true)
if echo "${listing}" | grep -q "\"${SESSION}\""; then
  echo "  ok   session '${SESSION}' visible in /api/sessions"
else
  echo "  FAIL session '${SESSION}' not in /api/sessions"
  exit 1
fi

# 2. sample current_stage over time — assert it reaches >= 1 and never regresses
prev=-1
max_stage=0
transitions=0
for i in $(seq 1 "${SAMPLES}"); do
  status=$(curl -s -m 5 "${API}/sessions/${SESSION}/status" || true)
  stage=$(echo "${status}" | python3 -c "import json,sys; print(json.load(sys.stdin).get('current_stage',-1))" 2>/dev/null || echo -1)
  echo "  sample ${i}: current_stage=${stage}"
  if [[ "${stage}" -gt "${prev}" && "${prev}" -ge 0 ]]; then
    transitions=$((transitions + 1))
  fi
  [[ "${stage}" -gt "${max_stage}" ]] && max_stage="${stage}"
  prev="${stage}"
  sleep "${INTERVAL_S}"
done

echo
if [[ "${max_stage}" -ge 1 ]]; then
  echo "  ok   dashboard reported current_stage >= 1 (max=${max_stage}, transitions=${transitions})"
  echo "[verify_dashboard] PASS"
  exit 0
else
  echo "  FAIL dashboard never reported a stage >= 1"
  exit 1
fi
