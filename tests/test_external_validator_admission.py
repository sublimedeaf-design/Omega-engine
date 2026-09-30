"""Exercise admission through Flask while the real validation worker is delayed."""
import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("omega_validator_admission", ROOT / "external_validator/app.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
SHA = "a" * 40
RAW = b"same immutable bundle"


def submit(raw=RAW):
    with validator.app.test_client() as client:
        response = client.post("/validate", data=raw, headers={
            "x-omega-sha": SHA,
            "x-omega-validator-code-sha256": validator.VALIDATOR_CODE_SHA256,
        })
        return response.status_code, response.get_json()


def process_request(barrier, output):
    barrier.wait(timeout=10)
    output.put(submit())


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.state_patch = patch.object(validator, "STATE", Path(self.directory.name))
        self.auth_patch = patch.object(validator, "_oidc", return_value={"run_id": "test"})
        self.state_patch.start()
        self.auth_patch.start()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.state_patch.stop)
        self.addCleanup(self.auth_patch.stop)

    def test_concurrent_requests_reserve_before_worker_runs(self):
        barrier = threading.Barrier(8)
        release = threading.Event()
        finished = threading.Event()
        calls = []

        def worker(sha, raw, digest, claims):
            calls.append(sha)
            release.wait(timeout=10)
            row = validator._read(sha)
            row["state"] = "success"
            validator._write(sha, row)
            finished.set()

        def request_once():
            barrier.wait(timeout=10)
            return submit()

        with patch.object(validator, "_validate", side_effect=worker):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                    rows = list(pool.map(lambda _: request_once(), range(8)))
                self.assertEqual([code for code, _ in rows], [202] * 8)
                self.assertEqual(sum(row["accepted"] for _, row in rows), 1)
                self.assertEqual(validator._read(SHA)["state"], "running")
                self.assertEqual(len(calls), 1)
            finally:
                release.set()
                self.assertTrue(finished.wait(timeout=10))
        code, row = submit()
        self.assertEqual(code, 202)
        self.assertEqual(row["reason"], "already_success")
        self.assertFalse(row["accepted"])

    @unittest.skipUnless("fork" in multiprocessing.get_all_start_methods(), "Linux process lock")
    def test_separate_processes_share_the_same_reservation(self):
        ctx = multiprocessing.get_context("fork")
        barrier, output = ctx.Barrier(4), ctx.Queue()
        # Workers stay inert so admission, rather than worker progress, decides.
        with patch.object(validator, "_validate", return_value=None):
            processes = [ctx.Process(target=process_request, args=(barrier, output)) for _ in range(4)]
            for process in processes:
                process.start()
            rows = [output.get(timeout=10) for _ in processes]
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)
        self.assertEqual(sum(row["accepted"] for _, row in rows), 1)
        self.assertEqual([code for code, _ in rows], [202] * 4)

    def test_conflicting_bundle_is_rejected_in_every_recorded_state(self):
        for state in ("running", "success", "failure"):
            with self.subTest(state=state):
                validator._write(SHA, {"state": state, "bundle_sha256": hashlib.sha256(RAW).hexdigest()})
                code, row = submit(b"different bundle")
                self.assertEqual(code, 409)
                self.assertEqual(row["error"], "IMMUTABLE_SHA_BUNDLE_CONFLICT")

    def test_failed_worker_start_is_retryable_and_not_running_forever(self):
        with patch.object(validator.threading.Thread, "start", side_effect=RuntimeError("no thread")):
            code, row = submit()
        self.assertEqual(code, 503)
        self.assertEqual(row["error"], "WORKER_START_FAILED")
        self.assertEqual(validator._read(SHA)["state"], "failure")
        with patch.object(validator, "_validate", return_value=None):
            code, row = submit()
        self.assertEqual(code, 202)
        self.assertTrue(row["accepted"])

    def test_failed_work_directory_creation_records_failure(self):
        digest = hashlib.sha256(RAW).hexdigest()
        validator._write(SHA, validator._initial_result(SHA, digest, {}))
        with patch.object(validator.tempfile, "mkdtemp", side_effect=OSError("no disk")):
            validator._validate(SHA, RAW, digest, {})
        row = validator._read(SHA)
        self.assertEqual(row["state"], "failure")
        self.assertIn("OSError:no disk", row["error"])

    def test_wrong_validator_code_cannot_admit_work(self):
        with validator.app.test_client() as client:
            response = client.post("/validate", data=RAW, headers={
                "x-omega-sha": SHA,
                "x-omega-validator-code-sha256": "0" * 64,
            })
        self.assertEqual(response.status_code, 409)
        self.assertIsNone(validator._read(SHA))

    def test_unauthenticated_request_cannot_reserve_work(self):
        with patch.object(validator, "_oidc", side_effect=ValueError("OIDC_BEARER_MISSING")):
            code, row = submit()
        self.assertEqual(code, 401)
        self.assertIsNone(validator._read(SHA))


if __name__ == "__main__":
    unittest.main()
