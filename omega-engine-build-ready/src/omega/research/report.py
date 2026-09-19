from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, math
from omega.backtest import ProbabilisticPrediction, brier_score, log_loss

@dataclass(frozen=True)
class BenchmarkSummary:
    n: int
    brier: float
    logloss: float
    calibration_mae: float


def calibration_mae(rows, bins: int = 10) -> float:
    rows=list(rows)
    if not rows: raise ValueError('no predictions')
    total=0.0
    for b in range(bins):
        lo, hi=b/bins,(b+1)/bins
        xs=[r for r in rows if lo <= r.probability < hi or (b==bins-1 and r.probability==1.0)]
        if xs:
            total += len(xs)/len(rows)*abs(sum(x.probability for x in xs)/len(xs)-sum(x.outcome for x in xs)/len(xs))
    return total


def summarize(rows) -> BenchmarkSummary:
    rows=list(rows)
    return BenchmarkSummary(len(rows), brier_score(rows), log_loss(rows), calibration_mae(rows))


def write_report(path: str|Path, title: str, models: dict[str, list[ProbabilisticPrediction]], metadata: dict|None=None):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    summaries={k: asdict(summarize(v)) for k,v in models.items() if v}
    payload={'title':title,'metadata':metadata or {},'models':summaries}
    path.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding='utf-8')
    return payload
