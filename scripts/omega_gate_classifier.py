#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

MARKERS = (
    ("EVIDENCE_ROOT_UPSTREAM_NOT_PASS", "UPSTREAM_PREREQUISITE", "BLOCKED", "upstream-proof", "recovery"),
    ("MAIN_PROTOCOL_NOT_EXECUTED", "NOT_EXECUTED", "NOT_EXECUTED", "protocol-generation", "recovery"),
    ("FEDERATION_PRIMARY_SOURCE_MISMATCH", "FEDERATION_IDENTITY", "FAIL", "federation", "federation"),
    ("FEDERATION_", "FEDERATION", "FAIL", "federation", "federation"),
    ("EVIDENCE_IDENTITY_MISMATCH", "EXECUTION_IDENTITY", "FAIL", "evidence", "evidence-root"),
    ("SOURCE_MISMATCH", "EXECUTION_IDENTITY", "FAIL", "identity", "recovery"),
    ("EXECUTION_ID_MISMATCH", "EXECUTION_IDENTITY", "FAIL", "identity", "recovery"),
    ("STALE_TRIGGER", "STALE_PROMOTION_SHA", "BLOCKED", "promotion-sha", "hosted-ci"),
    ("TRIGGER_NOT_CURRENT_BASE", "STALE_PROMOTION_SHA", "BLOCKED", "promotion-sha", "hosted-ci"),
    ("ARTIFACT_HASH_MISMATCH", "ARTIFACT_INTEGRITY", "FAIL", "artifact", "recovery"),
    ("digest-mismatch", "ARTIFACT_INTEGRITY", "FAIL", "artifact", "recovery"),
    ("LEDGER_INTEGRITY_FAILURE", "LEDGER_INTEGRITY", "FAIL", "ledger", "recovery"),
    ("EVIDENCE_MISSING", "ARTIFACT_MISSING", "FAIL", "artifact", "evidence-root"),
    ("LEDGER_MISSING", "ARTIFACT_MISSING", "FAIL", "artifact", "recovery"),
    ("NO_UNSIGNED_HANDOFF", "NOT_EXECUTED", "NOT_EXECUTED", "handoff", "release-stager"),
    ("NO_EVIDENCE_ARTIFACT", "NOT_EXECUTED", "NOT_EXECUTED", "handoff", "evidence-root"),
    ("INDEPENDENT_MODEL_COVERAGE_MISSING", "MODEL_COVERAGE", "BLOCKED", "model-evidence", "t24"),
    ("SIGNER_", "SIGNER_CONTINUITY", "BLOCKED", "signer", "signer"),
    ("APKSIGNER", "ANDROID_SIGNING", "FAIL", "android", "signer"),
    ("COLD_START", "ANDROID_RUNTIME", "FAIL", "android", "android-runtime"),
    ("ANDROID_RUNTIME", "ANDROID_RUNTIME", "FAIL", "android", "android-runtime"),
    ("FAILED tests/", "CODE_TEST", "FAIL", "code", "hosted-ci"),
    ("short test summary", "CODE_TEST", "FAIL", "code", "hosted-ci"),
)

POLICIES = {
    "NONE": (False, 1, "none"),
    "IN_PROGRESS": (False, 1, "wait"),
    "INFRA_PRESTART": (True, 2, "rerun_failed_jobs"),
    "SUCCESS_WITHOUT_PROOF": (False, 1, "reprove_same_gate"),
    "STALE_PROMOTION_SHA": (False, 1, "discard_stale_and_follow_canonical_sha"),
    "NOT_EXECUTED": (False, 1, "wait_for_upstream_proof"),
    "EXECUTION_IDENTITY": (False, 1, "rebuild_from_identity_boundary"),
    "ARTIFACT_INTEGRITY": (False, 1, "regenerate_artifact_from_reprove_boundary"),
    "ARTIFACT_MISSING": (False, 1, "reprove_upstream_artifact_producer"),
    "LEDGER_INTEGRITY": (False, 1, "rebuild_from_ledger_boundary"),
    "MODEL_COVERAGE": (False, 1, "return_no_bet_and_rebuild_model_evidence"),
    "SIGNER_CONTINUITY": (False, 1, "repair_signer_continuity_then_reprove"),
    "ANDROID_SIGNING": (False, 1, "repair_signing_then_reprove"),
    "ANDROID_RUNTIME": (False, 1, "repair_android_runtime_then_reprove"),
    "FEDERATION_IDENTITY": (False, 1, "repin_federation_epoch_then_reprove"),
    "FEDERATION": (False, 1, "repair_federation_then_reprove"),
    "CODE_TEST": (False, 1, "repair_code_then_reprove"),
    "UPSTREAM_PREREQUISITE": (False, 1, "reprove_from_upstream_boundary"),
    "UNKNOWN_FAILURE": (False, 1, "minimal_isolation_then_classify"),
    "UNKNOWN_STATE": (False, 1, "orchestrator_reconcile"),
}

