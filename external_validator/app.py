from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time

from flask import Flask, jsonify, request
import jwt
from jwt import PyJWKClient

app = Flask(__name__)
ISSUER = "https://token.actions.githubusercontent.com"
JWKS = "https://token.actions.githubusercontent.com/.well-known/jwks"
AUDIENCE = "omega-external-validator"
ALLOWED_REPOSITORY = os.getenv("OMEGA_VALIDATOR_ALLOWED_REPOSITORY", "sublimedeaf-design/Omega-engine")
ALLOWED_WORKFLOW = os.getenv("OMEGA_VALIDATOR_ALLOWED_WORKFLOW", "OMEGA External Validator Dispatch")
PROVIDER = os.getenv("OMEGA_VALIDATOR_PROVIDER", "unknown")
EXPECTED_PYTHON = os.getenv("OMEGA_VALIDATOR_EXPECTED_PYTHON", "3.13").strip()
if EXPECTED_PYTHON not in {"3.11", "3.13", "3.14"}:
    raise RuntimeError("OMEGA_VALIDATOR_EXPECTED_PYTHON_INVALID")
MAX_BUNDLE = int(os.getenv("OMEGA_VALIDATOR_MAX_BUNDLE_BYTES", str(100 * 1024 * 1024)))
if MAX_BUNDLE < 1024 * 1024 or MAX_BUNDLE > 128 * 1024 * 1024:
    raise RuntimeError("OMEGA_VALIDATOR_MAX_BUNDLE_BYTES_INVALID")
STATE = Path(os.getenv("OMEGA_VALIDATOR_STATE", "/tmp/omega-validator-attestations"))
STATE.mkdir(parents=True, exist_ok=True)
LOCK = threading.Lock()
JWK = PyJWKClient(JWKS)


def _write(sha: str, payload: dict) -> None:
    target = STATE / f"{sha}.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(target)


def _read(sha: str) -> dict | None:
    target = STATE / f"{sha}.json"
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None


def _oidc() -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise ValueError("OIDC_BEARER_MISSING")
    token = auth[7:].strip()
    key = JWK.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        audience=AUDIENCE,
        issuer=ISSUER,
        options={"require": ["exp", "iat", "iss", "aud", "repository", "ref"]},
    )
    if claims.get("repository") != ALLOWED_REPOSITORY:
        raise ValueError("OIDC_REPOSITORY_DENIED")
    if claims.get("ref") != "refs/heads/main":
        raise ValueError("OIDC_REF_DENIED")
    if claims.get("workflow") != ALLOWED_WORKFLOW:
        raise ValueError("OIDC_WORKFLOW_DENIED")
    if claims.get("event_name") not in {"workflow_dispatch", "schedule", "push"}:
        raise ValueError("OIDC_EVENT_DENIED")
    return claims


def _safe_extract(raw: bytes, dst: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        base = dst.resolve()
        members = tf.getmembers()
        for member in members:
            target = (dst / member.name).resolve()
            if target != base and base not in target.parents:
                raise ValueError("BUNDLE_PATH_ESCAPE")
            if member.issym() or member.islnk():
                raise ValueError("BUNDLE_LINK_DENIED")
        tf.extractall(dst)


def _run(argv: list[str], cwd: Path, *, timeout: int = 1200, env: dict | None = None) -> dict:
    started = time.time()
    proc = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        shell=False,
        timeout=timeout,
        env=env,
    )
    out = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-12000:]
    return {"argv": argv[:4], "rc": proc.returncode, "seconds": round(time.time() - started, 3), "tail": out}


