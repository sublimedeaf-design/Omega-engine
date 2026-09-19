from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Iterable

import numpy as np
from scipy.optimize import minimize


@dataclass(frozen=True)
class Match:
    kickoff: datetime
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class DixonColesFit:
    teams: tuple[str, ...]
    attack: dict[str, float]
    defence: dict[str, float]
    intercept: float
    home_advantage: float
    rho: float
    decay_rate: float
    fitted_at: datetime
    objective: float
    success: bool

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        if home_team not in self.attack or away_team not in self.attack:
            raise KeyError("team was not present in training data")
        lh = math.exp(self.intercept + self.home_advantage + self.attack[home_team] + self.defence[away_team])
        la = math.exp(self.intercept + self.attack[away_team] + self.defence[home_team])
        return lh, la


def _poisson_logpmf(k: int, lam: float) -> float:
    return -lam + k * math.log(lam) - math.lgamma(k + 1)


def _tau(x: int, y: int, lh: float, la: float, rho: float) -> float:
    if (x, y) == (0, 0):
        return 1.0 - lh * la * rho
    if (x, y) == (0, 1):
        return 1.0 + lh * rho
    if (x, y) == (1, 0):
        return 1.0 + la * rho
    if (x, y) == (1, 1):
        return 1.0 - rho
    return 1.0


def fit_dixon_coles(
    matches: Iterable[Match],
    as_of: datetime,
    decay_rate: float = 0.002,
    maxiter: int = 1000,
) -> DixonColesFit:
    """Fit a time-decayed Dixon-Coles model using only matches before ``as_of``.

    ``decay_rate`` is per day. It is intentionally supplied by the caller rather
    than silently tuned on the same sample; OMEGA will choose it by walk-forward
    validation.
    """
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    data = [m for m in matches if m.kickoff < as_of]
    if not data:
        raise ValueError("no historical matches before as_of")
    teams = tuple(sorted({m.home_team for m in data} | {m.away_team for m in data}))
    if len(teams) < 2:
        raise ValueError("at least two teams are required")
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    # attack[n], defence[n], intercept, home advantage, rho
    x0 = np.zeros(2 * n + 3, dtype=float)
    mean_goals = max(0.2, sum(m.home_goals + m.away_goals for m in data) / (2 * len(data)))
    x0[2 * n] = math.log(mean_goals)
    x0[2 * n + 1] = 0.15
    x0[2 * n + 2] = -0.05

    def unpack(x: np.ndarray):
        # Identifiability: center attack and defence effects every evaluation.
        attack = x[:n] - np.mean(x[:n])
        defence = x[n:2*n] - np.mean(x[n:2*n])
        return attack, defence, x[2*n], x[2*n+1], x[2*n+2]

    def objective(x: np.ndarray) -> float:
        attack, defence, intercept, home_adv, rho = unpack(x)
        total = 0.0
        for m in data:
            age_days = max(0.0, (as_of - m.kickoff).total_seconds() / 86400.0)
            w = math.exp(-decay_rate * age_days)
            lh = math.exp(intercept + home_adv + attack[idx[m.home_team]] + defence[idx[m.away_team]])
            la = math.exp(intercept + attack[idx[m.away_team]] + defence[idx[m.home_team]])
            tau = _tau(m.home_goals, m.away_goals, lh, la, rho)
            if tau <= 0 or not math.isfinite(tau):
                return 1e12
            ll = _poisson_logpmf(m.home_goals, lh) + _poisson_logpmf(m.away_goals, la) + math.log(tau)
            total -= w * ll
        # Gentle regularization prevents sparse-team parameters exploding.
        total += 0.01 * float(np.sum(x[:2*n] ** 2))
        return total

    bounds = [(None, None)] * (2 * n + 2) + [(-0.25, 0.25)]
    result = minimize(objective, x0, method="L-BFGS-B", bounds=bounds, options={"maxiter": maxiter})
    attack, defence, intercept, home_adv, rho = unpack(result.x)
    return DixonColesFit(
        teams=teams,
        attack={t: float(attack[i]) for t, i in idx.items()},
        defence={t: float(defence[i]) for t, i in idx.items()},
        intercept=float(intercept),
        home_advantage=float(home_adv),
        rho=float(rho),
        decay_rate=float(decay_rate),
        fitted_at=as_of,
        objective=float(result.fun),
        success=bool(result.success),
    )
