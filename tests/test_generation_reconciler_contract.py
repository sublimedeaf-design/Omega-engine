from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generation_reconciler_is_level_triggered_and_reads_full_status_history():
    text = _text("control-plane/generation-reconciler.mjs")
    assert 'model: "level-triggered-generation-reconciliation"' in text
    assert 'oneActionPerReconcile: true' in text
    assert '/statuses?per_page=100&page=' in text
    assert 'staleStatusSource: "full-status-history-newest-per-context"' in text
    assert 'omega/control-plane/generation-reconciler' in text


def test_generation_reconciler_dispatches_exact_handoffs():
    text = _text("control-plane/generation-reconciler.mjs")
    for workflow in (
        "omega-hosted-recovery-failover.yml",
        "omega-candidate-evidence-root.yml",
        "omega-recovery-evidence-release-stager.yml",
        "omega-resilience-certifier.yml",
        "omega-canonical-android-signer.yml",
        "omega-android-runtime-coldstart.yml",
        "omega-final-release-promoter.yml",
        "omega-post-live-verification.yml",
        "omega-limited-distribution-release-adapter.yml",
        "omega-limited-distribution-public-live-certifier.yml",
    ):
        assert workflow in text
    assert 'recovery_run_id: recovery' in text
    assert 'evidence_run_id: evidence' in text
    assert 'signer_run_id: signer' in text
    assert 'post_live_run_id: postLive' in text


def test_generation_reconciler_serializes_one_reconcile_and_has_schedule_fallback():
    wf = _text(".github/workflows/omega-generation-reconciler.yml")
    assert "workflow_dispatch:" in wf
    assert 'cron: "4,14,24,34,44,54 * * * *"' in wf
    assert "group: omega-generation-reconciler" in wf
    assert "cancel-in-progress: false" in wf
    assert "actions: write" in wf
    assert "OMEGA_PRIVATE_TOKEN" in wf
    assert "OMEGA_CONTROL_TOKEN" in wf


def test_recovery_explicitly_dispatches_candidate_evidence_root():
    wf = _text(".github/workflows/omega-hosted-recovery-failover.yml")
    assert "actions: write" in wf
    assert "omega-candidate-evidence-root.yml" in wf
    assert 'recovery_run_id="$GITHUB_RUN_ID"' in wf


if __name__ == "__main__":
    test_generation_reconciler_is_level_triggered_and_reads_full_status_history()
    test_generation_reconciler_dispatches_exact_handoffs()
    test_generation_reconciler_serializes_one_reconcile_and_has_schedule_fallback()
    test_recovery_explicitly_dispatches_candidate_evidence_root()
    print("OMEGA_GENERATION_RECONCILER_CONTRACT_PASS")
