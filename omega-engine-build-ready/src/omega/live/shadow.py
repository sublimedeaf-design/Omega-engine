from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json, pathlib

@dataclass(frozen=True)
class ShadowPrediction:
    fixture_id:str; kickoff:str; market:str; probability:float; offered_odds:float|None; model_version:str; input_fingerprint:str

def append_shadow(path, prediction:ShadowPrediction):
    row=asdict(prediction); row['recorded_at']=datetime.now(timezone.utc).isoformat()
    p=pathlib.Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a',encoding='utf8') as f: f.write(json.dumps(row,sort_keys=True)+'\n')
