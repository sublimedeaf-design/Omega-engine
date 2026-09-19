from __future__ import annotations
import math
import numpy as np


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        raise ValueError("lambda must be > 0")
    return math.exp(-lam) * lam**k / math.factorial(k)


def dixon_coles_tau(x: int, y: int, lh: float, la: float, rho: float) -> float:
    if (x, y) == (0, 0): return 1 - lh * la * rho
    if (x, y) == (0, 1): return 1 + lh * rho
    if (x, y) == (1, 0): return 1 + la * rho
    if (x, y) == (1, 1): return 1 - rho
    return 1.0


def score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 12, rho: float = 0.0) -> np.ndarray:
    """Return normalized Dixon-Coles adjusted score probability matrix."""
    if max_goals < 2:
        raise ValueError("max_goals must be >= 2")
    m = np.zeros((max_goals + 1, max_goals + 1), dtype=float)
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson_pmf(h, lambda_home) * poisson_pmf(a, lambda_away)
            m[h, a] = p * dixon_coles_tau(h, a, lambda_home, lambda_away, rho)
    if np.any(m < 0):
        raise ValueError("rho creates negative probabilities")
    return m / m.sum()


def market_probabilities(m: np.ndarray) -> dict[str, float]:
    h_idx, a_idx = np.indices(m.shape)
    total = h_idx + a_idx
    return {
        "home": float(m[h_idx > a_idx].sum()),
        "draw": float(m[h_idx == a_idx].sum()),
        "away": float(m[h_idx < a_idx].sum()),
        "btts_yes": float(m[(h_idx >= 1) & (a_idx >= 1)].sum()),
        "over_2_5": float(m[total >= 3].sum()),
        "btts_and_over_2_5": float(m[(h_idx >= 1) & (a_idx >= 1) & (total >= 3)].sum()),
    }
