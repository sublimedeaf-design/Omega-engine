#!/usr/bin/env python3
from __future__ import annotations
import base64, json, os, re, urllib.error, urllib.parse, urllib.request

API="https://api.github.com"
TOKEN=os.environ["OMEGA_BOOTSTRAP_TOKEN"].strip()
TARGET=os.environ["OMEGA_TARGET_SOURCE_SHA"].strip()
SOURCE_REF=os.environ["OMEGA_TARGET_SOURCE_REF"].strip()
CORE="sublimedeaf-design/Omega-engines"
CONTROL="sublimedeaf-design/Omega-engine"
HEX40=re.compile(r"^[0-9a-f]{40}$")
RELEASE_REF=re.compile(r"^release/[A-Za-z0-9._/-]+$")
PEERS=[
    ("sublimedeaf-design/Omega-recovery","control_recovery"),
    ("sublimedeaf-design/Omega-agents","agent_execution"),
    ("sublimedeaf-design/Omega-validation","independent_validation"),
    ("sublimedeaf-design/Omega-release","release_promotion"),
]
FILES=["OMEGA_INTEGRATION_CONTRACT.json","OMEGA_MESH.json",
       *[f"agents/agent-{i:02d}.json" for i in range(1,7)],"state/source-pin.json"]

def api(method,path,payload=None):
    data=None if payload is None else json.dumps(payload,separators=(",",":")).encode()
    req=urllib.request.Request(
        API+path, data=data, method=method,
        headers={
            "Authorization":f"Bearer {TOKEN}",
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28",
            "User-Agent":"OMEGA-transactional-federation-rollover",
            **({"Content-Type":"application/json"} if data is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            raw=r.read(8*1024*1024+1)
            if len(raw)>8*1024*1024: raise SystemExit("OMEGA_FEDERATION_API_RESPONSE_TOO_LARGE")
            return json.loads(raw or b"{}")
    except urllib.error.HTTPError as exc:
        detail=exc.read(65536).decode("utf-8","replace")
        raise SystemExit(f"OMEGA_FEDERATION_GITHUB_HTTP_{exc.code}:{path}:{detail[:1000]}") from exc

def content(repo,path,ref):
    q=urllib.parse.quote(ref,safe="")
    row=api("GET",f"/repos/{repo}/contents/{path}?ref={q}")
    raw=base64.b64decode(str(row["content"]).replace("\n",""),validate=True)
    return row,raw

def replace_exact(obj,old,new):
    if isinstance(obj,str): return new if obj==old else obj
    if isinstance(obj,list): return [replace_exact(x,old,new) for x in obj]
    if isinstance(obj,dict): return {k:replace_exact(v,old,new) for k,v in obj.items()}
    return obj

def latest_main(repo):
    return api("GET",f"/repos/{repo}/git/ref/heads/main")["object"]["sha"]

def update_peer(repo,expected_source,expected_commit):
    base=latest_main(repo)
    if base!=expected_commit:
        raise SystemExit(f"OMEGA_PEER_MAIN_DRIFT:{repo}:{base}!={expected_commit}")
    rows={}
    docs={}
    for path in FILES:
        meta,raw=content(repo,path,base)
        rows[path]=meta
        docs[path]=json.loads(raw)
    old=str(docs["state/source-pin.json"].get("source_sha") or "")
    if not HEX40.fullmatch(old): raise SystemExit(f"OMEGA_PEER_SOURCE_INVALID:{repo}:{old}")
    contract=str((docs["OMEGA_INTEGRATION_CONTRACT.json"].get("source") or {}).get("sha") or "")
    mesh=str(docs["OMEGA_MESH.json"].get("source_pin") or "")
    agents={str(docs[f"agents/agent-{i:02d}.json"].get("source_sha") or "") for i in range(1,7)}
    if contract!=old or mesh!=old or agents!={old}:
        raise SystemExit(f"OMEGA_PEER_PRE_ROLLOVER_SPLIT:{repo}")
    if old==TARGET:
        return base
    if old!=expected_source:
        raise SystemExit(f"OMEGA_PEER_UNEXPECTED_PREVIOUS_SOURCE:{repo}:{old}!={expected_source}")
    tree_entries=[]
    for path in FILES:
        newdoc=replace_exact(docs[path],old,TARGET)
        raw=(json.dumps(newdoc,indent=2,ensure_ascii=False)+"\n").encode()
        blob=api("POST",f"/repos/{repo}/git/blobs",{"content":raw.decode(),"encoding":"utf-8"})["sha"]
        tree_entries.append({"path":path,"mode":"100644","type":"blob","sha":blob})
    base_tree=api("GET",f"/repos/{repo}/git/commits/{base}")["tree"]["sha"]
    tree=api("POST",f"/repos/{repo}/git/trees",{"base_tree":base_tree,"tree":tree_entries})["sha"]
    commit=api("POST",f"/repos/{repo}/git/commits",{
        "message":f"Federation v3: atomically align release epoch to {TARGET[:12]}",
        "tree":tree,"parents":[base],
    })["sha"]
    api("PATCH",f"/repos/{repo}/git/refs/heads/main",{"sha":commit,"force":False})
    return commit

if not HEX40.fullmatch(TARGET): raise SystemExit("OMEGA_RELEASE_FEDERATION_TARGET_INVALID")
if not RELEASE_REF.fullmatch(SOURCE_REF) or ".." in SOURCE_REF or SOURCE_REF.startswith("/") or SOURCE_REF.startswith("-"):
    raise SystemExit("OMEGA_RELEASE_FEDERATION_REF_INVALID")
tip=api("GET",f"/repos/{CORE}/commits/{urllib.parse.quote(SOURCE_REF,safe='')}")["sha"]
if tip!=TARGET: raise SystemExit(f"OMEGA_RELEASE_FEDERATION_REF_MOVED:{tip}!={TARGET}")

status=api("GET",f"/repos/{CORE}/commits/{TARGET}/status?per_page=100")
latest={}
for row in status.get("statuses",[]):
    ctx=str(row.get("context") or "")
    if ctx and ctx not in latest: latest[ctx]=row
required={
    "omega/hosted-ci/python311","omega/hosted-ci/python313","omega/hosted-ci/python314",
    "omega/hosted-ci/storage","omega/hosted-governance","omega/hosted-android",
    "omega/release-evidence-staged","omega/android-release-unsigned",
}
bad=sorted(x for x in required if (latest.get(x) or {}).get("state")!="success")
if bad: raise SystemExit("OMEGA_RELEASE_FEDERATION_PREREQUISITE_NOT_PASS:"+",".join(bad))

meta,raw=content(CONTROL,"federation/epochs/current.json","main")
epoch=json.loads(raw)
if epoch.get("state")!="PASS" or (epoch.get("primary") or {}).get("certification_state")!="PASS":
    raise SystemExit("OMEGA_FEDERATION_AUTHORITY_NOT_PASS")
current_source=str((epoch.get("primary") or {}).get("source_sha") or "")
if not HEX40.fullmatch(current_source):
    raise SystemExit("OMEGA_FEDERATION_AUTHORITY_SOURCE_INVALID")
authority_peers={str(row.get("repository") or ""):row for row in (epoch.get("peers") or [])}
if set(authority_peers)!={repo for repo,_ in PEERS}:
    raise SystemExit("OMEGA_FEDERATION_AUTHORITY_PEER_SET_MISMATCH")
if current_source==TARGET:
    print(json.dumps({"ok":True,"already_current":True,"source_sha":TARGET,"source_ref":SOURCE_REF},sort_keys=True))
    raise SystemExit(0)

peer_shas={}
for repo,role in PEERS:
    row=authority_peers[repo]
    expected_commit=str(row.get("sha") or "")
    if row.get("state")!="PASS" or row.get("contract_state")!="PASS" or not HEX40.fullmatch(expected_commit):
        raise SystemExit(f"OMEGA_FEDERATION_AUTHORITY_PEER_NOT_PASS:{repo}")
    peer_shas[repo]=update_peer(repo,current_source,expected_commit)
epoch["state"]="NOT_EXECUTED"
epoch["blockers"]=["external exact-SHA peer validation pending"]
epoch["primary"]["source_sha"]=TARGET
epoch["primary"]["source_ref"]=SOURCE_REF
epoch["primary"]["certification_state"]="NOT_EXECUTED"
epoch["release_rollover"]={"source_ref":SOURCE_REF,"stage":"PEERS_ALIGNED_PENDING_EXTERNAL_VALIDATION"}
by_repo={x["repository"]:x for x in epoch["peers"]}
for repo,role in PEERS:
    row=by_repo[repo]
    row["sha"]=peer_shas[repo]
    row["role"]=role
    row["state"]="NOT_EXECUTED"
    row["contract_state"]="NOT_EXECUTED"
    row["reason"]="external exact-SHA federation v3 peer validation pending"
body=(json.dumps(epoch,indent=2,ensure_ascii=False)+"\n").encode()
api("PUT",f"/repos/{CONTROL}/contents/federation/epochs/current.json",{
    "message":f"Federation v3: stage release epoch {TARGET[:12]} for external validation",
    "content":base64.b64encode(body).decode(),
    "sha":meta["sha"],"branch":"main",
})
print(json.dumps({"ok":True,"source_sha":TARGET,"source_ref":SOURCE_REF,"peers":peer_shas},sort_keys=True))
