from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json

def export_value_snapshot(rows, path):
    """Export only verified VALUE rows for the Android client.

    Required: kickoff, match, market, selection, odds, probability, fair_odds, ev.
    Rows with odds < 1.90 or verified=False are omitted. UNKNOWN fields are rejected.
    """
    required=("kickoff","match","market","selection","odds","probability","fair_odds","ev")
    out=[]
    for r in rows:
        if not r.get("verified",False): continue
        if any(r.get(k) in (None,"","UNKNOWN") for k in required): continue
        try:
            if float(r["odds"]) < 1.90: continue
        except Exception: continue
        out.append({k:r[k] for k in required})
    out.sort(key=lambda x:x["kickoff"])
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"value":out}
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    return payload
