#!/usr/bin/env python3
"""Public bootstrap helper: discover and wake the existing private OMEGA Codespace."""
from __future__ import annotations
import json, os, sys, time, urllib.error, urllib.parse, urllib.request

API="https://api.github.com"
OWNER="sublimedeaf-design"
REPO="Omega-engines"
REF="main"
TOKEN=os.environ.get("OMEGA_CODESPACE_LIFECYCLE_TOKEN","").strip()
FORCE_RESTART=os.environ.get("OMEGA_FORCE_RESTART","").strip()=="1"

def request(method,path):
    req=urllib.request.Request(
        API+path,method=method,data=(b"" if method=="POST" else None),
        headers={
            "Accept":"application/vnd.github+json",
            "Authorization":f"Bearer {TOKEN}",
            "X-GitHub-Api-Version":"2022-11-28",
            "User-Agent":"OMEGA-Public-Bootstrap/1",
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

def main():
    if not TOKEN:
        print("OMEGA_BOOTSTRAP_SECRET_NOT_CONFIGURED")
        return 0
    code,body=request("GET","/user/codespaces?per_page=100")
    if code != 200:
        print(json.dumps({"ok":False,"stage":"list","http_status":code}))
        return 2
    owned=[r for r in body.get("codespaces",[]) if r.get("repository",{}).get("full_name")==f"{OWNER}/{REPO}"]
    exact=[r for r in owned if ref_of(r) in {REF,f"refs/heads/{REF}"}]
    candidates=exact or owned
    candidates.sort(key=lambda r:str(r.get("last_used_at") or r.get("created_at") or ""),reverse=True)
    if not candidates or not candidates[0].get("name"):
        print(json.dumps({"ok":False,"stage":"discover","error":"CODESPACE_NOT_FOUND"}))
        return 3
    name=str(candidates[0]["name"])
    q=urllib.parse.quote(name,safe="")
    dcode,detail=request("GET",f"/user/codespaces/{q}")
    state=str(detail.get("state") or "").lower()
    if dcode != 200:
        print(json.dumps({"ok":False,"stage":"detail","http_status":dcode}))
        return 4
    start_http=None
    stop_http=None
    if FORCE_RESTART and state in {"available","running"}:
        stop_http,_=request("POST",f"/user/codespaces/{q}/stop")
        if stop_http != 200:
            print(json.dumps({"ok":False,"stage":"stop","http_status":stop_http}))
            return 7
        deadline=time.time()+120
        while time.time()<deadline:
            time.sleep(5)
            scode,sbody=request("GET",f"/user/codespaces/{q}")
            state=str(sbody.get("state") or "").lower()
            if scode==200 and state not in {"available","running","starting"}:
                break
        else:
            print(json.dumps({"ok":False,"stage":"stop_verify","state":state}))
            return 6

    if state not in {"available","running"}:
        start_http,_=request("POST",f"/user/codespaces/{q}/start")
        if start_http not in {200,202,304,409}:
            print(json.dumps({"ok":False,"stage":"start","http_status":start_http}))
            return 5
        deadline=time.time()+120
        while time.time()<deadline:
            time.sleep(5)
            vcode,verify=request("GET",f"/user/codespaces/{q}")
            state=str(verify.get("state") or "").lower()
            if vcode==200 and state in {"available","running"}:
                break
        else:
            print(json.dumps({"ok":False,"stage":"verify","start_http":start_http,"state":state}))
            return 8
    print(json.dumps({
        "ok":True,"repository":f"{OWNER}/{REPO}","ref":REF,
        "codespace_name":name,"state":state,"stop_http":stop_http,"start_http":start_http,
        "credential_material_recorded":False,
    },sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
