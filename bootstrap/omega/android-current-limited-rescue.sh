#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
set +x

SOURCE_REPOSITORY="sublimedeaf-design/Omega-engines"
CONTROL_REPOSITORY="sublimedeaf-design/Omega-engine"
SOURCE_SHA="2f6635b66b74b4afc5f26013c73fc8b0db236a6e"
STAGER_RUN_ID="36344621894"
SIGNER_QUEUE_RUN_ID="36345017732"
RUNTIME_QUEUE_RUN_ID="36342638499"
SIGNER_RESCUE_SHA="3c69cbb8a3954d183590afac4e2bbd8fc7675353"
RUNTIME_RESCUE_SHA="e47c645a29004eab196285c1b4145c797f13bb66"

RUNNER_VERSION="2.337.0"
RUNNER_ARCHIVE="actions-runner-linux-arm64-${RUNNER_VERSION}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_ARCHIVE}"
RUNNER_SHA256="9b1dc70626422526e3c94767cf024896beb15da5342a3f4819bf2feac13e0393"
SIGNER_LABEL="omega-signer-rescue-v2"
RUNTIME_LABEL="omega-android-runtime-v1"

termux-wake-lock >/dev/null 2>&1 || true
pkg update -y
pkg install -y proot-distro curl android-tools
if ! proot-distro login ubuntu -- true >/dev/null 2>&1; then
  proot-distro install ubuntu
fi

proot-distro login ubuntu -- env \
  OMEGA_SOURCE_REPOSITORY="$SOURCE_REPOSITORY" \
  OMEGA_CONTROL_REPOSITORY="$CONTROL_REPOSITORY" \
  OMEGA_SOURCE_SHA="$SOURCE_SHA" \
  OMEGA_STAGER_RUN_ID="$STAGER_RUN_ID" \
  OMEGA_SIGNER_QUEUE_RUN_ID="$SIGNER_QUEUE_RUN_ID" \
  OMEGA_RUNTIME_QUEUE_RUN_ID="$RUNTIME_QUEUE_RUN_ID" \
  OMEGA_SIGNER_RESCUE_SHA="$SIGNER_RESCUE_SHA" \
  OMEGA_RUNTIME_RESCUE_SHA="$RUNTIME_RESCUE_SHA" \
  OMEGA_RUNNER_VERSION="$RUNNER_VERSION" \
  OMEGA_RUNNER_ARCHIVE="$RUNNER_ARCHIVE" \
  OMEGA_RUNNER_URL="$RUNNER_URL" \
  OMEGA_RUNNER_SHA256="$RUNNER_SHA256" \
  OMEGA_SIGNER_LABEL="$SIGNER_LABEL" \
  OMEGA_RUNTIME_LABEL="$RUNTIME_LABEL" \
  bash -lc '
set -Eeuo pipefail
set +x
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends ca-certificates curl git gh jq tar gzip unzip python3 openjdk-17-jre-headless aapt apksigner

if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  echo "OMEGA_PHONE_AUTH_REQUIRED: authorize GitHub once; credential is deleted before either runner executes."
  gh auth login --hostname github.com --git-protocol https --web
fi

current="$(gh api "/repos/$OMEGA_SOURCE_REPOSITORY/commits/main" --jq .sha)"
[ "$current" = "$OMEGA_SOURCE_SHA" ] || { echo "OMEGA_PHONE_MAIN_MOVED:$current!=$OMEGA_SOURCE_SHA" >&2; exit 75; }

verify_run() {
  local repo="$1" run_id="$2" expected_name="$3" expected_sha="$4"
  local raw
  raw="$(gh api "/repos/$repo/actions/runs/$run_id")"
  RUN_JSON="$raw" EXPECTED_NAME="$expected_name" EXPECTED_SHA="$expected_sha" python3 - <<'"'"'PY'"'"'
import json,os
r=json.loads(os.environ["RUN_JSON"])
if r.get("name")!=os.environ["EXPECTED_NAME"]:
    raise SystemExit("OMEGA_PHONE_RUN_NAME_MISMATCH")
if r.get("head_sha")!=os.environ["EXPECTED_SHA"]:
    raise SystemExit("OMEGA_PHONE_RUN_SHA_MISMATCH")
if r.get("status") not in {"queued","in_progress","completed"}:
    raise SystemExit("OMEGA_PHONE_RUN_STATUS_INVALID")
if r.get("status")=="completed" and r.get("conclusion") not in {"success"}:
    raise SystemExit("OMEGA_PHONE_REQUIRED_RUN_ALREADY_FAILED")
PY
}

stager="$(gh api "/repos/$OMEGA_CONTROL_REPOSITORY/actions/runs/$OMEGA_STAGER_RUN_ID")"
RUN_JSON="$stager" SOURCE_SHA="$OMEGA_SOURCE_SHA" python3 - <<'"'"'PY'"'"'
import json,os
r=json.loads(os.environ["RUN_JSON"])
if r.get("name")!="OMEGA Recovery Evidence Release Stager" or r.get("status")!="completed" or r.get("conclusion")!="success":
    raise SystemExit("OMEGA_PHONE_STAGER_NOT_SUCCESS")
PY

verify_run "$OMEGA_SOURCE_REPOSITORY" "$OMEGA_SIGNER_QUEUE_RUN_ID" "OMEGA Android Signing Keepalive" "$OMEGA_SIGNER_RESCUE_SHA"
verify_run "$OMEGA_SOURCE_REPOSITORY" "$OMEGA_RUNTIME_QUEUE_RUN_ID" "OMEGA Limited Distribution Installed Runtime Certification" "$OMEGA_RUNTIME_RESCUE_SHA"

