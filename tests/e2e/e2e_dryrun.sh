#!/bin/bash
# US-008 — End-to-end DRYRUN against the test repo (plan §5 honest bar).
#
# Honest bar: stages 1-8 do real subprocess work; stages 9-12 in dryrun are
# narration + pr_draft.json simulation only. No real git push, no real PR.
#
# Usage:  tests/e2e/e2e_dryrun.sh [session_name] [repo_url]
set -euo pipefail

DEV_BOOTH_ROOT="/dev-booth"
SESSION="${1:-e2e-dryrun}"
REPO="${2:-https://github.com/mooner92/firebase-chat-exp}"
GOAL="코드 품질 개선 및 버그 수정"
SESSION_DIR="${DEV_BOOTH_ROOT}/sessions/${SESSION}"
# whole-session cap is 5400s in core/config.py; allow a little headroom.
MAX_WAIT_S="${MAX_WAIT_S:-6000}"
POLL_S=15

echo "[e2e_dryrun] session=${SESSION} repo=${REPO} mode=dryrun"

# fresh session dir so the run starts clean
rm -rf "${SESSION_DIR}"

"${DEV_BOOTH_ROOT}/run.sh" start "${SESSION}" "${REPO}" "${GOAL}" dryrun

# poll status.json until a terminal state or timeout
waited=0
state="(none)"
while [[ "${waited}" -lt "${MAX_WAIT_S}" ]]; do
  sleep "${POLL_S}"
  waited=$((waited + POLL_S))
  if [[ -f "${SESSION_DIR}/status.json" ]]; then
    state=$(python3 -c "import json,sys; print(json.load(open('${SESSION_DIR}/status.json')).get('status','?'))" 2>/dev/null || echo "?")
    step=$(python3 -c "import json,sys; print(json.load(open('${SESSION_DIR}/status.json')).get('current_step','?'))" 2>/dev/null || echo "?")
    echo "[e2e_dryrun] t=${waited}s state=${state} step=${step}"
    case "${state}" in
      completed|error|aborted) break ;;
    esac
  else
    echo "[e2e_dryrun] t=${waited}s waiting for status.json..."
  fi
done

echo
echo "[e2e_dryrun] === ASSERTIONS ==="
fail=0
assert() {  # assert <label> <condition-exit-code>
  if [[ "$2" -eq 0 ]]; then echo "  ok   $1"; else echo "  FAIL $1"; fail=1; fi
}

# 1. messages.jsonl exists and is non-empty
[[ -s "${SESSION_DIR}/log/messages.jsonl" ]]; assert "log/messages.jsonl exists and non-empty" $?

# 2. status.json exists
[[ -f "${SESSION_DIR}/status.json" ]]; assert "status.json exists" $?

# 3. terminal state reached (completed strongly preferred)
[[ "${state}" == "completed" ]]; assert "status == completed (state=${state})" $?

# 4. pr_draft.json url == DRYRUN://no-pr
if [[ -f "${SESSION_DIR}/pr_draft.json" ]]; then
  url=$(python3 -c "import json; print(json.load(open('${SESSION_DIR}/pr_draft.json')).get('url',''))")
  [[ "${url}" == "DRYRUN://no-pr" ]]; assert "pr_draft.json url == DRYRUN://no-pr (got ${url})" $?
else
  assert "pr_draft.json exists" 1
fi

# 5. queues/ contains exactly openclaw, hermes-a, hermes-b — no orchestrator/
qdirs=$(cd "${SESSION_DIR}/queues" && ls -d */ 2>/dev/null | tr -d '/' | sort | tr '\n' ',' || true)
[[ "${qdirs}" == "hermes-a,hermes-b,openclaw," ]]; assert "queues/ == {openclaw,hermes-a,hermes-b} (got ${qdirs})" $?
[[ ! -d "${SESSION_DIR}/queues/orchestrator" ]]; assert "no queues/orchestrator/ phantom agent" $?

# 6. no strands left in any processing/
strands=$(find "${SESSION_DIR}/queues" -path "*/processing/*.json" 2>/dev/null | wc -l)
[[ "${strands}" -eq 0 ]]; assert "all processing/ queues empty (${strands} strands)" $?

# 7. at least one orchestrator narration line in the log
narration=$(grep -c '"from":"orchestrator"' "${SESSION_DIR}/log/messages.jsonl" 2>/dev/null || echo 0)
[[ "${narration}" -ge 1 ]]; assert "orchestrator narration present (${narration} lines)" $?

echo
if [[ "${fail}" -eq 0 ]]; then
  echo "[e2e_dryrun] ALL ASSERTIONS PASSED"
  exit 0
else
  echo "[e2e_dryrun] FAILED"
  exit 1
fi
