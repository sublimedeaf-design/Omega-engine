from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import math
from typing import Callable, Iterable


@dataclass(frozen=True)
class ProbabilisticPrediction:
    kickoff: datetime
    fixture_id: str
    probability: float
    outcome: int


def brier_score(rows: Iterable[ProbabilisticPrediction]) -> float:
    rows = list(rows)
    if not rows:
        raise ValueError("no predictions")
    return sum((r.probability - r.outcome) ** 2 for r in rows) / len(rows)


def log_loss(rows: Iterable[ProbabilisticPrediction], eps: float = 1e-12) -> float:
    rows = list(rows)
    if not rows:
        raise ValueError("no predictions")
    total = 0.0
    for r in rows:
        p = min(1.0 - eps, max(eps, r.probability))
        total -= r.outcome * math.log(p) + (1 - r.outcome) * math.log(1 - p)
    return total / len(rows)


def walk_forward(
    events: list,
    min_train: int,
    fit_predict: Callable[[list, object], float],
    outcome: Callable[[object], int],
    fixture_id: Callable[[object], str],
    kickoff: Callable[[object], datetime],
) -> list[ProbabilisticPrediction]:
    """Generic chronological backtester with a hard no-future-data boundary."""
    ordered = sorted(events, key=kickoff)
    out: list[ProbabilisticPrediction] = []
    for i in range(min_train, len(ordered)):
        target = ordered[i]
        train = [e for e in ordered[:i] if kickoff(e) < kickoff(target)]
        p = float(fit_predict(train, target))
        if not 0.0 <= p <= 1.0:
            raise ValueError("fit_predict returned invalid probability")
        out.append(ProbabilisticPrediction(kickoff(target), fixture_id(target), p, int(outcome(target))))
    return out
