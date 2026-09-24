#!/usr/bin/env bash
set -Eeuo pipefail

STATE="${OMEGA_STATE:-/workspaces/.omega-state}"
RUNNER_HOME="${OMEGA_CODESPACE_RUNNER_HOME:-$STATE/actions-runner}"
mkdir -p "$STATE/logs" "$STATE/evidence"

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
[ -n "$ROOT" ] || { echo "OMEGA_REUSE_REPO_NOT_FOUND" >&2; exit 41; }
cd "$ROOT"

SUPERVISOR=deploy/codespaces/runner-supervisor.sh
[ -x "$RUNNER_HOME/run.sh" ] || { echo "OMEGA_REUSE_RUNNER_BINARY_MISSING"; exit 42; }
[ -f "$RUNNER_HOME/.runner" ] || { echo "OMEGA_REUSE_RUNNER_CONFIG_MISSING"; exit 43; }
[ -f "$SUPERVISOR" ] || { echo "OMEGA_REUSE_SUPERVISOR_MISSING" >&2; exit 44; }

if pgrep -f "$RUNNER_HOME/bin/Runner.Listener" >/dev/null 2>&1; then
  pid="$(pgrep -f "$RUNNER_HOME/bin/Runner.Listener" | head -1)"
  echo "OMEGA_REUSE_RUNNER_ONLINE pid=$pid"
  exit 0
fi

while read -r pid; do
  [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null || true
done < <(pgrep -f 'bash deploy/codespaces/runner-supervisor[.]sh' 2>/dev/null || true)
sleep 1

nohup env OMEGA_STATE="$STATE" OMEGA_CODESPACE_RUNNER_HOME="$RUNNER_HOME" \
  bash "$SUPERVISOR" \
  >"$STATE/logs/actions-runner-supervisor-reuse.log" 2>&1 </dev/null &

for _ in $(seq 1 30); do
  sleep 2
  if pgrep -f "$RUNNER_HOME/bin/Runner.Listener" >/dev/null 2>&1; then
    pid="$(pgrep -f "$RUNNER_HOME/bin/Runner.Listener" | head -1)"
    echo "OMEGA_REUSE_RUNNER_ONLINE pid=$pid"
    exit 0
  fi
done

echo "OMEGA_REUSE_RUNNER_OFFLINE" >&2
tail -n 120 "$STATE/logs/actions-runner-supervisor.log" >&2 || true
tail -n 120 "$STATE/logs/actions-runner-supervisor-reuse.log" >&2 || true
exit 45
