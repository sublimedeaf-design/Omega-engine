from __future__ import annotations
from dataclasses import dataclass


def implied_probability(decimal_odds: float) -> float:
    if decimal_odds <= 1.0:
        raise ValueError("decimal odds must be > 1")
    return 1.0 / decimal_odds


def devig_proportional(decimal_odds: list[float]) -> list[float]:
    raw = [implied_probability(o) for o in decimal_odds]
    s = sum(raw)
    if s <= 0:
        raise ValueError("invalid market")
    return [p / s for p in raw]


@dataclass(frozen=True)
class ValueDecision:
    probability: float
    offered_odds: float
    fair_odds: float
    break_even_probability: float
    edge: float
    ev: float


def evaluate_value(probability: float, offered_odds: float) -> ValueDecision:
    if not 0 < probability < 1:
        raise ValueError("probability must be between 0 and 1")
    be = implied_probability(offered_odds)
    return ValueDecision(
        probability=probability,
        offered_odds=offered_odds,
        fair_odds=1.0 / probability,
        break_even_probability=be,
        edge=probability - be,
        ev=probability * offered_odds - 1.0,
    )
