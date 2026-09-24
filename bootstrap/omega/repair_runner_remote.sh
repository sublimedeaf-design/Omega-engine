#!/usr/bin/env bash
set -Eeuo pipefail

STATE="${OMEGA_STATE:-/workspaces/.omega-state}"
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
[ -n "$ROOT" ] || { echo "OMEGA_REMOTE_REPO_NOT_FOUND" >&2; exit 21; }
cd "$ROOT"

RUNNER_HOME="${OMEGA_CODESPACE_RUNNER_HOME:-$STATE/actions-runner}"
INSTALL=deploy/codespaces/install-actions-runner.sh
SUPERVISOR=deploy/codespaces/runner-supervisor.sh
[ -f "$SUPERVISOR" ] || { echo "OMEGA_REMOTE_RUNNER_SUPERVISOR_MISSING" >&2; exit 22; }

if [ ! -x "$RUNNER_HOME/run.sh" ] || [ ! -f "$RUNNER_HOME/.runner" ]; then
  [ -f "$INSTALL" ] || { echo "OMEGA_REMOTE_RUNNER_INSTALLER_MISSING" >&2; exit 23; }
  if ! env OMEGA_STATE="$STATE" OMEGA_CODESPACE_RUNNER_HOME="$RUNNER_HOME" bash "$INSTALL"       >"$STATE/logs/actions-runner-install-remote-repair.log" 2>&1; then
    echo "OMEGA_REMOTE_RUNNER_INSTALL_FAILED" >&2
    tail -n 80 "$STATE/logs/actions-runner-install-remote-repair.log" >&2 || true
    exit 24
  fi
fi

if pgrep -f "$RUNNER_HOME/bin/Runner.Listener" >/dev/null 2>&1; then
  pid="$(pgrep -f "$RUNNER_HOME/bin/Runner.Listener" | head -1)"
  echo "OMEGA_REMOTE_RUNNER_ONLINE pid=$pid"
  exit 0
fi

# Replace a stale supervisor; the runner process itself is only touched if absent.
while read -r pid; do
  [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null || true
done < <(pgrep -f 'bash deploy/codespaces/runner-supervisor[.]sh' 2>/dev/null || true)
sleep 1

nohup env OMEGA_STATE="$STATE" OMEGA_CODESPACE_RUNNER_HOME="$RUNNER_HOME"   bash "$SUPERVISOR"   >"$STATE/logs/actions-runner-supervisor-remote-repair.log" 2>&1 </dev/null &

for _ in $(seq 1 20); do
  sleep 2
  if pgrep -f "$RUNNER_HOME/bin/Runner.Listener" >/dev/null 2>&1; then
    pid="$(pgrep -f "$RUNNER_HOME/bin/Runner.Listener" | head -1)"
    echo "OMEGA_REMOTE_RUNNER_ONLINE pid=$pid"
    exit 0
  fi
done

echo "OMEGA_REMOTE_RUNNER_OFFLINE" >&2
tail -n 120 "$STATE/logs/actions-runner-supervisor.log" >&2 || true
tail -n 120 "$STATE/logs/actions-runner-supervisor-remote-repair.log" >&2 || true
exit 25
