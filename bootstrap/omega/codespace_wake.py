#!/usr/bin/env python3
"""Public bootstrap helper: discover and converge the existing OMEGA Codespace to available."""
from __future__ import annotations
import json, os, sys, time, urllib.error, urllib.parse, urllib.request

API="https://api.github.com"
OWNER="sublimedeaf-design"
REPO="Omega-engines"
REF="main"
TOKEN=os.environ.get("OMEGA_CODESPACE_LIFECYCLE_TOKEN","").strip()
FORCE_RESTART=os.environ.get("OMEGA_FORCE_RESTART","").strip()=="1"
POLL_SECONDS=5
CONVERGE_SECONDS=240
AVAILABLE={"available","running"}
STOP_TRANSITION={"shuttingdown","stopping"}
START_TRANSITION={"starting","rebuilding","updating"}

def request(method,path):
    req=urllib.request.Request(
        API+path,method=method,data=(b"" if method=="POST" else None),
        headers={
            "Accept":"application/vnd.github+json",
            "Authorization":f"Bearer {TOKEN}",
            "X-GitHub-Api-Version":"2022-11-28",
            "User-Agent":"OMEGA-Public-Bootstrap/2",
        },
    )
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read(1_000_000)
            return r.status,json.loads(raw or b"{}")
    except urllib.error.HTTPError as exc:
        raw=exc.read(200_000)
        try: body=json.loads(raw or b"{}")
        except Exception: body={}
        return exc.code,body

def ref_of(row):
    gs=row.get("git_status") if isinstance(row.get("git_status"),dict) else {}
    return str(gs.get("ref") or row.get("ref") or "")

def discover():
    code,body=request("GET","/user/codespaces?per_page=100")
    if code != 200:
        return code,None
    owned=[r for r in body.get("codespaces",[]) if r.get("repository",{}).get("full_name")==f"{OWNER}/{REPO}"]
    exact=[r for r in owned if ref_of(r) in {REF,f"refs/heads/{REF}"}]
    candidates=exact or owned
    candidates.sort(key=lambda r:str(r.get("last_used_at") or r.get("created_at") or ""),reverse=True)
    return 200,(candidates[0] if candidates else None)

def detail(q):
    code,body=request("GET",f"/user/codespaces/{q}")
    return code,str(body.get("state") or "").lower()

def converge_available(q, initial_state):
    deadline=time.time()+CONVERGE_SECONDS
    state=initial_state
    start_attempts=[]
    while time.time()<deadline:
        if state in AVAILABLE:
            return True,state,start_attempts

        if state not in STOP_TRANSITION and state not in START_TRANSITION:
            http,_=request("POST",f"/user/codespaces/{q}/start")
            start_attempts.append(http)
            if http not in {200,202,304,409}:
                return False,state,start_attempts

        time.sleep(POLL_SECONDS)
        code,state=detail(q)
        if code != 200:
            return False,f"http_{code}",start_attempts

    return False,state,start_attempts

def main():
    if not TOKEN:
        print("OMEGA_BOOTSTRAP_SECRET_NOT_CONFIGURED")
        return 0

    code,target=discover()
    if code != 200:
        print(json.dumps({"ok":False,"stage":"list","http_status":code}))
        return 2
    if not target or not target.get("name"):
        print(json.dumps({"ok":False,"stage":"discover","error":"CODESPACE_NOT_FOUND"}))
        return 3

    name=str(target["name"])
    q=urllib.parse.quote(name,safe="")
    dcode,state=detail(q)
    if dcode != 200:
        print(json.dumps({"ok":False,"stage":"detail","http_status":dcode}))
        return 4

    stop_http=None
    if FORCE_RESTART and state in AVAILABLE:
        stop_http,_=request("POST",f"/user/codespaces/{q}/stop")
        if stop_http not in {200,202,409}:
            print(json.dumps({"ok":False,"stage":"stop","http_status":stop_http}))
            return 7
        # Do not call /start while GitHub is still shutting down.
        deadline=time.time()+CONVERGE_SECONDS
        while time.time()<deadline:
            time.sleep(POLL_SECONDS)
            scode,state=detail(q)
            if scode != 200:
                print(json.dumps({"ok":False,"stage":"stop_verify","http_status":scode}))
                return 6
            if state not in AVAILABLE and state not in STOP_TRANSITION:
                break
        else:
            print(json.dumps({"ok":False,"stage":"stop_verify","state":state}))
            return 6

    ok,state,start_attempts=converge_available(q,state)
    payload={
        "ok":ok,
        "repository":f"{OWNER}/{REPO}",
        "ref":REF,
        "codespace_name":name,
        "state":state,
        "stop_http":stop_http,
        "start_attempts":start_attempts,
        "credential_material_recorded":False,
    }
    print(json.dumps(payload,sort_keys=True))
    return 0 if ok else 8

if __name__=="__main__":
    raise SystemExit(main())
