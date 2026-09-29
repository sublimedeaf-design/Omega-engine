import base64
import html
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from urllib.parse import quote

import jwt
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import Flask, jsonify, redirect, request

logging.getLogger("werkzeug").disabled = True
app = Flask(__name__)

API = "https://api.github.com"
API_VERSION = "2026-03-10"
TARGET_OWNER = os.environ.get("TARGET_OWNER", "sublimedeaf-design")
TARGET_REPO = os.environ.get("TARGET_REPO", "Omega-engines")
BROKER_STATE = os.environ["BROKER_STATE"]
BROKER_NONCE = os.environ["BROKER_NONCE"]
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"].rstrip("/")
HANDOFF_PUBLIC_KEY = serialization.load_pem_public_key(
    base64.b64decode(os.environ["HANDOFF_PUBLIC_KEY_PEM_B64"])
)
APP_NAME = os.environ.get("APP_NAME", "omega-runner-authority")
DATA = {
    "stage": "ready_for_authorization",
    "app": None,
    "installation_id": None,
    "handoff": None,
    "runner_name": None,
    "error": None,
}

def _headers(token=None):
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "OMEGA-Runner-Authority-Broker/1.1",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def _app_jwt():
    info = DATA.get("app") or {}
    app_id = info.get("id")
    pem = info.get("pem")
    if not app_id or not pem:
        raise RuntimeError("APP_NOT_READY")
    now = int(time.time())
    return jwt.encode({"iat": now - 30, "exp": now + 540, "iss": str(app_id)}, pem, algorithm="RS256")

