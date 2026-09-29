#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="${OMEGA_TARGET:-}"
SSH_USER="${OMEGA_SSH_USER:-}"
SSH_PORT="${OMEGA_SSH_PORT:-8022}"
TS_HOSTNAME="${OMEGA_TS_HOSTNAME:-omega-google-cloudshell}"
STATE="${HOME}/.omega-cloudshell/tailscale.state"
SOCKET="${HOME}/.omega-cloudshell/tailscaled.sock"
LOG="${HOME}/.omega-cloudshell/tailscaled.log"
SOCKS="127.0.0.1:1055"
KEY="${HOME}/.ssh/omega_cloudshell_ed25519"

fail(){ echo "$1" >&2; exit "${2:-1}"; }

[ -n "$TARGET" ] || fail "OMEGA_TARGET_REQUIRED"
[ -n "$SSH_USER" ] || fail "OMEGA_SSH_USER_REQUIRED"

mkdir -p "${HOME}/.omega-cloudshell" "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"

if ! command -v tailscale >/dev/null 2>&1 || ! command -v tailscaled >/dev/null 2>&1; then
  echo "OMEGA_INSTALL_TAILSCALE"
  curl -fsSL https://tailscale.com/install.sh | sh
fi

if ! command -v nc >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y netcat-openbsd
fi

pkill -f "tailscaled.*$SOCKET" >/dev/null 2>&1 || true
rm -f "$SOCKET"

nohup sudo tailscaled \
  --tun=userspace-networking \
  --socks5-server="$SOCKS" \
  --state="$STATE" \
  --socket="$SOCKET" \
  >"$LOG" 2>&1 &

for _ in $(seq 1 30); do
  if sudo tailscale --socket="$SOCKET" status >/dev/null 2>&1; then break; fi
  sleep 1
done

echo "OMEGA_TAILSCALE_LOGIN_BEGIN"
sudo tailscale --socket="$SOCKET" up \
  --hostname="$TS_HOSTNAME" \
  --accept-routes=false \
  --accept-dns=false
echo "OMEGA_TAILSCALE_LOGIN_PASS"

sudo tailscale --socket="$SOCKET" status
sudo tailscale --socket="$SOCKET" ping --timeout=10s --until-direct=false --c=1 "$TARGET"
echo "OMEGA_EXTERNAL_PEER_REACHABILITY_PASS target=$TARGET"

if [ ! -f "$KEY" ]; then
  ssh-keygen -t ed25519 -N "" -f "$KEY" -C "omega-google-cloudshell"
fi

PROXY="nc -X 5 -x $SOCKS %h %p"

echo
echo "OMEGA_BOOTSTRAP_SSH_KEY"
echo "The next command may ask for the existing Termux password once."
echo "Type it only in this Cloud Shell terminal; do not share it elsewhere."
ssh-copy-id \
  -i "$KEY.pub" \
  -p "$SSH_PORT" \
  -o "ProxyCommand=$PROXY" \
  -o StrictHostKeyChecking=accept-new \
  "$SSH_USER@$TARGET"

echo "OMEGA_SSH_KEY_ENROLLED_PASS"

REMOTE="$(ssh \
  -i "$KEY" \
  -p "$SSH_PORT" \
  -o BatchMode=yes \
  -o PasswordAuthentication=no \
  -o "ProxyCommand=$PROXY" \
  -o StrictHostKeyChecking=yes \
  "$SSH_USER@$TARGET" \
  "printf 'identity user=%s model=%s android=%s\\n' \"\$(whoami)\" \"\$(getprop ro.product.model 2>/dev/null)\" \"\$(getprop ro.build.version.release 2>/dev/null)\"; tail -3 ~/omega-device/heartbeat.log")"

printf '%s\n' "$REMOTE"

grep -F "identity user=$SSH_USER " <<<"$REMOTE" >/dev/null || fail "OMEGA_EXTERNAL_CONTROLLER_IDENTITY_FAIL" 65
grep -F "OMEGA_DEVICE_ALIVE" <<<"$REMOTE" >/dev/null || fail "OMEGA_EXTERNAL_CONTROLLER_HEARTBEAT_FAIL" 65

echo "OMEGA_EXTERNAL_CONTROLLER_AUTHENTICATED_PASS target=$TARGET"