def _jobs_all_prestep(jobs: Any) -> bool:
    if not isinstance(jobs, list) or not jobs:
        return False
    for job in jobs:
        if not isinstance(job, dict):
            return False
        steps = job.get("steps")
        if isinstance(steps, list) and steps:
            return False
    return True

def _diagnostic_sha256(log: str) -> str:
    interesting = []
    needles = ("OMEGA_", "FAILED ", "ERROR", "MISMATCH", "MISSING", "BLOCKED", "NOT_EXECUTED")
    for raw in log.splitlines():
        line = " ".join(raw.strip().split())
        if line and any(needle in line.upper() for needle in needles):
            interesting.append(line[:512])
    normalized = "\n".join(sorted(set(interesting))[:32])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def _decorate(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    failure_class = str(result["failure_class"])
    retryable, max_attempts, next_action = POLICIES.get(
        failure_class, (False, 1, "orchestrator_reconcile")
    )
    promotion_sha = str(payload.get("promotion_sha") or "").lower()
    execution_id = str(payload.get("omega_execution_id") or "").lower()
    evidence_root = str(payload.get("evidence_root") or "").lower()
    diagnostic_sha256 = _diagnostic_sha256(str(payload.get("log") or ""))
    if promotion_sha and not HEX40.fullmatch(promotion_sha):
        promotion_sha = ""
    if execution_id and not HEX64.fullmatch(execution_id):
        execution_id = ""
    if evidence_root and not HEX64.fullmatch(evidence_root):
        evidence_root = ""
    material = {
        "schema_version": 1,
        "promotion_sha": promotion_sha,
        "omega_execution_id": execution_id,
        "evidence_root": evidence_root,
        "gate": result["gate"],
        "failure_class": failure_class,
        "reprove_from": result["reprove_from"],
        "diagnostic_sha256": diagnostic_sha256,
    }
    canonical = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    result.update({
        "promotion_sha": promotion_sha,
        "omega_execution_id": execution_id,
        "evidence_root": evidence_root,
        "diagnostic_sha256": diagnostic_sha256,
        "incident_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "retryable": retryable,
        "max_attempts": max_attempts,
        "next_action": next_action,
    })
    return result

def classify(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "").lower()
    conclusion = str(payload.get("conclusion") or "").lower()
    proof_present = bool(payload.get("proof_present"))
    log = str(payload.get("log") or "")
    jobs = payload.get("jobs")
    gate = str(payload.get("gate") or "unknown")

    if status in {"queued", "pending", "waiting", "requested", "in_progress"}:
        result = {
            "gate": gate,
            "state": "PENDING",
            "failure_class": "IN_PROGRESS",
            "repair_scope": "none",
            "reprove_from": gate,
        }
        return _decorate(payload, result)

    if status == "completed" and conclusion == "success" and proof_present:
        result = {
            "gate": gate,
            "state": "PASS",
            "failure_class": "NONE",
            "repair_scope": "none",
            "reprove_from": "none",
        }
        return _decorate(payload, result)

    if status == "completed" and conclusion == "success" and not proof_present:
        result = {
            "gate": gate,
            "state": "NOT_EXECUTED",
            "failure_class": "SUCCESS_WITHOUT_PROOF",
            "repair_scope": "orchestration",
            "reprove_from": gate,
        }
        return _decorate(payload, result)

    if conclusion in {"failure", "cancelled", "skipped"} and _jobs_all_prestep(jobs):
        result = {
            "gate": gate,
            "state": "BLOCKED",
            "failure_class": "INFRA_PRESTART",
            "repair_scope": "runner-or-hosted-fallback",
            "reprove_from": gate,
        }
        return _decorate(payload, result)

    upper = log.upper()
    for marker, cls, state, scope, reprove in MARKERS:
        if marker.upper() in upper:
            result = {
                "gate": gate,
                "state": state,
                "failure_class": cls,
                "repair_scope": scope,
                "reprove_from": reprove,
            }
            return _decorate(payload, result)

    if conclusion in {"failure", "cancelled", "skipped"}:
        result = {
            "gate": gate,
            "state": "FAIL",
            "failure_class": "UNKNOWN_FAILURE",
            "repair_scope": "minimal-isolation",
            "reprove_from": gate,
        }
        return _decorate(payload, result)

    result = {
        "gate": gate,
        "state": "NOT_EXECUTED",
        "failure_class": "UNKNOWN_STATE",
        "repair_scope": "orchestration",
        "reprove_from": gate,
    }
    return _decorate(payload, result)

def _self_test() -> None:
    cases = [
        ({"status": "completed", "conclusion": "failure", "jobs": [{"steps": []}], "gate": "ci"}, "INFRA_PRESTART"),
        ({"status": "completed", "conclusion": "failure", "jobs": [{"steps": [{"name": "x"}]}], "log": "OMEGA_RELEASE_STAGE_EVIDENCE_IDENTITY_MISMATCH:latest-24h.json"}, "EXECUTION_IDENTITY"),
        ({"status": "completed", "conclusion": "success", "proof_present": False}, "SUCCESS_WITHOUT_PROOF"),
        ({"status": "completed", "conclusion": "success", "proof_present": True}, "NONE"),
        ({"status": "completed", "conclusion": "failure", "log": "FAILED tests/test_x.py::test_y\nshort test summary"}, "CODE_TEST"),
        ({"status": "completed", "conclusion": "failure", "log": "OMEGA_CANONICAL_SIGNER_BLOCKED_AUTORETRY"}, "SIGNER_CONTINUITY"),
    ]
    for payload, expected in cases:
        got = classify(payload)
        if got["failure_class"] != expected:
            raise SystemExit(f"SELF_TEST_FAIL expected={expected} got={got['failure_class']} payload={payload}")
        if not HEX64.fullmatch(got["incident_id"]):
            raise SystemExit("SELF_TEST_FAIL incident_id")
    infra = classify({
        "status": "completed",
        "conclusion": "failure",
        "jobs": [{"steps": []}],
        "gate": "hosted-ci",
        "promotion_sha": "a" * 40,
    })
    if not infra["retryable"] or infra["max_attempts"] != 2 or infra["next_action"] != "rerun_failed_jobs":
        raise SystemExit("SELF_TEST_FAIL infra_retry_policy")
    code = classify({
        "status": "completed",
        "conclusion": "failure",
        "jobs": [{"steps": [{"name": "pytest"}]}],
        "log": "FAILED tests/test_x.py::test_y",
        "gate": "hosted-ci",
        "promotion_sha": "a" * 40,
    })
    if code["retryable"]:
        raise SystemExit("SELF_TEST_FAIL code_must_not_blind_retry")
    same = classify({
        "status": "completed",
        "conclusion": "failure",
        "jobs": [{"steps": []}],
        "gate": "hosted-ci",
        "promotion_sha": "a" * 40,
    })
    changed = classify({
        "status": "completed",
        "conclusion": "failure",
        "jobs": [{"steps": []}],
        "gate": "hosted-ci",
        "promotion_sha": "b" * 40,
    })
    if infra["incident_id"] != same["incident_id"] or infra["incident_id"] == changed["incident_id"]:
        raise SystemExit("SELF_TEST_FAIL incident_dedup_identity")
    diag_a = classify({
        "status": "completed",
        "conclusion": "failure",
        "jobs": [{"steps": [{"name": "pytest"}]}],
        "log": "FAILED tests/test_alpha.py::test_a",
        "gate": "hosted-ci",
        "promotion_sha": "a" * 40,
    })
    diag_b = classify({
        "status": "completed",
        "conclusion": "failure",
        "jobs": [{"steps": [{"name": "pytest"}]}],
        "log": "FAILED tests/test_beta.py::test_b",
        "gate": "hosted-ci",
        "promotion_sha": "a" * 40,
    })
    if diag_a["incident_id"] == diag_b["incident_id"]:
        raise SystemExit("SELF_TEST_FAIL distinct_diagnostics_must_not_collide")
    print("OMEGA_GATE_CLASSIFIER_SELF_TEST_PASS")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--input", default="-")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
        return 0
    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("JSON_OBJECT_REQUIRED")
    print(json.dumps(classify(payload), sort_keys=True, separators=(",", ":")))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
