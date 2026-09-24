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

# Give asynchronous acceptance/federation workers a short bounded window to
# emit phase markers, then publish redacted diagnostics. Failure to publish
# evidence must not turn runtime hot-sync into a false outage.
sleep 8
timeout 60 bash deploy/codespaces/publish-evidence.sh || true
echo "OMEGA_REMOTE_EVIDENCE_REFRESH_REQUESTED"
