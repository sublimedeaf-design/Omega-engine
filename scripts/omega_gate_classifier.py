#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

MARKERS = (
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

def classify(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "").lower()
    conclusion = str(payload.get("conclusion") or "").lower()
    proof_present = bool(payload.get("proof_present"))
    log = str(payload.get("log") or "")
    jobs = payload.get("jobs")
    gate = str(payload.get("gate") or "unknown")

    if status in {"queued", "pending", "waiting", "requested", "in_progress"}:
        return {
            "gate": gate,
            "state": "PENDING",
            "failure_class": "IN_PROGRESS",
            "repair_scope": "none",
            "reprove_from": gate,
        }

    if status == "completed" and conclusion == "success" and proof_present:
        return {
            "gate": gate,
            "state": "PASS",
            "failure_class": "NONE",
            "repair_scope": "none",
            "reprove_from": "none",
        }

    if status == "completed" and conclusion == "success" and not proof_present:
        return {
            "gate": gate,
            "state": "NOT_EXECUTED",
            "failure_class": "SUCCESS_WITHOUT_PROOF",
            "repair_scope": "orchestration",
            "reprove_from": gate,
        }

    if conclusion in {"failure", "cancelled", "skipped"} and _jobs_all_prestep(jobs):
        return {
            "gate": gate,
            "state": "BLOCKED",
            "failure_class": "INFRA_PRESTART",
            "repair_scope": "runner-or-hosted-fallback",
            "reprove_from": gate,
        }

    upper = log.upper()
    for marker, cls, state, scope, reprove in MARKERS:
        if marker.upper() in upper:
            return {
                "gate": gate,
                "state": state,
                "failure_class": cls,
                "repair_scope": scope,
                "reprove_from": reprove,
            }

    if conclusion in {"failure", "cancelled", "skipped"}:
        return {
            "gate": gate,
            "state": "FAIL",
            "failure_class": "UNKNOWN_FAILURE",
            "repair_scope": "minimal-isolation",
            "reprove_from": gate,
        }

    return {
        "gate": gate,
        "state": "NOT_EXECUTED",
        "failure_class": "UNKNOWN_STATE",
        "repair_scope": "orchestration",
        "reprove_from": gate,
    }

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
        got = classify(payload)["failure_class"]
        if got != expected:
            raise SystemExit(f"SELF_TEST_FAIL expected={expected} got={got} payload={payload}")
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
