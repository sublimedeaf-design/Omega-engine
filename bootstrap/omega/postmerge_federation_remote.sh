#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED="${OMEGA_EXPECTED_MAIN_SHA:?missing expected main sha}"
STATE="${OMEGA_STATE:-/workspaces/.omega-state}"
export OMEGA_STATE="$STATE"
mkdir -p "$STATE/logs" "$STATE/evidence"

if [ -r /workspaces/.codespaces/shared/.env ]; then
  set +x
  set -a
  . /workspaces/.codespaces/shared/.env
  set +a
fi

ROOT=""
if [ -d /workspaces/Omega-engines/.git ]; then
  ROOT=/workspaces/Omega-engines
else
  for candidate in /workspaces/*; do
    [ -d "$candidate/.git" ] || continue
    origin="$(git -C "$candidate" remote get-url origin 2>/dev/null || true)"
    case "$origin" in
      *sublimedeaf-design/Omega-engines*) ROOT="$candidate"; break ;;
    esac
  done
fi
[ -n "$ROOT" ] || { echo "OMEGA_STAGE_RUNTIME_MAIN=failure"; exit 31; }
cd "$ROOT"

if ! OMEGA_CODESPACES_BRANCH=main bash deploy/codespaces/sync-source.sh     >"$STATE/logs/postmerge-source-sync.log" 2>&1; then
  echo "OMEGA_STAGE_RUNTIME_MAIN=failure"
  exit 32
fi

head="$(git rev-parse HEAD)"
if [ "$head" != "$EXPECTED" ]; then
  echo "OMEGA_STAGE_RUNTIME_MAIN=failure"
  exit 33
fi
echo "OMEGA_STAGE_RUNTIME_MAIN=success"

set +e
python3 deploy/codespaces/federation-autovalidate.py   >"$STATE/logs/postmerge-federation-autovalidate.log" 2>&1
federation_rc=$?
set -e

access="$STATE/evidence/federation-access.json"
executor="$STATE/evidence/federation-executor.json"

peer_ok=false
executor_ok=false
if [ -s "$access" ]; then
  peer_ok="$(python3 - "$access" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
expected={"Omega-release","Omega-validation","Omega-agents","Omega-recovery","Jarv"}
http=p.get("peer_http") or {}
print("true" if p.get("authorized") is True and set(http)==expected and all(http.get(x)==200 for x in expected) else "false")
PY
)"
fi
if [ "$peer_ok" = true ]; then
  echo "OMEGA_STAGE_PEER_HTTP=success"
else
  echo "OMEGA_STAGE_PEER_HTTP=failure"
fi

if [ -s "$executor" ]; then
  executor_ok="$(python3 - "$executor" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
expected={"Omega-release","Omega-validation","Omega-agents","Omega-recovery","Jarv"}
rows=p.get("peers") or []
ok=(p.get("ok") is True and {r.get("repository") for r in rows}==expected and all(
    r.get("ok") is True and r.get("repository_http")==200 and r.get("source_pin_match") is True
    and r.get("validator_rc")==0 and r.get("tests_rc")==0 and r.get("status_http") in (200,201)
    for r in rows
))
print("true" if ok else "false")
PY
)"
fi
if [ "$executor_ok" = true ] && [ "$federation_rc" = 0 ]; then
  echo "OMEGA_STAGE_EXECUTOR=success"
else
  echo "OMEGA_STAGE_EXECUTOR=failure"
  if [ -s "$executor" ]; then
    python3 - "$executor" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
for row in p.get("peers") or []:
    fields={
      "repo":row.get("repository"),
      "repository_http":row.get("repository_http"),
      "source_pin_match":row.get("source_pin_match"),
      "validator_rc":row.get("validator_rc"),
      "tests_rc":row.get("tests_rc"),
      "status_http":row.get("status_http"),
      "ok":row.get("ok"),
      "error":row.get("error"),
    }
    print("OMEGA_DIAG_EXECUTOR "+" ".join(f"{k}={v}" for k,v in fields.items()))
PY
  fi
fi

set +e
python3 scripts/verify_federation_evidence.py   --access "$access" --executor "$executor"   >"$STATE/logs/postmerge-federation-verifier.log" 2>&1
verify_rc=$?
set -e
if [ "$verify_rc" = 0 ]; then
  echo "OMEGA_STAGE_VERIFIER=success"
else
  echo "OMEGA_STAGE_VERIFIER=failure"
fi

if [ "$peer_ok" != true ] || [ "$executor_ok" != true ] || [ "$federation_rc" != 0 ] || [ "$verify_rc" != 0 ]; then
  exit 34
fi

if bash deploy/codespaces/publish-evidence.sh     >"$STATE/logs/postmerge-evidence-publish.log" 2>&1; then
  echo "OMEGA_STAGE_PUBLISH=success"
else
  echo "OMEGA_STAGE_PUBLISH=failure"
  exit 35
fi
