import base64
import hashlib
import hmac
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
APP_NAME = os.environ.get("APP_NAME", "omega-9980fbd6-runner-r2")
AUTHORITY_MASTER_KEY = base64.b64decode(os.environ["AUTHORITY_MASTER_KEY_B64"])
if len(AUTHORITY_MASTER_KEY) != 32:
    raise RuntimeError("AUTHORITY_MASTER_KEY_INVALID")
AUTHORITY_STATE_URL = os.environ.get(
    "AUTHORITY_STATE_URL",
    "https://raw.githubusercontent.com/sublimedeaf-design/Omega-engine/"
    "automation/runner-authority-28a3e81/deploy/render/runner-authority-state.enc.json",
)

DATA = {
    "stage": "ready_for_authorization",
    "app": None,
    "installation_id": None,
    "webhook_secret": None,
    "authority_export": None,
    "handoff": None,
    "runner_name": None,
    "runner_active": False,
    "last_runner_result": None,
    "error": None,
}
LOCK = threading.Lock()


def _headers(token=None):
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "OMEGA-Runner-Authority-Broker/2.0",
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
    return jwt.encode(
        {"iat": now - 30, "exp": now + 540, "iss": str(app_id)},
        pem,
        algorithm="RS256",
    )


def _installation_token():
    installation_id = DATA.get("installation_id")
    if not installation_id:
        raise RuntimeError("INSTALLATION_NOT_READY")
    r = requests.post(
        f"{API}/app/installations/{installation_id}/access_tokens",
        headers=_headers(_app_jwt()),
        json={
            "repositories": [TARGET_REPO],
            "permissions": {"administration": "write", "actions": "read"},
        },
        timeout=20,
    )
    if r.status_code != 201:
        raise RuntimeError(f"INSTALLATION_TOKEN_HTTP_{r.status_code}")
    return r.json()["token"]


def _mint_runner_registration():
    token = _installation_token()
    try:
        r = requests.post(
            f"{API}/repos/{TARGET_OWNER}/{TARGET_REPO}/actions/runners/registration-token",
            headers=_headers(token),
            timeout=20,
        )
        if r.status_code != 201:
            raise RuntimeError(f"RUNNER_REGISTRATION_HTTP_{r.status_code}")
        return r.json()
    finally:
        token = ""


def _hybrid_encrypt(payload):
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    aad = b"omega-runner-authority-v1"
    ciphertext = AESGCM(key).encrypt(nonce, raw, aad)
    wrapped_key = HANDOFF_PUBLIC_KEY.encrypt(
        key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return {
        "schema": 1,
        "alg": "RSA-OAEP-SHA256+AES-256-GCM",
        "wrapped_key_b64": base64.b64encode(wrapped_key).decode(),
        "nonce_b64": base64.b64encode(nonce).decode(),
        "ciphertext_b64": base64.b64encode(ciphertext).decode(),
        "aad_b64": base64.b64encode(aad).decode(),
    }


def _encrypt_authority(payload):
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    nonce = os.urandom(12)
    aad = b"omega-runner-authority-persistent-v1"
    ciphertext = AESGCM(AUTHORITY_MASTER_KEY).encrypt(nonce, raw, aad)
    return {
        "schema": 1,
        "alg": "AES-256-GCM",
        "nonce_b64": base64.b64encode(nonce).decode(),
        "ciphertext_b64": base64.b64encode(ciphertext).decode(),
        "aad_b64": base64.b64encode(aad).decode(),
    }


def _decrypt_authority(doc):
    if int(doc.get("schema", 0)) != 1 or doc.get("alg") != "AES-256-GCM":
        raise RuntimeError("AUTHORITY_STATE_SCHEMA_INVALID")
    nonce = base64.b64decode(doc["nonce_b64"])
    ciphertext = base64.b64decode(doc["ciphertext_b64"])
    aad = base64.b64decode(doc["aad_b64"])
    raw = AESGCM(AUTHORITY_MASTER_KEY).decrypt(nonce, ciphertext, aad)
    payload = json.loads(raw.decode("utf-8"))
    required = {"app_id", "pem", "slug", "installation_id", "webhook_secret"}
    if not required.issubset(payload):
        raise RuntimeError("AUTHORITY_STATE_INCOMPLETE")
    return payload


def _apply_authority(payload):
    DATA["app"] = {
        "id": int(payload["app_id"]),
        "pem": str(payload["pem"]),
        "slug": str(payload["slug"]),
    }
    DATA["installation_id"] = int(payload["installation_id"])
    DATA["webhook_secret"] = str(payload["webhook_secret"])
    DATA["stage"] = "persistent_authority_ready"
    DATA["error"] = None


def _load_persisted_authority():
    try:
        r = requests.get(
            AUTHORITY_STATE_URL,
            headers={"User-Agent": "OMEGA-Runner-Authority-Broker/2.0"},
            timeout=20,
        )
        if r.status_code == 404:
            return False
        if r.status_code != 200:
            raise RuntimeError(f"AUTHORITY_STATE_HTTP_{r.status_code}")
        _apply_authority(_decrypt_authority(r.json()))
        print("OMEGA_AUTHORITY_STATE_LOAD_PASS", flush=True)
        return True
    except Exception as exc:
        DATA["error"] = f"AUTHORITY_STATE_LOAD_FAILED:{type(exc).__name__}"
        print(f"OMEGA_AUTHORITY_STATE_LOAD_ERROR {DATA['error']}", flush=True)
        return False


def _ensure_authority_loaded():
    if DATA.get("app") and DATA.get("installation_id") and DATA.get("webhook_secret"):
        return True
    return _load_persisted_authority()


def _revoke_installation():
    installation_id = DATA.get("installation_id")
    if not installation_id or not DATA.get("app"):
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
    version = "2.337.0"
    url = (
        f"https://github.com/actions/runner/releases/download/v{version}/"
        f"actions-runner-linux-x64-{version}.tar.gz"
    )
    expected_sha256 = "70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613"
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as fh:
        archive = pathlib.Path(fh.name)
    try:
        DATA["stage"] = "runner_download"
        print(f"OMEGA_AUTHORITY_RUNNER_DOWNLOAD version={version}", flush=True)
        with requests.get(
            url,
            stream=True,
            timeout=(20, 300),
            headers={"User-Agent": "OMEGA-Runner-Authority-Broker/2.0"},
        ) as dl:
            if dl.status_code != 200:
                raise RuntimeError(f"RUNNER_DOWNLOAD_HTTP_{dl.status_code}")
            digest = hashlib.sha256()
            with archive.open("wb") as out:
                for chunk in dl.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)
                        digest.update(chunk)
        actual = digest.hexdigest()
        if actual != expected_sha256:
            raise RuntimeError(f"RUNNER_ARCHIVE_SHA256_MISMATCH:{actual}")
        DATA["stage"] = "runner_extract"
        print(f"OMEGA_AUTHORITY_RUNNER_DOWNLOAD_PASS sha256={actual}", flush=True)
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(root, filter="data")
    finally:
        archive.unlink(missing_ok=True)


