from __future__ import annotations
from pathlib import Path
import hashlib
import json


def input_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def connect(path: str | Path):
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("Install omega-engine[data] to use DuckDB storage") from exc
    con = duckdb.connect(str(path))
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    con.execute(schema)
    return con
