from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class StressResult:
    base_probability: float
    stressed_probabilities: tuple[float,...]
    worst_probability: float
    spread: float


def stress_probabilities(base_probability: float, scenarios: list[Callable[[float], float]]) -> StressResult:
    vals=tuple(max(0.0,min(1.0,float(fn(base_probability)))) for fn in scenarios)
    allv=(base_probability,)+vals
    return StressResult(base_probability,vals,min(allv),max(allv)-min(allv))
