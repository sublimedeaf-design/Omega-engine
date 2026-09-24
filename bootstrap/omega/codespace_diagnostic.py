#!/usr/bin/env python3
from __future__ import annotations
import json, os, urllib.error, urllib.parse, urllib.request

API="https://api.github.com"
TOKEN=os.environ.get("OMEGA_BOOTSTRAP_TOKEN","").strip()
NAME="zany-invention-vpr6jxpxppv4hpvp6"
OWNER="sublimedeaf-design"
REPO="Omega-engines"

def req(method,path):
    request=urllib.request.Request(
        API+path,
        method=method,
        data=(b"" if method=="POST" else None),
        headers={
            "Accept":"application/vnd.github+json",
            "Authorization":f"Bearer {TOKEN}",
            "X-GitHub-Api-Version":"2026-03-10",
            "User-Agent":"OMEGA-Codespace-Diagnostic/1",
        },
    )
    try:
        with urllib.request.urlopen(request,timeout=30) as r:
            raw=r.read(200_000)
            try: body=json.loads(raw or b"{}")
            except Exception: body={}
            return r.status,body
    except urllib.error.HTTPError as exc:
        raw=exc.read(200_000)
        try: body=json.loads(raw or b"{}")
        except Exception: body={"message":"non-json github error"}
        return exc.code,body

def scrub(body):
    if not isinstance(body,dict):
        return {}
    keep={}
    for k in ("message","accepted","state","name","web_url","documentation_url","status"):
        if k in body:
            keep[k]=body[k]
    return keep

def main():
    if not TOKEN:
        print(json.dumps({"ok":False,"error":"TOKEN_MISSING"}))
        return 0

    detail_http,detail=req("GET",f"/user/codespaces/{urllib.parse.quote(NAME,safe='')}")
    perm_path=(
        f"/repos/{OWNER}/{REPO}/codespaces/permissions_check"
        "?ref=heads%2Fmain&devcontainer_path=.devcontainer%2Fdevcontainer.json"
    )
    perm_http,perm=req("GET",perm_path)

    start_http=None
    start={}
    state=str(detail.get("state") or "").lower() if isinstance(detail,dict) else ""
    if detail_http==200 and state in {"shutdown","stopped"}:
        start_http,start=req("POST",f"/user/codespaces/{urllib.parse.quote(NAME,safe='')}/start")

    print(json.dumps({
        "detail_http":detail_http,
        "detail":scrub(detail),
        "permissions_check_http":perm_http,
        "permissions_check":scrub(perm),
        "start_attempted":start_http is not None,
        "start_http":start_http,
        "start":scrub(start),
        "credential_material_recorded":False,
    },sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
