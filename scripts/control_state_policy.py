"""Shared release boundary: known data pointers may advance; code requires an epoch."""
import json
from pathlib import Path
import re
import sys

POLICY_PATH = Path(__file__).resolve().parents[1] / "control-plane/state-only-paths.json"
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
EXACT = frozenset(POLICY["exact_paths"])
PATTERNS = tuple(re.compile(value) for value in POLICY["patterns"])


def is_state_only_path(path: str) -> bool:
    if not isinstance(path, str) or not path or "\\" in path:
        return False
    if any(part in {"", ".", ".."} for part in path.split("/")):
        return False
    return path in EXACT or any(pattern.fullmatch(path) for pattern in PATTERNS)


if __name__ == "__main__":
    raise SystemExit(0 if len(sys.argv) > 1 and all(is_state_only_path(x) for x in sys.argv[1:]) else 1)
