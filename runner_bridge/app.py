from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import threading
import time
from typing import Any

import jwt
from flask import Flask, jsonify, request
from jwt import PyJWKClient

ROOT = pathlib.Path(__file__).resolve().parent
RUNNER = ROOT / "actions-runner"
GH_BIN = ROOT / "bin" / "bin"
PRIVATE_REPOSITORY = os.getenv("OMEGA_PRIVATE_REPOSITORY", "sublimedeaf-design/Omega-engines").strip()
SOURCE_SHA = os.getenv("OMEGA_SOURCE_SHA", "").strip()
RESCUE_REF = os.getenv("OMEGA_RESCUE_REF", "").strip()
CONTROL_REPOSITORY = os.getenv("OMEGA_CONTROL_REPOSITORY", "sublimedeaf-design/Omega-engine").strip()
CONTROL_REF = os.getenv("OMEGA_CONTROL_REF", "").strip()
AUDIENCE = "omega-render-runner"
ISSUER = "https://token.actions.githubusercontent.com"
JWKS = PyJWKClient("https://token.actions.githubusercontent.com/.well-known/jwks")

app = Flask(__name__)
LOCK = threading.Lock()
STATE: dict[str, Any] = {
    "service": "omega-render-canonical-signer-runner",
    "ok": True,
    "runner_state": "idle",
    "source_sha": SOURCE_SHA,
    "rescue_ref": RESCUE_REF,
    "credential_material_recorded": False,
    "updated_at": None,
}


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def public_state() -> dict[str, Any]:
    with LOCK:
        return dict(STATE)


def verify_oidc(raw: str) -> dict[str, Any]:
    if not raw or len(raw) > 20000:
        raise ValueError("OMEGA_RENDER_OIDC_MISSING")
    key = JWKS.get_signing_key_from_jwt(raw)
    claims = jwt.decode(raw, key.key, algorithms=["RS256"], audience=AUDIENCE, issuer=ISSUER)
    if claims.get("repository") != CONTROL_REPOSITORY:
        raise ValueError("OMEGA_RENDER_OIDC_REPOSITORY_INVALID")
    if CONTROL_REF and claims.get("ref") != CONTROL_REF:
        raise ValueError("OMEGA_RENDER_OIDC_REF_INVALID")
    if claims.get("event_name") != "push":
        raise ValueError("OMEGA_RENDER_OIDC_EVENT_INVALID")
    workflow_ref = str(claims.get("job_workflow_ref") or claims.get("workflow_ref") or "")
    if ".github/workflows/omega-canonical-android-signer.yml@" not in workflow_ref:
        raise ValueError("OMEGA_RENDER_OIDC_WORKFLOW_INVALID")
    return claims


def run_runner(registration_token: str) -> None:
    env = os.environ.copy()
    env["PATH"] = str(GH_BIN) + os.pathsep + env.get("PATH", "")
    env["RUNNER_ALLOW_RUNASROOT"] = "1"
    log_path = ROOT / "runner.log"
    try:
        with LOCK:
            STATE.update(runner_state="configuring", updated_at=stamp(), ok=True)
        for name in (".runner", ".credentials", ".credentials_rsaparams", ".service"):
            path = RUNNER / name
            if path.exists():
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        config = [
            str(RUNNER / "config.sh"),
            "--url",
            "https://github.com/" + PRIVATE_REPOSITORY,
            "--token",
            registration_token,
            "--name",
            "omega-render-signer-" + SOURCE_SHA[:12],
            "--labels",
            "omega-ci",
            "--unattended",
            "--ephemeral",
            "--replace",
        ]
        with log_path.open("ab", buffering=0) as log:
            result = subprocess.run(
                config,
                cwd=RUNNER,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError("OMEGA_RENDER_RUNNER_CONFIG_FAILED:" + str(result.returncode))
            with LOCK:
                STATE.update(runner_state="online_waiting", updated_at=stamp(), ok=True)
            proc = subprocess.Popen(
                [str(RUNNER / "run.sh")],
                cwd=RUNNER,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            code = proc.wait()
        with LOCK:
            STATE.update(
                runner_state="completed" if code == 0 else "runner_failed",
                runner_exit_code=code,
                updated_at=stamp(),
                ok=(code == 0),
            )
    except Exception as exc:
        with LOCK:
            STATE.update(runner_state="error", error=str(exc)[:240], updated_at=stamp(), ok=False)


@app.get("/")
@app.get("/healthz")
def health():
    return jsonify(public_state()), 200


@app.post("/arm")
def arm():
    try:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise ValueError("OMEGA_RENDER_AUTH_SCHEME_INVALID")
        verify_oidc(auth[7:].strip())
        body = request.get_json(force=True, silent=False) or {}
        token = str(body.get("registration_token") or "")
        source = str(body.get("source_sha") or "")
        rescue_ref = str(body.get("rescue_ref") or "")
        repository = str(body.get("repository") or "")
        if not re.fullmatch(r"[0-9A-Za-z_\-]{20,500}", token):
            raise ValueError("OMEGA_RENDER_REGISTRATION_TOKEN_INVALID")
        if source != SOURCE_SHA or not re.fullmatch(r"[0-9a-f]{40}", source):
            raise ValueError("OMEGA_RENDER_SOURCE_SHA_INVALID")
        if rescue_ref != RESCUE_REF or not rescue_ref.startswith("rescue/"):
            raise ValueError("OMEGA_RENDER_RESCUE_REF_INVALID")
        if repository != PRIVATE_REPOSITORY:
            raise ValueError("OMEGA_RENDER_PRIVATE_REPOSITORY_INVALID")
        with LOCK:
            current = str(STATE.get("runner_state") or "")
            if current in {"configuring", "online_waiting"}:
                return jsonify({"ok": True, "runner_state": current, "credential_material_recorded": False}), 202
            STATE.pop("error", None)
            STATE.pop("runner_exit_code", None)
            STATE.update(runner_state="arming", updated_at=stamp(), ok=True)
        thread = threading.Thread(target=run_runner, args=(token,), daemon=True)
        thread.start()
        return jsonify({"ok": True, "runner_state": "arming", "credential_material_recorded": False}), 202
    except Exception as exc:
        with LOCK:
            STATE.update(runner_state="rejected", error=str(exc)[:240], updated_at=stamp(), ok=False)
        return jsonify({"ok": False, "error": str(exc)[:240], "credential_material_recorded": False}), 403
