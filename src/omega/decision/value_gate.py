from __future__ import annotations
from dataclasses import dataclass
from omega.market import evaluate_value

@dataclass(frozen=True)
class GateConfig:
    min_odds: float=1.90
    min_ev: float=0.03
    min_edge: float=0.02
    max_uncertainty: float=0.08
    min_data_quality: float=0.70

@dataclass(frozen=True)
class GateResult:
    decision: str
    reason: str
    decision_probability: float
    ev: float
    edge: float


def robust_probability(calibrated_probability: float, uncertainty: float) -> float:
    if not 0 <= uncertainty < 1: raise ValueError("uncertainty out of range")
    return max(1e-6, min(1-1e-6, calibrated_probability-uncertainty))


def value_gate(calibrated_probability: float, offered_odds: float, uncertainty: float, data_quality: float, config: GateConfig=GateConfig()) -> GateResult:
    if not 0 < calibrated_probability < 1: raise ValueError('probability must be between 0 and 1')
    if not offered_odds > 1: raise ValueError('decimal odds must be > 1')
    if not 0 <= data_quality <= 1: raise ValueError('data_quality must be in [0,1]')
    if config.min_odds <= 1 or config.min_ev < 0 or config.min_edge < 0 or not 0 <= config.max_uncertainty < 1 or not 0 <= config.min_data_quality <= 1: raise ValueError('invalid GateConfig')
    p=robust_probability(calibrated_probability, uncertainty)
    v=evaluate_value(p, offered_odds)
    if offered_odds < config.min_odds: return GateResult("REJECT","ODDS_BELOW_MINIMUM",p,v.ev,v.edge)
    if data_quality < config.min_data_quality: return GateResult("REJECT","DATA_QUALITY",p,v.ev,v.edge)
    if uncertainty > config.max_uncertainty: return GateResult("REJECT","UNCERTAINTY",p,v.ev,v.edge)
    if v.edge < config.min_edge: return GateResult("REJECT","EDGE",p,v.ev,v.edge)
    if v.ev < config.min_ev: return GateResult("REJECT","EV",p,v.ev,v.edge)
    return GateResult("VALUE","PASS",p,v.ev,v.edge)
