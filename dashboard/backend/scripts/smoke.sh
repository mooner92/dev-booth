#!/usr/bin/env bash
# Hits every REST endpoint and exits non-zero on the first failure.
set -euo pipefail

HOST="${HOST:-http://127.0.0.1:7001}"
SESSION="${SESSION:-test-awg}"

check() {
  local label="$1"; shift
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' "$@") || code="000"
  if [[ "$code" =~ ^2 ]] || [[ "$2" == "EXPECT_NOT_200" && "$code" =~ ^4 ]]; then
    echo "  ok  $label -> $code"
  else
    echo "  FAIL $label -> $code"
    exit 1
  fi
}

echo "[smoke] base = $HOST, session = $SESSION"
check "GET /api/health"                   "$HOST/api/health"
check "GET /api/sessions"                 "$HOST/api/sessions"
check "GET /api/sessions/$SESSION"        "$HOST/api/sessions/$SESSION"
check "GET /api/sessions/$SESSION/status" "$HOST/api/sessions/$SESSION/status"
check "GET /api/sessions/$SESSION/files"  "$HOST/api/sessions/$SESSION/files"
check "GET /api/sessions/$SESSION/logs"   "$HOST/api/sessions/$SESSION/logs?limit=10"
check "GET /api/sessions/$SESSION/queues" "$HOST/api/sessions/$SESSION/queues"
check "GET /api/sessions/$SESSION/file?path=log/messages.jsonl" \
      "$HOST/api/sessions/$SESSION/file?path=log/messages.jsonl"
check "GET /api/metrics/preset/gpu_utilization" \
      "$HOST/api/metrics/preset/gpu_utilization"
check "GET /api/metrics/internal"         "$HOST/api/metrics/internal"

# Path traversal must return 4xx, not 2xx
echo "[smoke] expect 4xx on path traversal..."
status=$(curl -s -o /dev/null -w '%{http_code}' "$HOST/api/sessions/$SESSION/file?path=../../../etc/passwd")
if [[ "$status" =~ ^4 ]]; then
  echo "  ok  traversal blocked -> $status"
else
  echo "  FAIL traversal -> $status"
  exit 1
fi

echo "[smoke] all OK"
