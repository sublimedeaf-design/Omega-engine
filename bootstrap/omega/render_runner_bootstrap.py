#!/usr/bin/env python3
import base64, json, os, threading, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from nacl.public import PublicKey, SealedBox

API="https://api.github.com"
OWNER="sublimedeaf-design"
REPO="Omega-engines"
TARGET=f"{OWNER}/{REPO}"
REF="main"
TOKEN=os.environ.get("OMEGA_ADMIN_BOOTSTRAP_TOKEN","").strip()
PORT=int(os.environ.get("PORT","10000"))
STATE={"ok":False,"stage":"init","credential_material_recorded":False}

def api(method,path,payload=None):
    data=None if payload is None else json.dumps(payload,separators=(",",":")).encode()
    req=urllib.request.Request(API+path,method=method,data=data,headers={
        "Accept":"application/vnd.github+json",
        "Authorization":"Bearer "+TOKEN,
        "X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"OMEGA-Runner-Bootstrap/1",
        **({"Content-Type":"application/json"} if data is not None else {}),
    })
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            raw=r.read(1000000)
            return r.status,(json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw=e.read(200000)
        try: body=json.loads(raw or b"{}")
        except Exception: body={}
        return e.code,body

def seal(value,key_b64):
    pk=PublicKey(base64.b64decode(key_b64))
    return base64.b64encode(SealedBox(pk).encrypt(value.encode())).decode()

def set_codespaces_secret(name,value):
    code,key=api("GET",f"/repos/{OWNER}/{REPO}/codespaces/secrets/public-key")
    if code!=200: raise RuntimeError(f"codespaces_public_key_http_{code}")
    code,_=api("PUT",f"/repos/{OWNER}/{REPO}/codespaces/secrets/{name}",{
        "encrypted_value":seal(value,key["key"]),"key_id":key["key_id"]
    })
    if code not in (201,204): raise RuntimeError(f"codespaces_secret_put_http_{code}")

def delete_codespaces_secret(name):
    code,_=api("DELETE",f"/repos/{OWNER}/{REPO}/codespaces/secrets/{name}")
    return code

def repo_ref(row):
    gs=row.get("git_status") if isinstance(row.get("git_status"),dict) else {}
    return str(gs.get("ref") or row.get("ref") or "")

def discover():
    code,body=api("GET","/user/codespaces?per_page=100")
    if code!=200: raise RuntimeError(f"codespace_list_http_{code}")
    rows=[r for r in body.get("codespaces",[]) if r.get("repository",{}).get("full_name")==TARGET]
    exact=[r for r in rows if repo_ref(r) in {REF,f"refs/heads/{REF}"}]
    rows=exact or rows
    rows.sort(key=lambda r:str(r.get("last_used_at") or r.get("created_at") or ""),reverse=True)
    if not rows or not rows[0].get("name"): raise RuntimeError("codespace_not_found")
    return str(rows[0]["name"])

def detail(name):
    q=urllib.parse.quote(name,safe="")
    code,body=api("GET",f"/user/codespaces/{q}")
    return code,str(body.get("state") or "").lower()

def wait_state(name,accepted,timeout):
    deadline=time.time()+timeout
    last=""
    while time.time()<deadline:
        code,last=detail(name)
        if code==200 and last in accepted: return last
        time.sleep(5)
    raise RuntimeError(f"state_timeout_{last}")

def bootstrap():
    global STATE
    secret_name="OMEGA_RUNNER_REGISTRATION_TOKEN"
    if not TOKEN:
        STATE={"ok":False,"stage":"token_missing","credential_material_recorded":False}; return
    try:
        STATE={"ok":False,"stage":"mint_registration_token","credential_material_recorded":False}
        code,body=api("POST",f"/repos/{OWNER}/{REPO}/actions/runners/registration-token",{})
        if code!=201 or not body.get("token"): raise RuntimeError(f"runner_registration_http_{code}")
        registration=str(body["token"])

        STATE={"ok":False,"stage":"set_codespaces_secret","credential_material_recorded":False}
        set_codespaces_secret(secret_name,registration)
        registration=""

        name=discover()
        STATE={"ok":False,"stage":"restart_codespace","codespace_name":name,"credential_material_recorded":False}
        code,state=detail(name)
        if code!=200: raise RuntimeError(f"codespace_detail_http_{code}")
        q=urllib.parse.quote(name,safe="")
        if state in {"available","running"}:
            scode,_=api("POST",f"/user/codespaces/{q}/stop",{})
            if scode not in (200,202,304,409): raise RuntimeError(f"codespace_stop_http_{scode}")
            wait_state(name,{"shutdown","stopped","unavailable"},180)
        scode,_=api("POST",f"/user/codespaces/{q}/start",{})
        if scode not in (200,202,304,409): raise RuntimeError(f"codespace_start_http_{scode}")
        final=wait_state(name,{"available","running"},240)

        time.sleep(20)
        dcode=delete_codespaces_secret(secret_name)
        if dcode not in (204,404): raise RuntimeError(f"codespaces_secret_delete_http_{dcode}")

        STATE={"ok":True,"stage":"complete","codespace_name":name,"state":final,
               "temporary_secret_deleted":dcode==204,"credential_material_recorded":False}
    except Exception as e:
        try: delete_codespaces_secret(secret_name)
        except Exception: pass
        STATE={"ok":False,"stage":"failed","error":str(e)[:240],"credential_material_recorded":False}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body=(json.dumps(STATE,separators=(",",":"))+"\n").encode()
        self.send_response(200 if STATE.get("ok") else 503)
        self.send_header("content-type","application/json")
        self.send_header("cache-control","no-store")
        self.send_header("content-length",str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass

threading.Thread(target=bootstrap,daemon=True).start()
ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
