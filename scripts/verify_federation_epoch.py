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
    print("OMEGA_FEDERATION_V3_INVALID:"+msg,file=sys.stderr); return 2
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("epoch",nargs="?",default="federation/epochs/current.json"); a=ap.parse_args()
    d=json.loads(Path(a.epoch).read_text(encoding="utf-8"))
    if d.get("schema_version")!=1 or d.get("federation_version")!=3:return fail("schema")
    if d.get("authority_repository")!="sublimedeaf-design/Omega-engine":return fail("authority")
    primary=d.get("primary") or {}
    if primary.get("repository")!="sublimedeaf-design/Omega-engines":return fail("primary_repo")
    if not HEX40.fullmatch(str(primary.get("source_sha") or "")):return fail("primary_sha")
    rows=d.get("peers") or []
    peers={str(x.get("repository")):x for x in rows if isinstance(x,dict)}
    if set(peers)!=set(EXPECTED):return fail("peer_set")
    for repo,role in EXPECTED.items():
        row=peers[repo]
        if row.get("role")!=role:return fail("peer_role:"+repo)
        if not HEX40.fullmatch(str(row.get("sha") or "")):return fail("peer_sha:"+repo)
        if row.get("state") not in ALLOWED:return fail("peer_state:"+repo)
    hf=d.get("hf") or {}
    for role in ("worker","qa"):
        row=hf.get(role) or {}
        if not HEX40.fullmatch(str(row.get("revision") or "")):return fail("hf_revision:"+role)
        if not HEX64.fullmatch(str(row.get("sha256") or "")):return fail("hf_sha256:"+role)
    inv=d.get("invariants") or {}
    required=("one_external_federation_authority","peer_repositories_must_not_pin_each_others_commit_sha","source_sha_frozen_per_epoch","pass_requires_all_peers_pass","skipped_or_missing_is_never_pass")
    if any(inv.get(k) is not True for k in required):return fail("invariants")
    states=[x["state"] for x in rows]
    if d.get("state")=="PASS" and (primary.get("certification_state")!="PASS" or any(x!="PASS" for x in states)):
        return fail("false_pass")
    print(json.dumps({"ok":True,"state":d.get("state"),"primary_sha":primary["source_sha"],"peer_states":{x["repository"]:x["state"] for x in rows}},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
