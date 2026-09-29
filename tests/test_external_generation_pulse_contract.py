from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = (ROOT / "bootstrap/omega/qstash/cloudflare-generation-pulse.js").read_text(encoding="utf-8")
WRANGLER = (ROOT / "bootstrap/omega/qstash/wrangler.toml").read_text(encoding="utf-8")
SCHEDULE = (ROOT / "bootstrap/omega/qstash/create-schedule.sh").read_text(encoding="utf-8")


def test_external_pulse_can_only_dispatch_generation_reconciler() -> None:
    assert 'GENERATION_WORKFLOW = "omega-generation-reconciler.yml"' in WORKER
    assert "/actions/workflows/${GENERATION_WORKFLOW}/dispatches" in WORKER
    assert 'action: "already_active"' in WORKER
    assert "queued" in WORKER and "in_progress" in WORKER
    for forbidden in (
        "Omega-engines",
        "android-signing-keepalive.yml",
        "omega-canonical-android-signer.yml",
        "OMEGA_BOOTSTRAP_TOKEN",
        "keystore",
        "apksigner",
    ):
        assert forbidden not in WORKER


def test_external_pulse_is_authenticated_and_fail_closed() -> None:
    assert "OMEGA_CONTROL_DISPATCH_TOKEN_MISSING" in WORKER
    assert "OMEGA_CONTROL_KEY" in WORKER
    assert 'return response(403, { ok: false, error: "forbidden" })' in WORKER
    assert 'request.method !== "POST" || url.pathname !== "/pulse"' in WORKER
    assert 'url.pathname === "/healthz"' in WORKER


def test_cloudflare_and_qstash_cadences_are_bounded() -> None:
    assert 'crons = ["*/5 * * * *"]' in WRANGLER
    assert 'CRON="${OMEGA_QSTASH_CRON:-*/10 * * * *}"' in SCHEDULE
    assert 'RETRIES="${OMEGA_QSTASH_RETRIES:-3}"' in SCHEDULE
    assert '"$RETRIES" -le 3' in SCHEDULE
    assert "omega-generation-pulse-v1" in SCHEDULE
    assert "Upstash-Schedule-Id" in SCHEDULE
    assert "Upstash-Forward-Authorization" in SCHEDULE


if __name__ == "__main__":
    test_external_pulse_can_only_dispatch_generation_reconciler()
    test_external_pulse_is_authenticated_and_fail_closed()
    test_cloudflare_and_qstash_cadences_are_bounded()
    print("OMEGA_EXTERNAL_GENERATION_PULSE_CONTRACT_PASS")
