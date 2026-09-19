from __future__ import annotations
import math
import numpy as np
from scipy.special import gammaln


def nb_pmf(k: int, mean: float, dispersion: float) -> float:
    """NB2 PMF with Var[Y]=mean + mean^2/dispersion; Poisson as dispersion→∞."""
    if mean <= 0 or dispersion <= 0 or k < 0:
        raise ValueError("invalid negative-binomial parameters")
    r=dispersion
    p=r/(r+mean)
    logp=gammaln(k+r)-gammaln(r)-gammaln(k+1)+r*math.log(p)+k*math.log1p(-p)
    return float(math.exp(logp))


def score_matrix_nb(mean_home: float, mean_away: float, dispersion_home: float, dispersion_away: float, max_goals: int=14) -> np.ndarray:
    m=np.zeros((max_goals+1,max_goals+1), dtype=float)
    for h in range(max_goals+1):
        ph=nb_pmf(h,mean_home,dispersion_home)
        for a in range(max_goals+1):
            m[h,a]=ph*nb_pmf(a,mean_away,dispersion_away)
    return m/m.sum()
