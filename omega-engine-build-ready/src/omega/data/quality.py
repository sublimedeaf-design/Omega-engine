from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class Observation:
    field: str
    value: object
    source: str
    known_at: datetime
    confidence: float


def consensus(observations: list[Observation], as_of: datetime) -> tuple[object|None, float]:
    eligible=[o for o in observations if o.known_at <= as_of]
    if not eligible:
        return None, 0.0
    scores={}
    for o in eligible:
        scores[o.value]=scores.get(o.value,0.0)+max(0.0,min(1.0,o.confidence))
    value=max(scores, key=scores.get)
    total=sum(scores.values())
    return value, (scores[value]/total if total else 0.0)
