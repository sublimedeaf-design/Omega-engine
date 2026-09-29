# OMEGA Google Cloud Shell external-controller proof

This performs the missing independent-node proof without changing the canonical Android runtime authority.

## Start

Set the target Tailscale address and Termux SSH user in the terminal, then run the controller:

```bash
OMEGA_TARGET="<TAILSCALE_IP_OR_MAGICDNS>" \
OMEGA_SSH_USER="<TERMUX_USER>" \
bash cloud/google-cloudshell-omega-controller.sh
```

The script:

1. installs Tailscale if needed;
2. starts Tailscale in userspace networking mode with a local SOCKS5 proxy;
3. asks you to authorize the temporary Google Cloud Shell node in Tailscale;
4. proves peer reachability with `tailscale ping`;
5. generates a dedicated Ed25519 controller key;
6. uses the existing Termux password once to enroll that public key;
7. re-connects with public-key authentication and strict host-key verification;
8. reads device identity and the OMEGA heartbeat.

A successful run ends with:

```text
OMEGA_EXTERNAL_CONTROLLER_AUTHENTICATED_PASS
```

This is a transport/control proof only. It does not replace native Android physical attestation or certify the release.
