from pathlib import Path


def test_federation_peer_bridge_treats_validation_trigger_as_state_only():
    workflow = Path(".github/workflows/omega-federation-v3-peer-bridge.yml").read_text(encoding="utf-8")
    assert 'python3 scripts/control_state_policy.py "$path"' in workflow
    assert "federation/epochs/*|bootstrap/omega/*" not in workflow
    assert "OMEGA_FEDERATION_CONTROL_DRIFT_REQUIRES_NEW_EPOCH" in workflow
