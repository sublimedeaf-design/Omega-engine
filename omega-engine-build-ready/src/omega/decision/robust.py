from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from omega.market import evaluate_value

@dataclass(frozen=True)
class RobustValue:
    mean_probability: float
    lower_probability: float
    mean_ev: float
    lower_ev: float
    probability_positive_ev: float


def robust_value(probabilities, odds: float, lower_quantile: float = .10) -> RobustValue:
    ps=np.asarray(list(probabilities), dtype=float)
    if ps.size == 0 or np.any((ps <= 0)|(ps >= 1)):
        raise ValueError("probabilities must be non-empty and in (0,1)")
    evs=ps*odds-1.0
    lp=float(np.quantile(ps, lower_quantile))
    return RobustValue(float(ps.mean()), lp, float(evs.mean()), float(np.quantile(evs,lower_quantile)), float((evs>0).mean()))
