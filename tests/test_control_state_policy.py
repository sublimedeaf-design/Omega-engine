import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from control_state_policy import is_state_only_path


class ControlStatePolicyTests(unittest.TestCase):
    def test_known_wake_pointers_and_epoch_data_are_allowed(self):
        for path in (
            "bootstrap/omega/pr-validation-trigger.txt",
            "bootstrap/omega/recovery-trigger.txt",
            "bootstrap/omega/canonical-unsigned-lock.json",
            "bootstrap/omega/validation-requests/" + "a" * 40 + ".json",
            "federation/epochs/current.json",
            "federation/epochs/releases/9980-proof.json",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_state_only_path(path))

    def test_executable_bootstrap_and_control_changes_require_new_epoch(self):
        for path in (
            "bootstrap/omega/codespace_wake.py",
            "bootstrap/omega/hot_sync_runtime_remote.sh",
            "bootstrap/omega/cloudflare/worker.js",
            "bootstrap/omega/qstash/wrangler.toml",
            "bootstrap/omega/validation-requests/run.py",
            "bootstrap/omega/unknown-trigger.txt",
            "federation/epochs/run.sh",
            "control-plane/state-only-paths.json",
            "scripts/control_state_policy.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(is_state_only_path(path))

    def test_malformed_and_traversing_paths_are_denied(self):
        for path in (
            "", "/federation/epochs/current.json", "federation/epochs/../current.json",
            "federation//epochs/current.json", "federation/epochs/./current.json",
            "federation/epochs/current.json\n", "federation\\epochs\\current.json",
            "bootstrap/omega/validation-requests/short.json", None,
        ):
            with self.subTest(path=path):
                self.assertFalse(is_state_only_path(path))


if __name__ == "__main__":
    unittest.main()
