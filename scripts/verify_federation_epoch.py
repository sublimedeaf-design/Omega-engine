#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path

HEX40=re.compile(r"^[0-9a-f]{40}$")
HEX64=re.compile(r"^[0-9a-f]{64}$")
ALLOWED={"PASS","FAIL","BLOCKED","NOT_EXECUTED"}
EXPECTED={
"sublimedeaf-design/Omega-recovery":"control_recovery",
"sublimedeaf-design/Omega-agents":"agent_execution",
"sublimedeaf-design/Omega-validation":"independent_validation",
"sublimedeaf-design/Omega-release":"release_promotion",
}

def fail(msg):
    print("OMEGA_FEDERATION_V3_INVALID:"+msg,file=sys.stderr)
    return 2

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("epoch",nargs="?",default="federation/epochs/current.json")
    a=ap.parse_args()
    d=json.loads(Path(a.epoch).read_text(encoding="utf-8"))
    if d.get("schema_version")!=1 or d.get("federation_version")!=3:
        return fail("schema")
    if d.get("authority_repository")!="sublimedeaf-design/Omega-engine":
        return fail("authority")
    primary=d.get("primary") or {}
    if primary.get("repository")!="sublimedeaf-design/Omega-engines":
        return fail("primary_repo")
    if not HEX40.fullmatch(str(primary.get("source_sha") or "")):
        return fail("primary_sha")
    rows=d.get("peers") or []
    peers={str(x.get("repository")):x for x in rows if isinstance(x,dict)}
    if set(peers)!=set(EXPECTED):
        return fail("peer_set")
    for repo,role in EXPECTED.items():
        row=peers[repo]
        if row.get("role")!=role:
            return fail("peer_role:"+repo)
        if not HEX40.fullmatch(str(row.get("sha") or "")):
            return fail("peer_sha:"+repo)
        if row.get("state") not in ALLOWED:
            return fail("peer_state:"+repo)
    hf=d.get("hf") or {}
    for role in ("worker","qa"):
        row=hf.get(role) or {}
        if not HEX40.fullmatch(str(row.get("revision") or "")):
            return fail("hf_revision:"+role)
        if not HEX64.fullmatch(str(row.get("sha256") or "")):
            return fail("hf_sha256:"+role)
    inv=d.get("invariants") or {}
    required=(
        "one_external_federation_authority",
        "peer_repositories_must_not_pin_each_others_commit_sha",
        "source_sha_frozen_per_epoch",
        "pass_requires_all_peers_pass",
        "skipped_or_missing_is_never_pass",
    )
    if any(inv.get(k) is not True for k in required):
        return fail("invariants")

    release_epoch=d.get("release_epoch")
    if release_epoch is not None:
        if not isinstance(release_epoch,dict):
            return fail("release_epoch_type")
        epoch_id=str(release_epoch.get("id") or "")
        immutable_path=str(release_epoch.get("immutable_path") or "")
        contract_sha=str(release_epoch.get("control_contract_sha") or "")
        baseline=str(release_epoch.get("peer_contract_source_sha") or "")
        if not HEX64.fullmatch(epoch_id):
            return fail("release_epoch_id")
        if release_epoch.get("source_binding_mode")!="external_epoch":
            return fail("release_epoch_binding_mode")
        if not HEX40.fullmatch(contract_sha):
            return fail("release_epoch_control_sha")
        if not HEX40.fullmatch(baseline):
            return fail("release_epoch_peer_baseline")
        if release_epoch.get("new_deviation_requires_new_epoch") is not True:
            return fail("release_epoch_deviation_policy")
        if release_epoch.get("old_evidence_runs_are_never_mutated") is not True:
            return fail("release_epoch_evidence_policy")
        expected_prefix="federation/epochs/releases/"+str(primary["source_sha"])+"-"
        if not immutable_path.startswith(expected_prefix) or not immutable_path.endswith(".json"):
            return fail("release_epoch_immutable_path")
        rr=d.get("release_rollover") or {}
        if rr.get("release_epoch_id") not in (None,epoch_id):
            return fail("release_rollover_epoch_id")

    states=[x["state"] for x in rows]
    if d.get("state")=="PASS" and (
        primary.get("certification_state")!="PASS" or any(x!="PASS" for x in states)
    ):
        return fail("false_pass")
    print(json.dumps({
        "ok":True,
        "state":d.get("state"),
        "primary_sha":primary["source_sha"],
        "release_epoch_id":(release_epoch or {}).get("id"),
        "peer_states":{x["repository"]:x["state"] for x in rows},
    },sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