def _runner_worker(registration_token, reason):
    root = pathlib.Path("/tmp/omega-authority-runner")
    rc = None
    try:
        DATA["stage"] = "runner_provisioning"
        print(f"OMEGA_AUTHORITY_RUNNER_PROVISION_START reason={reason}", flush=True)
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        _download_runner(root)

        runner_name = f"omega-render-authority-{int(time.time())}"
        DATA["runner_name"] = runner_name
        env = os.environ.copy()
        env["RUNNER_ALLOW_RUNASROOT"] = "1"

        print(f"OMEGA_AUTHORITY_RUNNER_CONFIG_START name={runner_name}", flush=True)
        subprocess.run(
            [
                str(root / "config.sh"),
                "--url",
                f"https://github.com/{TARGET_OWNER}/{TARGET_REPO}",
                "--token",
                registration_token,
                "--name",
                runner_name,
                "--labels",
                "omega-ci",
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
        print(f"OMEGA_AUTHORITY_RUNNER_CONFIG_PASS name={runner_name}", flush=True)

        proc = subprocess.Popen([str(root / "run.sh")], cwd=root, env=env)
        rc = proc.wait()
        print(f"OMEGA_AUTHORITY_RUNNER_EXIT rc={rc}", flush=True)
        DATA["stage"] = "persistent_authority_ready"
        DATA["last_runner_result"] = "success" if rc == 0 else f"exit_{rc}"
        if rc != 0:
            DATA["error"] = f"RUNNER_EXIT_{rc}"
    except Exception as exc:
        registration_token = ""
        code = f"RUNNER_START_FAILED:{type(exc).__name__}"
        if isinstance(exc, subprocess.CalledProcessError):
            code += f":rc={exc.returncode}"
        DATA["stage"] = "persistent_authority_ready"
        DATA["last_runner_result"] = code
        DATA["error"] = code
        print(f"OMEGA_AUTHORITY_RUNNER_ERROR {code}", flush=True)
    finally:
        with LOCK:
            DATA["runner_active"] = False
        try:
            shutil.rmtree(root)
        except Exception:
            pass


def _ensure_ephemeral_runner(reason):
    if not _ensure_authority_loaded():
        raise RuntimeError("PERSISTENT_AUTHORITY_UNAVAILABLE")
    with LOCK:
        if DATA.get("runner_active"):
            print(f"OMEGA_AUTHORITY_RUNNER_ALREADY_ACTIVE reason={reason}", flush=True)
            return False
        DATA["runner_active"] = True
    try:
        regj = _mint_runner_registration()
        print(
            f"OMEGA_AUTHORITY_REGISTRATION_TOKEN_MINTED expires_at={regj.get('expires_at','unknown')}",
            flush=True,
        )
        threading.Thread(
            target=_runner_worker,
            args=(regj["token"], reason),
            daemon=True,
        ).start()
        return True
    except Exception:
        with LOCK:
            DATA["runner_active"] = False
        raise


def _hook_valid(body):
    secret = DATA.get("webhook_secret")
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not secret or not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _fail(code, exc=None):
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
        "description": (
            "Persistent OMEGA runner authority. Administration write mints only short-lived "
            "ephemeral runner registration tokens; Actions read is used for workflow-job webhooks. "
            "No Android signing key is created, stored, or exported."
        ),
        "hook_attributes": {"url": PUBLIC_BASE_URL + "/hook", "active": True},
        "default_permissions": {"administration": "write", "actions": "read"},
        "default_events": ["workflow_job"],
    }
    m = html.escape(json.dumps(manifest, separators=(",", ":")), quote=True)
    action = f"https://github.com/settings/apps/new?state={quote(BROKER_STATE)}"
    status = (
        "<p style='color:#4ee29a'><b>Persistente authority is al geladen.</b></p>"
        if _ensure_authority_loaded()
        else ""
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OMEGA runner authority</title></head>
<body style="font-family:sans-serif;background:#07111f;color:#eef5ff;max-width:760px;margin:40px auto;padding:24px">
<h1>OMEGA · persistent runner authority</h1>
{status}
<p>Deze privé GitHub App vraagt uitsluitend <b>Repository Administration: write</b> en <b>Actions: read</b>
voor <b>{html.escape(TARGET_OWNER + "/" + TARGET_REPO)}</b>.</p>
<p>De authority blijft geïnstalleerd. Iedere queued <b>omega-ci</b> job krijgt automatisch een nieuwe
ephemeral runner; na één job verdwijnt die runner weer. De Android signing-key wordt niet door deze
authority opgeslagen of geëxporteerd.</p>
<form method="post" action="{action}">
<input type="hidden" name="manifest" value="{m}">
<button style="font-size:18px;padding:14px 20px">Permanente GitHub-authority installeren</button>
</form></body></html>"""


@app.post("/hook")
def hook():
    body = request.get_data(cache=True)
    if not _ensure_authority_loaded():
        return ("", 503)
    if not _hook_valid(body):
        return ("", 401)
    event = request.headers.get("X-GitHub-Event", "")
    if event != "workflow_job":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    if payload.get("action") != "queued":
        return ("", 204)
    repo = ((payload.get("repository") or {}).get("full_name") or "")
    job = payload.get("workflow_job") or {}
    labels = {str(x) for x in (job.get("labels") or [])}
    if repo != f"{TARGET_OWNER}/{TARGET_REPO}" or "omega-ci" not in labels:
        return ("", 204)
    try:
        started = _ensure_ephemeral_runner(
            f"workflow_job:{job.get('id','unknown')}"
        )
        return jsonify({"ok": True, "runner_started": started}), 202
    except Exception as exc:
        DATA["error"] = f"WEBHOOK_RUNNER_START_FAILED:{type(exc).__name__}"
        return jsonify({"ok": False, "error": DATA["error"]}), 503


@app.get("/manifest")
def manifest_callback():
    try:
        if request.args.get("state") != BROKER_STATE:
            return _fail("STATE_MISMATCH")
        code = request.args.get("code", "")
        if not code:
            return _fail("MANIFEST_CODE_MISSING")
        r = requests.post(
            f"{API}/app-manifests/{quote(code)}/conversions",
            headers=_headers(),
            timeout=20,
        )
        if r.status_code != 201:
            return _fail(f"MANIFEST_CONVERSION_HTTP_{r.status_code}")
        cfg = r.json()
        if not cfg.get("id") or not cfg.get("pem") or not cfg.get("slug") or not cfg.get("webhook_secret"):
            return _fail("MANIFEST_CONVERSION_INCOMPLETE")
        DATA["app"] = {"id": cfg["id"], "pem": cfg["pem"], "slug": cfg["slug"]}
        DATA["webhook_secret"] = cfg["webhook_secret"]
        DATA["stage"] = "awaiting_installation"
        return redirect(
            f"https://github.com/apps/{quote(cfg['slug'])}/installations/new",
            code=302,
        )
    except Exception as exc:
        return _fail(f"MANIFEST_CALLBACK_FAILED:{type(exc).__name__}")


@app.get("/installed")
def installed():
    try:
        installation_id = int(request.args.get("installation_id", "0"))
        if installation_id <= 0:
            return _fail("INSTALLATION_ID_MISSING")
        jwt_token = _app_jwt()
        r = requests.get(
            f"{API}/app/installations/{installation_id}",
            headers=_headers(jwt_token),
            timeout=20,
        )
        if r.status_code != 200:
            return _fail(f"INSTALLATION_LOOKUP_HTTP_{r.status_code}")
        inst = r.json()
        login = ((inst.get("account") or {}).get("login") or "")
        perms = inst.get("permissions") or {}
        if login.lower() != TARGET_OWNER.lower():
            return _fail("INSTALLATION_ACCOUNT_MISMATCH")
        if perms.get("administration") != "write":
            return _fail("INSTALLATION_ADMIN_WRITE_MISSING")
        if perms.get("actions") not in ("read", "write"):
            return _fail("INSTALLATION_ACTIONS_READ_MISSING")

        DATA["installation_id"] = installation_id
        authority = {
            "app_id": DATA["app"]["id"],
            "pem": DATA["app"]["pem"],
            "slug": DATA["app"]["slug"],
            "installation_id": installation_id,
            "webhook_secret": DATA["webhook_secret"],
            "repository": f"{TARGET_OWNER}/{TARGET_REPO}",
        }
        DATA["authority_export"] = _encrypt_authority(authority)
        DATA["stage"] = "persistent_authority_pending_commit"

        regj = _mint_runner_registration()
        payload = {
            "repository": f"{TARGET_OWNER}/{TARGET_REPO}",
            "registration_token": regj["token"],
            "expires_at": regj["expires_at"],
            "installation_id": installation_id,
            "app_id": DATA["app"]["id"],
        }
        DATA["handoff"] = _hybrid_encrypt(payload)

        with LOCK:
            can_start = not DATA.get("runner_active")
            if can_start:
                DATA["runner_active"] = True
        if can_start:
            threading.Thread(
                target=_runner_worker,
                args=(regj["token"], "installation_bootstrap"),
                daemon=True,
            ).start()

        return """<!doctype html><html><body style='font-family:sans-serif;background:#07111f;color:#eef5ff;padding:32px'>
<h2 style='color:#4ee29a'>OMEGA permanente authority geautoriseerd</h2>
<p>De GitHub App-installatie blijft bestaan. De huidige queued omega-ci job krijgt nu automatisch
een ephemeral runner. Toekomstige omega-ci jobs starten via geverifieerde GitHub workflow_job webhooks.</p>
<p>Er hoeft geen runner-token of signing-key te worden gekopieerd.</p>
</body></html>"""
    except Exception as exc:
        return _fail(f"INSTALLATION_FLOW_FAILED:{type(exc).__name__}")


@app.get("/authority-export/<nonce>")
def authority_export(nonce):
    if nonce != BROKER_NONCE:
        return jsonify({"error": "not_found"}), 404
    doc = DATA.get("authority_export")
    if not doc:
        return jsonify(
            {
                "ready": False,
                "stage": DATA.get("stage"),
                "error": DATA.get("error"),
            }
        ), 202
    return jsonify({"ready": True, "authority": doc})


@app.get("/healthz")
def healthz():
    _ensure_authority_loaded()
    return jsonify(
        {
            "ok": DATA["stage"] != "error",
            "stage": DATA["stage"],
            "runner_name": DATA.get("runner_name"),
            "runner_active": DATA.get("runner_active"),
            "last_runner_result": DATA.get("last_runner_result"),
            "persistent_authority": bool(
                DATA.get("app")
                and DATA.get("installation_id")
                and DATA.get("webhook_secret")
            ),
            "error": DATA["error"],
        }
    )


@app.get("/handoff/<nonce>")
def handoff(nonce):
    if nonce != BROKER_NONCE:
        return jsonify({"error": "not_found"}), 404
    if not DATA.get("handoff"):
        return jsonify(
            {
                "ready": False,
                "stage": DATA.get("stage"),
                "error": DATA.get("error"),
            }
        ), 202
    return jsonify(
        {
            "ready": True,
            "stage": DATA.get("stage"),
            "handoff": DATA["handoff"],
        }
    )


@app.get("/cleanup/<nonce>")
def cleanup(nonce):
    if nonce != BROKER_NONCE:
        return jsonify({"error": "not_found"}), 404
    if _revoke_installation():
        DATA["stage"] = "installation_revoked"
        DATA["app"] = None
        DATA["installation_id"] = None
        DATA["webhook_secret"] = None
        return jsonify({"ok": True, "stage": DATA["stage"]})
    return jsonify({"ok": False, "stage": "cleanup_failed"}), 500


# Best-effort restore after service restart. A missing state blob is expected
# before the first persistent GitHub App installation is committed.
_load_persisted_authority()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
