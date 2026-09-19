from __future__ import annotations
from dataclasses import dataclass
from omega.research.champion import ModelScore, compare

@dataclass(frozen=True)
class AutoPromotion:
    promote: bool
    reasons: tuple[str,...]

def decide_promotion(champion: ModelScore, challenger: ModelScore, min_predictions:int=500) -> AutoPromotion:
    d=compare(champion,challenger,min_samples=min_predictions)
    return AutoPromotion(d.promote,d.reasons)
