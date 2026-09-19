from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import importlib.util
import sys

@dataclass(frozen=True)
class HealthReport:
    ok: bool
    python: str
    numpy: bool
    scipy: bool
    duckdb: bool
    schema_present: bool

    def to_dict(self):
        return asdict(self)

def healthcheck() -> HealthReport:
    schema = Path(__file__).parent / 'storage' / 'schema.sql'
    numpy_ok = importlib.util.find_spec('numpy') is not None
    scipy_ok = importlib.util.find_spec('scipy') is not None
    duckdb_ok = importlib.util.find_spec('duckdb') is not None
    schema_ok = schema.is_file() and schema.stat().st_size > 0
    return HealthReport(numpy_ok and scipy_ok and schema_ok, sys.version.split()[0], numpy_ok, scipy_ok, duckdb_ok, schema_ok)