HANDOFF=/opt/omega-current-limited/unsigned
RUNNER=/opt/omega-current-limited/runner
rm -rf "$HANDOFF"
mkdir -p "$HANDOFF"
gh run download "$OMEGA_STAGER_RUN_ID" -R "$OMEGA_CONTROL_REPOSITORY" \
  -n "OMEGA-Unsigned-Release-$OMEGA_SOURCE_SHA" -D "$HANDOFF"

apk="$(find "$HANDOFF" -type f -name OMEGA-Engine-unsigned.apk -print -quit)"
checksum="$(find "$HANDOFF" -type f -name OMEGA-Engine-unsigned.apk.sha256 -print -quit)"
prov="$(find "$HANDOFF" -type f -name OMEGA-Engine-unsigned.provenance.json -print -quit)"
test -s "$apk"; test -s "$checksum"; test -s "$prov"
actual="$(sha256sum "$apk" | awk "{print \$1}")"
recorded="$(awk "{print \$1}" "$checksum")"
[ "$actual" = "$recorded" ] || { echo OMEGA_PHONE_UNSIGNED_DIGEST_MISMATCH >&2; exit 78; }

EXPECTED_FINGERPRINT="$(gh api "/repos/$OMEGA_SOURCE_REPOSITORY/contents/android/signing-cert.sha256?ref=$OMEGA_SOURCE_SHA" --jq .content | tr -d "\n" | base64 -d | tr -d "[:space:]: " | tr "A-F" "a-f")"
APK_SHA="$actual" PROV="$prov" SOURCE="$OMEGA_SOURCE_SHA" FP="$EXPECTED_FINGERPRINT" python3 - <<'"'"'PY'"'"'
import json,os,re
p=json.load(open(os.environ["PROV"],encoding="utf-8"))
checks={
 "class":p.get("classification")=="PRODUCTION_RELEASE_PAYLOAD_UNSIGNED",
 "source":p.get("source_commit")==os.environ["SOURCE"],
 "apk":p.get("apk_sha256")==os.environ["APK_SHA"],
 "fingerprint":str(p.get("expected_signer_certificate_sha256") or "").replace(":","").lower()==os.environ["FP"].lower(),
}
if not all(checks.values()): raise SystemExit("OMEGA_PHONE_UNSIGNED_PROVENANCE_INVALID:"+repr(checks))
if not re.fullmatch(r"[0-9a-f]{64}",os.environ["FP"]): raise SystemExit("OMEGA_PHONE_FINGERPRINT_INVALID")
PY
echo "OMEGA_PHONE_CURRENT_HANDOFF_PASS source=$OMEGA_SOURCE_SHA stager=$OMEGA_STAGER_RUN_ID sha256=$actual"

SIGNER_TOKEN="$(gh api --method POST "/repos/$OMEGA_SOURCE_REPOSITORY/actions/runners/registration-token" --jq .token)"
RUNTIME_TOKEN="$(gh api --method POST "/repos/$OMEGA_SOURCE_REPOSITORY/actions/runners/registration-token" --jq .token)"
[ -n "$SIGNER_TOKEN" ] && [ -n "$RUNTIME_TOKEN" ] || { echo OMEGA_PHONE_RUNNER_TOKEN_EMPTY >&2; exit 67; }

# No long-lived user credential crosses into either repository workflow.
rm -rf /root/.config/gh

prepare_runner() {
  rm -rf "$RUNNER"; mkdir -p "$RUNNER"; cd "$RUNNER"
  curl -fL "$OMEGA_RUNNER_URL" -o "$OMEGA_RUNNER_ARCHIVE"
  echo "$OMEGA_RUNNER_SHA256  $OMEGA_RUNNER_ARCHIVE" | sha256sum -c -
  tar xzf "$OMEGA_RUNNER_ARCHIVE"; rm -f "$OMEGA_RUNNER_ARCHIVE"
  ./bin/installdependencies.sh
}
export RUNNER_ALLOW_RUNASROOT=1

prepare_runner
./config.sh --unattended --url "https://github.com/$OMEGA_SOURCE_REPOSITORY" \
  --token "$SIGNER_TOKEN" --name "omega-current-signer-$(date +%s)" \
  --labels "$OMEGA_SIGNER_LABEL" --ephemeral --replace
unset SIGNER_TOKEN
export OMEGA_ONE_CLICK_UNSIGNED_DIR="$HANDOFF"
echo "OMEGA_PHONE_SIGNER_RUNNER_READY source=$OMEGA_SOURCE_SHA queue=$OMEGA_SIGNER_QUEUE_RUN_ID"
./run.sh
unset OMEGA_ONE_CLICK_UNSIGNED_DIR

prepare_runner
./config.sh --unattended --url "https://github.com/$OMEGA_SOURCE_REPOSITORY" \
  --token "$RUNTIME_TOKEN" --name "omega-current-runtime-$(date +%s)" \
  --labels "$OMEGA_RUNTIME_LABEL" --ephemeral --replace
unset RUNTIME_TOKEN
echo "OMEGA_PHONE_RUNTIME_RUNNER_READY source=$OMEGA_SOURCE_SHA queue=$OMEGA_RUNTIME_QUEUE_RUN_ID"
exec ./run.sh
'
