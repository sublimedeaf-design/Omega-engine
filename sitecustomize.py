import base64
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _install_legacy_authority_bridge():
    legacy_key_b64 = os.environ.get("AUTHORITY_SEAL_KEY_B64", "")
    legacy_blob = os.environ.get("AUTHORITY_PERSIST_BLOB", "")
    master_key_b64 = os.environ.get("AUTHORITY_MASTER_KEY_B64", "")
    if not (legacy_key_b64 and legacy_blob and master_key_b64):
        print("SUBLIMEJ_AUTHORITY_LEGACY_BRIDGE=UNAVAILABLE", flush=True)
        return

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        legacy_key = base64.b64decode(legacy_key_b64)
        master_key = base64.b64decode(master_key_b64)
        if len(legacy_key) != 32 or len(master_key) != 32:
            raise RuntimeError("AUTHORITY_KEY_LENGTH_INVALID")

        sealed = base64.urlsafe_b64decode(legacy_blob.encode("ascii"))
        if len(sealed) <= 12:
            raise RuntimeError("AUTHORITY_LEGACY_BLOB_INVALID")
        raw = AESGCM(legacy_key).decrypt(
            sealed[:12], sealed[12:], b"omega-authority-persist-v1"
        )
        legacy = json.loads(raw.decode("utf-8"))
        required = {"app_id", "pem", "slug", "installation_id"}
        if not required.issubset(legacy):
            raise RuntimeError("AUTHORITY_LEGACY_STATE_INCOMPLETE")

        payload = {
            "app_id": legacy["app_id"],
            "pem": legacy["pem"],
            "slug": legacy["slug"],
            "installation_id": legacy["installation_id"],
            "webhook_secret": "LEGACY_POLL_ONLY",
        }
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        nonce = os.urandom(12)
        aad = b"omega-runner-authority-persistent-v1"
        ciphertext = AESGCM(master_key).encrypt(nonce, plaintext, aad)
        state_doc = {
            "schema": 1,
            "alg": "AES-256-GCM",
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "aad_b64": base64.b64encode(aad).decode("ascii"),
        }
        state_bytes = json.dumps(state_doc, separators=(",", ":")).encode("utf-8")

        class StateHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/state":
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(state_bytes)))
                self.end_headers()
                self.wfile.write(state_bytes)

            def log_message(self, _format, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), StateHandler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        os.environ["AUTHORITY_STATE_URL"] = f"http://127.0.0.1:{port}/state"
        print("SUBLIMEJ_AUTHORITY_LEGACY_BRIDGE=PASS", flush=True)
    except Exception as exc:
        print(f"SUBLIMEJ_AUTHORITY_LEGACY_BRIDGE=FAIL:{type(exc).__name__}", flush=True)


def _bootstrap_runner_worker(token):
    root = pathlib.Path("/tmp/sublimej-bootstrap-runner")
    try:
        version = "2.337.0"
        expected = "70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613"
        repo = os.environ.get("SUBLIMEJ_BOOTSTRAP_REPOSITORY", "https://github.com/sublimedeaf-design/Sublimej")
        label = os.environ.get("SUBLIMEJ_BOOTSTRAP_RUNNER_LABEL", "sublimej-ci")
        name = os.environ.get("SUBLIMEJ_BOOTSTRAP_RUNNER_NAME", "sublimej-render-authority")

        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        url = (
            f"https://github.com/actions/runner/releases/download/v{version}/"
            f"actions-runner-linux-x64-{version}.tar.gz"
        )
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as fh:
            archive = pathlib.Path(fh.name)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SublimeJ-Runner-Recovery/1"})
            digest = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=180) as response, archive.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
            actual = digest.hexdigest()
            if actual != expected:
                raise RuntimeError(f"RUNNER_ARCHIVE_SHA256_MISMATCH:{actual}")
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(root, filter="data")
        finally:
            archive.unlink(missing_ok=True)

        env = os.environ.copy()
        env["RUNNER_ALLOW_RUNASROOT"] = "1"
        subprocess.run(
            [
                str(root / "config.sh"),
                "--url",
                repo,
                "--token",
                token,
                "--name",
                name,
                "--labels",
                label,
                "--unattended",
                "--replace",
            ],
            cwd=root,
            env=env,
            check=True,
            timeout=180,
        )
        token = ""
        os.environ.pop("SUBLIMEJ_BOOTSTRAP_RUNNER_TOKEN", None)
        print(
            f"SUBLIMEJ_BOOTSTRAP_RUNNER=ONLINE name={name} label={label} version={version}",
            flush=True,
        )
        rc = subprocess.call([str(root / "run.sh")], cwd=root, env=env)
        print(f"SUBLIMEJ_BOOTSTRAP_RUNNER=EXIT rc={rc}", flush=True)
    except Exception as exc:
        token = ""
        print(f"SUBLIMEJ_BOOTSTRAP_RUNNER=FAIL:{type(exc).__name__}", flush=True)


def _start_bootstrap_runner_if_configured():
    token = os.environ.get("SUBLIMEJ_BOOTSTRAP_RUNNER_TOKEN", "")
    # Build-time Python invocations must never register a runner. Render exposes
    # PORT to the running web service; use that as the runtime boundary.
    if not token or not os.environ.get("PORT"):
        return
    threading.Thread(target=_bootstrap_runner_worker, args=(token,), daemon=True).start()


_install_legacy_authority_bridge()
_start_bootstrap_runner_if_configured()