def _validate(sha: str, raw: bytes, bundle_sha: str, oidc_claims: dict) -> None:
    work = Path(tempfile.mkdtemp(prefix="omega-validator-"))
    result = {
        "schema_version": 1,
        "provider": PROVIDER,
        "sha": sha,
        "bundle_sha256": bundle_sha,
        "state": "running",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "credential_material_recorded": False,
        "oidc": {
            "repository": oidc_claims.get("repository"),
            "ref": oidc_claims.get("ref"),
            "workflow": oidc_claims.get("workflow"),
            "run_id": oidc_claims.get("run_id"),
        },
        "checks": [],
    }
    _write(sha, result)
    try:
        _safe_extract(raw, work)
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True, timeout=30).strip()
        if head != sha:
            raise RuntimeError(f"EXACT_SHA_MISMATCH:{head}!={sha}")
        version = subprocess.check_output([os.sys.executable, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], text=True).strip()
        if version != EXPECTED_PYTHON:
            raise RuntimeError(f"PYTHON_VERSION_MISMATCH:{version}!={EXPECTED_PYTHON}")

        venv = work / ".omega-validator-venv"
        commands = [
            ([os.sys.executable, "-m", "venv", str(venv)], 180),
        ]
        for argv, timeout in commands:
            row = _run(argv, work, timeout=timeout)
            result["checks"].append(row)
            if row["rc"] != 0:
                raise RuntimeError(f"COMMAND_FAILED:{argv[0]}:{row['rc']}")

        py = str(venv / "bin" / "python")
        env = {**os.environ, "PYTHONPATH": str(work / "src")}
        suite = [
            ([py, "-m", "pip", "install", "--upgrade", "pip"], 300),
            ([py, "-m", "pip", "install", "-c", "requirements-ci.lock", "-e", ".[dev,data]"], 900),
            ([py, "-m", "pytest", "-q"], 900),
            ([py, "-m", "compileall", "-q", "src", "scripts"], 300),
            ([py, "-m", "pip", "check"], 300),
            ([py, "scripts/repo_audit.py", "--out", "reports/external-repo-audit.json"], 300),
            ([py, "-c", "from omega.research.preflight import run_preflight; r=run_preflight('reports/external-preflight.json'); assert r['passed'], r"], 300),
            ([py, "scripts/final_audit_gate.py", "--audit", "reports/external-repo-audit.json", "--out", "reports/external-final-audit.json"], 300),
            ([py, "scripts/validate_agent_handoff.py", "--self-check"], 300),
            ([py, "scripts/agent_orchestrator.py", "--agents", ".omega/agents.json", "--plan", ".omega/work-plan.json", "validate"], 300),
            ([py, "-m", "pytest", "-q", "tests/test_storage.py", "tests/test_support_runtime_integrity.py"], 300),
            ([py, "-c", "from omega.research.preflight import run_preflight; [(_ for _ in ()).throw(AssertionError(r)) if not (r:=run_preflight(backend=b))['passed'] or r['storage_backend']!=b else None for b in ('sqlite','duckdb')]"], 300),
        ]
        for argv, timeout in suite:
            row = _run(argv, work, timeout=timeout, env=env)
            result["checks"].append(row)
            _write(sha, result)
            if row["rc"] != 0:
                raise RuntimeError(f"COMMAND_FAILED:{' '.join(argv[:3])}:{row['rc']}")

        result["state"] = "success"
        result["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    except Exception as exc:
        result["state"] = "failure"
        result["error"] = f"{type(exc).__name__}:{str(exc)[:1000]}"
        result["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    finally:
        _write(sha, result)
        shutil.rmtree(work, ignore_errors=True)


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "provider": PROVIDER, "audience": AUDIENCE, "suite": "core", "python": EXPECTED_PYTHON})


@app.post("/validate")
def validate():
    try:
        claims = _oidc()
        sha = request.headers.get("x-omega-sha", "").strip().lower()
        if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
            return jsonify({"ok": False, "error": "INVALID_SHA"}), 400
        raw = request.get_data(cache=False, as_text=False)
        if not raw or len(raw) > MAX_BUNDLE:
            return jsonify({"ok": False, "error": "INVALID_BUNDLE_SIZE"}), 413
        bundle_sha = hashlib.sha256(raw).hexdigest()
        with LOCK:
            prior = _read(sha)
            if prior and prior.get("state") in {"running", "success"}:
                prior_bundle = str(prior.get("bundle_sha256") or "")
                if prior_bundle and prior_bundle != bundle_sha:
                    return jsonify({
                        "ok": False,
                        "error": "IMMUTABLE_SHA_BUNDLE_CONFLICT",
                        "sha": sha,
                    }), 409
                return jsonify({
                    "ok": True,
                    "accepted": False,
                    "reason": "already_" + str(prior.get("state")),
                    "sha": sha,
                    "bundle_sha256": bundle_sha,
                }), 202
            thread = threading.Thread(target=_validate, args=(sha, raw, bundle_sha, claims), daemon=True)
            thread.start()
        return jsonify({"ok": True, "accepted": True, "sha": sha, "bundle_sha256": bundle_sha}), 202
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}:{str(exc)[:300]}"}), 401


@app.get("/attestation/<sha>")
def attestation(sha: str):
    row = _read(sha.lower())
    if row is None:
        return jsonify({"ok": False, "error": "NOT_FOUND"}), 404
    return jsonify(row)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
