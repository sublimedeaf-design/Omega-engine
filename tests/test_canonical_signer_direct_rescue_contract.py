from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WF = (ROOT / ".github/workflows/omega-canonical-android-signer.yml").read_text(encoding="utf-8")


def test_public_signer_preserves_private_signer_boundary() -> None:
    assert "Request repo-local signer rescue with bounded direct fallback" in WF
    assert "PRIVATE_TOKEN: ${{ secrets.OMEGA_BOOTSTRAP_TOKEN }}" in WF
    assert "PRIVATE_SIGNER_WORKFLOW: android-signing-keepalive.yml" in WF
    assert "sleep 10" in WF
    assert 'current="$(GH_TOKEN="$PRIVATE_TOKEN" gh api "/repos/$PRIVATE_REPOSITORY/commits/main" --jq .sha)"' in WF
    assert 'if [ "$current" != "$FINAL_SHA" ]; then' in WF
    assert "OMEGA_NATIVE_SIGNER_DIRECT_STALE_NOOP" in WF


def test_public_signer_dispatches_only_existing_fingerprint_locked_rescue() -> None:
    assert 'gh workflow run "$PRIVATE_SIGNER_WORKFLOW"' in WF
    assert '-f mode=rescue' in WF
    assert '-f allow_private_self_hosted=true' in WF
    assert "OMEGA_NATIVE_SIGNER_DIRECT_RESCUE_DISPATCHED" in WF
    assert "backend=github-hosted-cache-rescue" in WF
    block = WF.split("Request repo-local signer rescue with bounded direct fallback", 1)[1]
    block = block.split("Hold certification pending when no canonical signer backend is available", 1)[0]
    for forbidden in ("OMEGA_ANDROID_KEYSTORE_B64", "base64 -d", "keytool", "apksigner", "debug.keystore"):
        assert forbidden not in block


def test_direct_rescue_is_deduplicated_and_non_certifying() -> None:
    block = WF.split("Request repo-local signer rescue with bounded direct fallback", 1)[1]
    block = block.split("Hold certification pending when no canonical signer backend is available", 1)[0]
    assert "status=queued" in block
    assert "status=in_progress" in block
    assert "OMEGA_NATIVE_SIGNER_RESCUE_ALREADY_ACTIVE" in block
    assert "statuses/" not in block
    assert "omega/android-release-signed" not in block
    assert "omega/signer/continuity" not in block


if __name__ == "__main__":
    test_public_signer_preserves_private_signer_boundary()
    test_public_signer_dispatches_only_existing_fingerprint_locked_rescue()
    test_direct_rescue_is_deduplicated_and_non_certifying()
    print("OMEGA_CANONICAL_SIGNER_DIRECT_RESCUE_CONTRACT_PASS")
