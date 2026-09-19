from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class State:
    mean: float = 0.0
    variance: float = 1.0

class DynamicTeamState:
    """Scalar Bayesian/Kalman-style latent team-strength state.

    Observations are opponent-adjusted performance signals on a log-strength scale.
    This is deliberately small and auditable; richer state vectors are challengers.
    """
    def __init__(self, process_variance: float=.03, observation_variance: float=.25):
        if process_variance <= 0 or observation_variance <= 0: raise ValueError
        self.q=process_variance; self.r=observation_variance; self.states={}
    def get(self, team: str) -> State: return self.states.get(team, State())
    def update(self, team: str, observation: float, obs_variance: float|None=None) -> State:
        prior=self.get(team); pv=prior.variance+self.q; r=self.r if obs_variance is None else obs_variance
        k=pv/(pv+r); mean=prior.mean+k*(observation-prior.mean); var=(1-k)*pv
        s=State(mean,var); self.states[team]=s; return s
    def expected_multiplier(self, team: str) -> float: return math.exp(self.get(team).mean)
