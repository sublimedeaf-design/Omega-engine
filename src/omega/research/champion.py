from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelScore:
    name: str
    n: int
    brier: float
    log_loss: float
    calibration_error: float

@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    reasons: tuple[str, ...]


def compare(champion: ModelScore, challenger: ModelScore, min_samples: int = 500) -> PromotionDecision:
    reasons=[]
    if challenger.n < min_samples:
        reasons.append(f"insufficient samples: {challenger.n} < {min_samples}")
    if challenger.brier >= champion.brier:
        reasons.append("Brier score not improved")
    if challenger.log_loss >= champion.log_loss:
        reasons.append("log-loss not improved")
    if challenger.calibration_error > champion.calibration_error:
        reasons.append("calibration worsened")
    return PromotionDecision(not reasons, tuple(reasons))
