#!/usr/bin/env bash
set -Eeuo pipefail
set +x

: "${QSTASH_TOKEN:?QSTASH_TOKEN is required}"
: "${OMEGA_PULSE_URL:?OMEGA_PULSE_URL is required}"
: "${OMEGA_CONTROL_KEY:?OMEGA_CONTROL_KEY is required}"

QSTASH_URL="${QSTASH_URL:-https://qstash.upstash.io}"
SCHEDULE_ID="${OMEGA_QSTASH_SCHEDULE_ID:-omega-generation-pulse-v1}"
CRON="${OMEGA_QSTASH_CRON:-*/10 * * * *}"
RETRIES="${OMEGA_QSTASH_RETRIES:-3}"

[[ "$RETRIES" =~ ^[0-9]+$ ]] || { echo "OMEGA_QSTASH_RETRIES_INVALID" >&2; exit 64; }
[ "$RETRIES" -le 3 ] || { echo "OMEGA_QSTASH_RETRIES_EXCEEDS_ZERO_COST_BUDGET" >&2; exit 64; }

destination="$(
  python3 - "$OMEGA_PULSE_URL" <<'PY'
import sys, urllib.parse
url=sys.argv[1]
if not url.startswith("https://"):
    raise SystemExit("OMEGA_QSTASH_DESTINATION_MUST_BE_HTTPS")
print(urllib.parse.quote(url, safe=""))
PY
)"

tmp="$(mktemp)"
cleanup(){ rm -f "$tmp"; }
trap cleanup EXIT

curl --fail-with-body --silent --show-error   --request POST   --url "$QSTASH_URL/v2/schedules/$destination"   --header "Authorization: Bearer $QSTASH_TOKEN"   --header "Upstash-Cron: $CRON"   --header "Upstash-Schedule-Id: $SCHEDULE_ID"   --header "Upstash-Method: POST"   --header "Upstash-Timeout: 10s"   --header "Upstash-Retries: $RETRIES"   --header "Upstash-Forward-Authorization: Bearer $OMEGA_CONTROL_KEY"   --header "Upstash-Label: omega-generation-pulse"   --header "Content-Type: application/json"   --data '{"source":"qstash","authority":"wake_reconcile_only"}'   > "$tmp"

python3 - "$tmp" "$SCHEDULE_ID" <<'PY'
import json,sys
payload=json.load(open(sys.argv[1],encoding="utf-8"))
actual=str(payload.get("scheduleId") or "")
expected=sys.argv[2]
if actual != expected:
    raise SystemExit(f"OMEGA_QSTASH_SCHEDULE_ID_MISMATCH:{actual}!={expected}")
print(f"OMEGA_QSTASH_SCHEDULE_READY id={actual}")
PY