def _hybrid_encrypt(payload):
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    aad = b"omega-runner-authority-v1"
    ciphertext = AESGCM(key).encrypt(nonce, raw, aad)
    wrapped_key = HANDOFF_PUBLIC_KEY.encrypt(
        key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return {
        "schema": 1,
        "alg": "RSA-OAEP-SHA256+AES-256-GCM",
        "wrapped_key_b64": base64.b64encode(wrapped_key).decode(),
        "nonce_b64": base64.b64encode(nonce).decode(),
        "ciphertext_b64": base64.b64encode(ciphertext).decode(),
        "aad_b64": base64.b64encode(aad).decode(),
    }

def _revoke_installation():
    installation_id = DATA.get("installation_id")
    if not installation_id:
        return True
    try:
        r = requests.delete(
            f"{API}/app/installations/{installation_id}",
            headers=_headers(_app_jwt()),
            timeout=20,
        )
        return r.status_code in (202, 204, 404)
    except Exception:
        return False

def _download_runner(root):
    r = requests.get(
        f"{API}/repos/actions/runner/releases/latest",
        headers=_headers(),
        timeout=30,
    )
    r.raise_for_status()
    release = r.json()
    assets = [
        a for a in release.get("assets", [])
        if re.fullmatch(r"actions-runner-linux-x64-[0-9.]+\.tar\.gz", str(a.get("name") or ""))
    ]
    if len(assets) != 1:
        raise RuntimeError("RUNNER_ASSET_INVALID")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as fh:
        archive = pathlib.Path(fh.name)
    try:
        with requests.get(assets[0]["browser_download_url"], stream=True, timeout=120) as dl:
            dl.raise_for_status()
            with archive.open("wb") as out:
                for chunk in dl.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(root, filter="data")
    finally:
        archive.unlink(missing_ok=True)

def _runner_worker(registration_token):
    root = pathlib.Path("/tmp/omega-authority-runner")
    try:
        DATA["stage"] = "runner_provisioning"
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        _download_runner(root)

        runner_name = f"omega-render-authority-{int(time.time())}"
        DATA["runner_name"] = runner_name
        env = os.environ.copy()
        env["RUNNER_ALLOW_RUNASROOT"] = "1"

        subprocess.run(
            [
                str(root / "config.sh"),
                "--url", f"https://github.com/{TARGET_OWNER}/{TARGET_REPO}",
                "--token", registration_token,
                "--name", runner_name,
                "--labels", "omega-ci",
                "--unattended",
                "--ephemeral",
                "--replace",
            ],
            cwd=root,
            env=env,
            check=True,
            timeout=180,
        )
        registration_token = ""
        DATA["stage"] = "runner_online"

        proc = subprocess.Popen([str(root / "run.sh")], cwd=root, env=env)
        rc = proc.wait()
        DATA["stage"] = "runner_job_complete" if rc == 0 else "runner_job_failed"
        if rc != 0:
            DATA["error"] = f"RUNNER_EXIT_{rc}"
    except Exception as exc:
        registration_token = ""
        DATA["stage"] = "error"
        DATA["error"] = f"RUNNER_START_FAILED:{type(exc).__name__}"
    finally:
        revoked = _revoke_installation()
        DATA["installation_revoked"] = revoked
        try:
            shutil.rmtree(root)
        except Exception:
            pass

def _fail(code, exc):
    DATA["stage"] = "error"
    DATA["error"] = code
    return (
        "<!doctype html><html><body style='font-family:sans-serif;background:#07111f;color:#eef5ff;padding:32px'>"
        f"<h2 style='color:#ff7272'>OMEGA authority gestopt</h2><p>{html.escape(code)}</p>"
        "<p>Er is niets aan de Android signing-identiteit gewijzigd. Ga terug naar ChatGPT.</p></body></html>",
        500,
    )

@app.get("/")
def index():
    manifest = {
        "name": APP_NAME,
        "url": PUBLIC_BASE_URL + "/",
        "redirect_url": PUBLIC_BASE_URL + "/manifest",
        "setup_url": PUBLIC_BASE_URL + "/installed",
        "setup_on_update": False,
        "public": False,
        "description": "One-time OMEGA runner registration authority. Administration write is used only to mint one ephemeral repository runner token; no Android signing key is created or exported.",
        "hook_attributes": {"url": PUBLIC_BASE_URL + "/hook", "active": False},
        "default_permissions": {"administration": "write"},
        "default_events": [],
    }
    m = html.escape(json.dumps(manifest, separators=(",", ":")), quote=True)
    action = f"https://github.com/settings/apps/new?state={quote(BROKER_STATE)}"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OMEGA runner authority</title></head>
<body style="font-family:sans-serif;background:#07111f;color:#eef5ff;max-width:760px;margin:40px auto;padding:24px">
<h1>OMEGA · one-time runner authority</h1>
<p>Deze tijdelijke privé GitHub App vraagt alleen <b>Repository Administration: write</b> voor <b>{html.escape(TARGET_OWNER + "/" + TARGET_REPO)}</b>.
Dat recht wordt uitsluitend gebruikt om één GitHub self-hosted runner registration token te maken. De canonical Android signing key wordt niet vervangen of geëxporteerd.</p>
<p>Installeer de App alleen op <b>{html.escape(TARGET_REPO)}</b>. Na de eerste ephemeral runner-job wordt de installatie automatisch weer ingetrokken.</p>
<form method="post" action="{action}">
<input type="hidden" name="manifest" value="{m}">
<button style="font-size:18px;padding:14px 20px">GitHub-toestemming starten</button>
</form></body></html>"""

@app.post("/hook")
def hook():
    return ("", 204)

@app.get("/manifest")
def manifest_callback():
    try:
        if request.args.get("state") != BROKER_STATE:
            return _fail("STATE_MISMATCH", RuntimeError("state"))
        code = request.args.get("code", "")
        if not code:
            return _fail("MANIFEST_CODE_MISSING", RuntimeError("code"))
        r = requests.post(
            f"{API}/app-manifests/{quote(code)}/conversions",
            headers=_headers(),
            timeout=20,
        )
        if r.status_code != 201:
            return _fail(f"MANIFEST_CONVERSION_HTTP_{r.status_code}", RuntimeError(r.text[:200]))
        cfg = r.json()
        if not cfg.get("id") or not cfg.get("pem") or not cfg.get("slug"):
            return _fail("MANIFEST_CONVERSION_INCOMPLETE", RuntimeError("incomplete"))
        DATA["app"] = {"id": cfg["id"], "pem": cfg["pem"], "slug": cfg["slug"]}
        DATA["stage"] = "awaiting_installation"
        return redirect(f"https://github.com/apps/{quote(cfg['slug'])}/installations/new", code=302)
    except Exception as exc:
        return _fail("MANIFEST_CALLBACK_FAILED", exc)

@app.get("/installed")
def installed():
    try:
        installation_id = int(request.args.get("installation_id", "0"))
        if installation_id <= 0:
            return _fail("INSTALLATION_ID_MISSING", RuntimeError("installation"))
        jwt_token = _app_jwt()
        r = requests.get(f"{API}/app/installations/{installation_id}", headers=_headers(jwt_token), timeout=20)
        if r.status_code != 200:
            return _fail(f"INSTALLATION_LOOKUP_HTTP_{r.status_code}", RuntimeError(r.text[:200]))
        inst = r.json()
        login = ((inst.get("account") or {}).get("login") or "")
        admin_perm = ((inst.get("permissions") or {}).get("administration") or "")
        if login.lower() != TARGET_OWNER.lower():
            return _fail("INSTALLATION_ACCOUNT_MISMATCH", RuntimeError(login))
        if admin_perm != "write":
            return _fail("INSTALLATION_ADMIN_WRITE_MISSING", RuntimeError(admin_perm))

        token_resp = requests.post(
            f"{API}/app/installations/{installation_id}/access_tokens",
            headers=_headers(jwt_token),
            json={"repositories": [TARGET_REPO], "permissions": {"administration": "write"}},
            timeout=20,
        )
        if token_resp.status_code != 201:
            return _fail(f"INSTALLATION_TOKEN_HTTP_{token_resp.status_code}", RuntimeError(token_resp.text[:200]))
        installation_token = token_resp.json()["token"]

        reg = requests.post(
            f"{API}/repos/{TARGET_OWNER}/{TARGET_REPO}/actions/runners/registration-token",
            headers=_headers(installation_token),
            timeout=20,
        )
        if reg.status_code != 201:
            return _fail(f"RUNNER_REGISTRATION_HTTP_{reg.status_code}", RuntimeError(reg.text[:200]))
        regj = reg.json()
        payload = {
            "repository": f"{TARGET_OWNER}/{TARGET_REPO}",
            "registration_token": regj["token"],
            "expires_at": regj["expires_at"],
            "installation_id": installation_id,
            "app_id": DATA["app"]["id"],
        }
        DATA["handoff"] = _hybrid_encrypt(payload)
        DATA["installation_id"] = installation_id
        DATA["stage"] = "runner_starting"
        threading.Thread(
            target=_runner_worker,
            args=(regj["token"],),
            daemon=True,
        ).start()

        return """<!doctype html><html><body style='font-family:sans-serif;background:#07111f;color:#eef5ff;padding:32px'>
<h2 style='color:#4ee29a'>OMEGA authority geautoriseerd</h2>
<p>De tijdelijke authority start nu automatisch één ephemeral omega-ci runner. Het runner-token wordt niet getoond of opgeslagen. Ga terug naar ChatGPT.</p>
</body></html>"""
    except Exception as exc:
        return _fail("INSTALLATION_FLOW_FAILED", exc)

@app.get("/healthz")
def healthz():
    return jsonify({
        "ok": DATA["stage"] != "error",
        "stage": DATA["stage"],
        "runner_name": DATA.get("runner_name"),
        "installation_revoked": DATA.get("installation_revoked"),
        "error": DATA["error"],
    })

@app.get("/handoff/<nonce>")
def handoff(nonce):
    if nonce != BROKER_NONCE:
        return jsonify({"error": "not_found"}), 404
    if not DATA.get("handoff"):
        return jsonify({"ready": False, "stage": DATA.get("stage"), "error": DATA.get("error")}), 202
    return jsonify({"ready": True, "stage": DATA.get("stage"), "handoff": DATA["handoff"]})

@app.get("/cleanup/<nonce>")
def cleanup(nonce):
    if nonce != BROKER_NONCE:
        return jsonify({"error": "not_found"}), 404
    if _revoke_installation():
        DATA["stage"] = "installation_revoked"
        return jsonify({"ok": True, "stage": DATA["stage"]})
    return jsonify({"ok": False, "stage": "cleanup_failed"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
