#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_REPOSITORY="${OMEGA_TARGET_REPOSITORY:-sublimedeaf-design/Omega-engines}"
STATE="${OMEGA_STATE:-/workspaces/.omega-state}"
mkdir -p "$STATE/logs" 2>/dev/null || true

declare -a homes=()
add_home() {
  local p="$1"
  [ -n "$p" ] || return 0
  for existing in "${homes[@]:-}"; do
    [ "$existing" = "$p" ] && return 0
  done
  homes+=("$p")
}

add_home "$STATE/actions-runner"
add_home "/workspaces/.omega-state/actions-runner"
add_home "$HOME/.omega-state/actions-runner"

while IFS= read -r runner_file; do
  add_home "$(dirname "$runner_file")"
done < <(find /workspaces "$HOME" -maxdepth 5 -type f -name .runner 2>/dev/null || true)

for home in "${homes[@]}"; do
  [ -x "$home/run.sh" ] || continue
  [ -f "$home/.runner" ] || continue
  [ -f "$home/.credentials" ] || continue

  github_url="$(python3 - "$home/.runner" <<'PY'
import json,sys
try:
    data=json.load(open(sys.argv[1],encoding="utf-8-sig"))
    print(data.get("gitHubUrl") or "")
except Exception:
    print("")
PY
)"
  case "$github_url" in
    "https://github.com/$TARGET_REPOSITORY"|"https://github.com/$TARGET_REPOSITORY/" ) ;;
    *) continue ;;
  esac

  runner_name="$(python3 - "$home/.runner" <<'PY'
import json,sys
try:
    data=json.load(open(sys.argv[1],encoding="utf-8-sig"))
    print(data.get("agentName") or "unknown")
except Exception:
    print("unknown")
PY
)"

  if pgrep -f "$home/bin/Runner.Listener" >/dev/null 2>&1; then
    pid="$(pgrep -f "$home/bin/Runner.Listener" | head -1)"
    echo "OMEGA_REGISTERED_RUNNER_ALREADY_ONLINE name=$runner_name pid=$pid home=$home"
    exit 0
  fi

  log="$STATE/logs/reused-registered-runner.log"
  (
    cd "$home"
    nohup ./run.sh >>"$log" 2>&1 </dev/null &
  )

  for _ in $(seq 1 30); do
    sleep 2
    if pgrep -f "$home/bin/Runner.Listener" >/dev/null 2>&1; then
      pid="$(pgrep -f "$home/bin/Runner.Listener" | head -1)"
      echo "OMEGA_REGISTERED_RUNNER_REUSED name=$runner_name pid=$pid home=$home"
      exit 0
    fi
  done

  echo "OMEGA_REGISTERED_RUNNER_START_FAILED name=$runner_name home=$home" >&2
  tail -n 100 "$log" >&2 || true
done

echo "OMEGA_REGISTERED_RUNNER_NOT_FOUND"
exit 46
