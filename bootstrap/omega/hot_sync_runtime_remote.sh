#!/usr/bin/env bash
set -Eeuo pipefail

STATE="${OMEGA_STATE:-/workspaces/.omega-state}"
ROOT=""
for candidate in /workspaces/*; do
  [ -d "$candidate" ] || continue
  [ -f "$candidate/deploy/codespaces/sync-source.sh" ] || continue
  remote="$(git -C "$candidate" remote get-url origin 2>/dev/null || true)"
  case "$remote" in
    *github.com/sublimedeaf-design/Omega-engines*|*github.com:sublimedeaf-design/Omega-engines*)
      ROOT="$candidate"
      break
      ;;
  esac
done

[ -n "$ROOT" ] || {
  echo "OMEGA_REMOTE_SOURCE_ROOT_NOT_FOUND" >&2
  exit 44
}

cd "$ROOT"
export OMEGA_STATE="$STATE"

# Keep acceptance on a GitHub-known source SHA. Local-only evidence drift is
# repaired immediately. A running acceptance may also be superseded only when
# the requested SHA is a verified fast-forward descendant of the current remote
# SHA. VM/autonomous mutation cycles are never killed by this controller.
expected_sha="${OMEGA_EXPECTED_PRIVATE_HEAD:-}"
current_sha="$(git rev-parse HEAD)"
acceptance_running=false
cycle_running=false
pgrep -f 'deploy/codespaces/acceptance-test.sh' >/dev/null 2>&1 && acceptance_running=true
pgrep -f 'deploy/vm/omega-cycle.sh' >/dev/null 2>&1 && cycle_running=true

if { [ "$acceptance_running" = true ] || [ "$cycle_running" = true ]; } && \
   [ -n "$expected_sha" ] && [ "$expected_sha" != "$current_sha" ]; then
  timeout 45 git fetch -q origin main >/dev/null 2>&1 || true
  evidence_only_drift=false
  remote_knows_current=false
  supersedable_acceptance=false

  if git branch -r --contains "$current_sha" 2>/dev/null | grep -q .; then
    remote_knows_current=true
  fi

  if [ "$remote_knows_current" = false ]; then
    base="$(git merge-base "$current_sha" "origin/main" 2>/dev/null || true)"
    if [ -n "$base" ]; then
      changed="$(git diff --name-only "$base..$current_sha" 2>/dev/null || true)"
      if [ -n "$changed" ] && ! printf '%s\n' "$changed" | grep -Ev '^evidence/codespaces-live/' >/dev/null; then
        evidence_only_drift=true
      fi
    fi
  elif [ "$acceptance_running" = true ] && [ "$cycle_running" = false ] && \
       [ "${OMEGA_ALLOW_ACCEPTANCE_SUPERSEDE:-1}" = "1" ] && \
       git cat-file -e "$expected_sha^{commit}" 2>/dev/null && \
       git merge-base --is-ancestor "$current_sha" "$expected_sha" >/dev/null 2>&1; then
    supersedable_acceptance=true
  fi

  if [ "$evidence_only_drift" = true ]; then
    echo "OMEGA_LOCAL_EVIDENCE_DRIFT_RECOVERY current=$current_sha expected=$expected_sha"
    pkill -f 'deploy/codespaces/acceptance-test.sh' >/dev/null 2>&1 || true
    rm -f "$STATE/acceptance.lock" "$STATE/acceptance.last-attempt"
    git reset --hard -q "$expected_sha"
    current_sha="$expected_sha"
  elif [ "$supersedable_acceptance" = true ]; then
    echo "OMEGA_ACCEPTANCE_SUPERSEDED current=$current_sha expected=$expected_sha"
    pkill -f 'deploy/codespaces/acceptance-test.sh' >/dev/null 2>&1 || true
    rm -f "$STATE/acceptance.lock" "$STATE/acceptance.last-attempt" \
          "$STATE/acceptance-rebuild-armed" \
          "$STATE/evidence/acceptance-pre-rebuild.json" \
          "$STATE/evidence/acceptance-live.json"
    git reset --hard -q "$expected_sha"
    current_sha="$expected_sha"
  else
    echo "OMEGA_REMOTE_SOURCE_SYNC_DEFERRED validated_mutation_running=true current=$current_sha expected=$expected_sha"
    timeout 60 bash deploy/codespaces/publish-evidence.sh || true
    exit 0
  fi
fi

# The private repository owns all sync/runtime logic. This public bootstrap only
# invokes those checked-in scripts; it never copies private source into public CI.
timeout 90 bash deploy/codespaces/sync-source.sh
new_sha="$(git rev-parse HEAD)"
expected_sha="${OMEGA_EXPECTED_PRIVATE_HEAD:-}"
if [ -n "$expected_sha" ]; then
  case "$expected_sha" in
    *[!0-9a-f]*|'') echo "OMEGA_EXPECTED_PRIVATE_HEAD_INVALID" >&2; exit 45 ;;
  esac
  [ "${#expected_sha}" -eq 40 ] || { echo "OMEGA_EXPECTED_PRIVATE_HEAD_INVALID" >&2; exit 45; }
  git cat-file -e "$expected_sha^{commit}" 2>/dev/null || {
    echo "OMEGA_EXPECTED_PRIVATE_HEAD_NOT_FETCHED:$expected_sha" >&2
    exit 46
  }
  git merge-base --is-ancestor "$expected_sha" "$new_sha" || {
    echo "OMEGA_PRIVATE_RUNTIME_BEHIND expected=$expected_sha actual=$new_sha" >&2
    exit 47
  }
fi
echo "OMEGA_REMOTE_SOURCE_SYNCED sha=$new_sha expected=${expected_sha:-unset}"

# start.sh is idempotent. It hot-reloads the runtime supervisor when its source
# hash changed, restores runner supervision if possible, and launches the
# runner-independent federation validator.
timeout 120 bash .devcontainer/start.sh
echo "OMEGA_REMOTE_RUNTIME_HOT_RELOADED sha=$(git rev-parse HEAD)"

# Preflight emits only check names + OK/FAIL; command outputs are suppressed by
# the private script, so this is safe diagnostic material for the public controller.
set +e
preflight_out="$(bash deploy/codespaces/preflight.sh 2>&1)"
preflight_rc=$?
set -e
printf '%s\n' "$preflight_out"
echo "OMEGA_REMOTE_PREFLIGHT_RC=$preflight_rc"

# If acceptance is absent, launch it through bash rather than relying on the
# workspace executable bit/mount semantics. The private runtime owns the lock.
if [ ! -s "$STATE/evidence/acceptance-pre-rebuild.json" ] && [ ! -s "$STATE/evidence/acceptance-live.json" ] && \
   ! pgrep -f 'deploy/codespaces/acceptance-test.sh' >/dev/null 2>&1; then
  nohup bash deploy/codespaces/acceptance-test.sh \
    >"$STATE/logs/acceptance-bootstrap.log" 2>&1 &
  echo "OMEGA_REMOTE_ACCEPTANCE_LAUNCHED"
fi

# Give asynchronous acceptance/federation workers a short bounded window to
# emit phase markers, then publish redacted diagnostics. Failure to publish
# evidence must not turn runtime hot-sync into a false outage.
sleep 8
# Run federation validation synchronously as a bounded convergence gate. This
# removes the 15-minute supervisor delay after a source/auth repair.
set +e
timeout 300 bash deploy/codespaces/federation-autovalidate.sh
federation_rc=$?
set -e
echo "OMEGA_REMOTE_FEDERATION_RC=$federation_rc"
timeout 60 bash deploy/codespaces/publish-evidence.sh || true
echo "OMEGA_REMOTE_EVIDENCE_REFRESH_REQUESTED"
