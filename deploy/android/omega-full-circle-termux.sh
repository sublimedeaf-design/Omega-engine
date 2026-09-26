#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REPO="sublimedeaf-design/Omega-engines"
WORKFLOW="omega-android-arm64-hotfix.yml"
SOURCE_SHA="e916529109d9abab278e7420062f3c423903b281"
ARTIFACT="OMEGA-ARM64-Hotfix-$SOURCE_SHA"
PACKAGE="com.omega.app"
VERSION_CODE="17"
RUNNER_VERSION="2.337.0"
RUNNER_ARCHIVE="actions-runner-linux-arm64-$RUNNER_VERSION.tar.gz"
RUNNER_SHA256="9b1dc70626422526e3c94767cf024896beb15da5342a3f4819bf2feac13e0393"

ROOT="$HOME/.omega-full-circle"
LOG="$ROOT/full-circle.log"
ART="$ROOT/artifact"
STATE="$ROOT/state"
mkdir -p "$ROOT" "$ART" "$STATE"
touch "$LOG"
exec > >(tee -a "$LOG") 2>&1

stamp(){ date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log(){ printf '%s %s\n' "$(stamp)" "$*"; }
die(){ log "FATAL $*"; exit 1; }

log "OMEGA_FULL_CIRCLE_START"
termux-wake-lock >/dev/null 2>&1 || true

missing=0
for x in proot-distro curl jq gh adb sha256sum; do command -v "$x" >/dev/null 2>&1 || missing=1; done
if [ "$missing" -eq 1 ]; then
  pkg update -y
  pkg install -y proot-distro curl jq gh android-tools coreutils
fi

if ! proot-distro login ubuntu -- true >/dev/null 2>&1; then
  proot-distro install ubuntu
fi

runner_dir(){
  proot-distro login ubuntu -- bash -lc '
    for d in /root/actions-runner /opt/omega-signer-rescue/runner /opt/omega-runner; do
      if [ -x "$d/run.sh" ] && [ -f "$d/.runner" ]; then printf "%s\n" "$d"; exit 0; fi
    done
    exit 1
  ' 2>/dev/null
}

bootstrap_runner(){
  gh auth status -h github.com >/dev/null 2>&1 || die "Runner ontbreekt en GitHub CLI is niet geauthenticeerd."
  token="$(gh api --method POST "repos/$REPO/actions/runners/registration-token" --jq .token)"
  [ -n "$token" ] || die "Geen runner registration token"
  proot-distro login ubuntu -- env TOKEN="$token" REPO="$REPO" VER="$RUNNER_VERSION" ARCHIVE="$RUNNER_ARCHIVE" SUM="$RUNNER_SHA256" bash -lc '
    set -Eeuo pipefail
    export DEBIAN_FRONTEND=noninteractive RUNNER_ALLOW_RUNASROOT=1
    apt-get -o Acquire::Retries=5 update
    apt-get -o Acquire::Retries=5 install -y --no-install-recommends ca-certificates curl tar gzip git jq
    d=/root/actions-runner; mkdir -p "$d"; cd "$d"
    if [ ! -x ./run.sh ]; then
      curl -fL --retry 5 --retry-all-errors --connect-timeout 20 \
        "https://github.com/actions/runner/releases/download/v$VER/$ARCHIVE" -o "$ARCHIVE"
      printf "%s  %s\n" "$SUM" "$ARCHIVE" | sha256sum -c -
      tar xzf "$ARCHIVE"; rm -f "$ARCHIVE"; ./bin/installdependencies.sh
    fi
    if [ ! -f .runner ]; then
      ./config.sh --unattended --replace --url "https://github.com/$REPO" \
        --token "$TOKEN" --name omega-android-anchor --labels omega-signer-rescue-v2
    fi
  '
}

ensure_runner(){
  pgrep -f 'Runner.Listener' >/dev/null 2>&1 && return 0
  d="$(runner_dir || true)"
  if [ -z "$d" ]; then bootstrap_runner; d="$(runner_dir || true)"; fi
  [ -n "$d" ] || die "Runnerconfiguratie ontbreekt"
  log "Starting runner: $d"
  nohup proot-distro login ubuntu -- env RUNNER_ALLOW_RUNASROOT=1 bash -lc "cd '$d' && exec ./run.sh" \
    >>"$ROOT/runner.log" 2>&1 < /dev/null &
  sleep 5
  pgrep -f 'Runner.Listener' >/dev/null 2>&1 || die "Runner.Listener startte niet"
}

latest_runs(){
  gh run list -R "$REPO" --workflow "$WORKFLOW" --limit 10 \
    --json databaseId,status,conclusion,headSha,createdAt 2>/dev/null || printf '[]'
}

maybe_dispatch(){
  gh auth status -h github.com >/dev/null 2>&1 || return 0
  rows="$(latest_runs)"
  active="$(jq -r '[.[]|select(.status=="queued" or .status=="in_progress" or .status=="pending")]|length' <<<"$rows")"
  [ "$active" -gt 0 ] && return 0
  count="$(jq -r 'length' <<<"$rows")"
  if [ "$count" -eq 0 ]; then
    log "Dispatching certified hotfix run"
    gh workflow run "$WORKFLOW" -R "$REPO" -f source_sha="$SOURCE_SHA"
  fi
}

find_apk(){
  for p in \
    /sdcard/Download/OMEGA/OMEGA-Engine.apk \
    /storage/emulated/0/Download/OMEGA/OMEGA-Engine.apk \
    "$HOME/storage/shared/Download/OMEGA/OMEGA-Engine.apk" \
    "$ART/OMEGA-Engine.apk"
  do
    [ -s "$p" ] && { printf '%s\n' "$p"; return 0; }
  done
  return 1
}

download_success(){
  gh auth status -h github.com >/dev/null 2>&1 || return 1
  rows="$(latest_runs)"
  run="$(jq -r '[.[]|select(.status=="completed" and .conclusion=="success")][0].databaseId // empty' <<<"$rows")"
  [ -n "$run" ] || return 1
  rm -rf "$ART"; mkdir -p "$ART"
  gh run download "$run" -R "$REPO" -n "$ARTIFACT" -D "$ART" >/dev/null
  [ -s "$ART/OMEGA-Engine.apk" ]
}

verify_apk(){
  apk="$1"; dir="$(dirname "$apk")"; sum="$dir/OMEGA-Engine.apk.sha256"
  [ -s "$sum" ] || return 1
  expected="$(awk 'NR==1{print $1}' "$sum" | tr 'A-F' 'a-f')"
  actual="$(sha256sum "$apk" | awk '{print $1}' | tr 'A-F' 'a-f')"
  [ "$(printf %s "$expected" | wc -c)" -eq 64 ] && [ "$expected" = "$actual" ] || return 1
  printf '%s\n' "$actual"
}

install_and_prove(){
  apk="$1"; digest="$2"
  adb start-server >/dev/null 2>&1 || true
  serial="$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1; exit}')"
  if [ -n "$serial" ]; then
    log "Authorized ADB device: $serial"
    adb -s "$serial" install -r "$apk"
    adb -s "$serial" shell am force-stop "$PACKAGE"
    adb -s "$serial" shell am start -W -n "$PACKAGE/.MainActivity" | tee "$ROOT/cold-start.txt"
    adb -s "$serial" shell pidof "$PACKAGE" | tee "$ROOT/pid.txt"
    test -s "$ROOT/pid.txt"
    log "OMEGA_LIVE_CERTIFIED_LOCAL sha256=$digest versionCode=$VERSION_CODE"
    exit 0
  fi
  opened="$(cat "$STATE/installer-opened.sha256" 2>/dev/null || true)"
  if [ "$opened" != "$digest" ]; then
    log "No pre-authorized ADB path; opening Android Package Installer once."
    termux-open --view --content-type application/vnd.android.package-archive "$apk"
    printf '%s\n' "$digest" > "$STATE/installer-opened.sha256"
  fi
  log "ANDROID_CONFIRMATION_REQUIRED_ONCE sha256=$digest"
  log "Android's package installer is now the only remaining first-install boundary."
  exit 20
}

mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/omega-full-circle" <<BOOT
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock >/dev/null 2>&1 || true
nohup "$ROOT/omega-full-circle.sh" >>"$LOG" 2>&1 < /dev/null &
BOOT
chmod +x "$HOME/.termux/boot/omega-full-circle"
cp -f "$0" "$ROOT/omega-full-circle.sh" 2>/dev/null || true
chmod +x "$ROOT/omega-full-circle.sh" 2>/dev/null || true

while :; do
  ensure_runner
  maybe_dispatch || true
  apk="$(find_apk || true)"
  if [ -z "$apk" ]; then
    download_success || true
    apk="$(find_apk || true)"
  fi
  if [ -n "$apk" ]; then
    digest="$(verify_apk "$apk" || true)"
    if [ -n "$digest" ]; then
      log "OMEGA_APK_VERIFIED path=$apk sha256=$digest"
      install_and_prove "$apk" "$digest"
    fi
  fi
  sleep 20
done
