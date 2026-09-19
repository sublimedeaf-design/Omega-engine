from __future__ import annotations
from dataclasses import dataclass
from omega.decision.value_gate import GateConfig, GateResult, value_gate

@dataclass(frozen=True)
class Candidate:
    fixture_id: str
    market: str
    odds: float
    calibrated_probability: float
    uncertainty: float
    data_quality: float
    stress_probabilities: tuple[float,...]


def evaluate_candidate(c: Candidate, config: GateConfig = GateConfig()) -> GateResult:
    stress_min=min(c.stress_probabilities) if c.stress_probabilities else c.calibrated_probability
    decision_p=min(c.calibrated_probability, stress_min)
    return value_gate(decision_p, c.odds, c.uncertainty, c.data_quality, config)
