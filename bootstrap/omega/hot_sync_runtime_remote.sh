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
echo "OMEGA_REMOTE_SOURCE_SYNCED sha=$new_sha"

# start.sh is idempotent. It hot-reloads the runtime supervisor when its source
# hash changed, restores runner supervision if possible, and launches the
# runner-independent federation validator.
timeout 120 bash .devcontainer/start.sh
echo "OMEGA_REMOTE_RUNTIME_HOT_RELOADED sha=$(git rev-parse HEAD)"
