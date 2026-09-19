from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import csv
from pathlib import Path
from omega.models.dixon_coles import Match

DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d")

def _date(s: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"unsupported date: {s!r}")

def load_results(path: str | Path) -> list[Match]:
    """Load a Football-Data-style CSV without network access.

    Required columns: Date, HomeTeam, AwayTeam, FTHG, FTAG.
    """
    out=[]
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if not all(r.get(k) not in (None, "") for k in ("Date","HomeTeam","AwayTeam","FTHG","FTAG")):
                continue
            out.append(Match(_date(r["Date"]), r["HomeTeam"].strip(), r["AwayTeam"].strip(), int(r["FTHG"]), int(r["FTAG"])))
    return sorted(out, key=lambda x: x.kickoff)
