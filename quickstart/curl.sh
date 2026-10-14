#!/usr/bin/env bash
# One part in, one price out — the same flow as main.py, in curl + jq.
#
#   export ARCNM_API_KEY="…"      # arcnm.io → Settings → API keys
#   export ARCNM_ENV_ID="…"       # arcnm.io → Environments
#   ./quickstart/curl.sh [path/to/part.step]
set -euo pipefail

API="${ARCNM_API_BASE:-https://api.arcnm.io/api/v1}"
CAD="${1:-$(dirname "$0")/../parts/shaft_thread.step}"

: "${ARCNM_API_KEY:?set ARCNM_API_KEY — arcnm.io → Settings → API keys}"
: "${ARCNM_ENV_ID:?set ARCNM_ENV_ID — arcnm.io → Environments}"
[ -f "$CAD" ] || { echo "no such file: $CAD" >&2; exit 1; }

echo "→ quoting $(basename "$CAD")"

# One multipart request creates the part, the revision and the dataset, then
# enqueues the calculation. 202 Accepted with an id you poll.
CALC=$(curl -sS -X POST "$API/calculations/upload-and-quote" \
  -H "X-API-Key: $ARCNM_API_KEY" \
  -F "costing_environment_id=$ARCNM_ENV_ID" \
  -F "part_number=$(basename "${CAD%.*}" | tr '[:lower:]' '[:upper:]')" \
  -F "cad_file=@$CAD;type=application/step" \
  -F "lot_size=50" \
  -F "annual_volume=500")

ID=$(jq -r '.id // empty' <<<"$CALC")
if [ -z "$ID" ]; then
  # Errors carry a stable error.code and a request_id to quote to support.
  # https://arcnm.io/docs/errors
  jq -r '"\(.error.code // "error"): \(.error.message // .)\nrequest_id: \(.request_id // "—")"' <<<"$CALC" >&2
  exit 1
fi
echo "  queued: $ID"

# Poll until terminal. Seconds for a typical milled part.
for _ in $(seq 1 300); do
  CALC=$(curl -sS "$API/calculations/$ID" -H "X-API-Key: $ARCNM_API_KEY")
  STATUS=$(jq -r '.status' <<<"$CALC")
  case "$STATUS" in
    # blocked: parked, the organization has no included calculations left.
    succeeded|failed|cancelled|timed_out|blocked) break ;;
  esac
  printf '  %s…\r' "$STATUS"
  sleep 2
done

printf '%*s\r' 40 ''
[ "$STATUS" = succeeded ] || {
  echo "calculation $STATUS $(jq -r '.coverage.message // empty' <<<"$CALC")" >&2
  exit 1
}

jq -r '"
\(.status)
  unit cost   \(.unit_cost) \(.currency)
  total       \(.total_cost) \(.currency)   (lot of 50)
  setup       \(.setup_cost) \(.currency)
  unit time   \(.unit_time_s) s
"' <<<"$CALC"

echo "The .analytics blob carries the audit trail:"
echo "https://arcnm.io/docs/concepts/audit-provenance"
