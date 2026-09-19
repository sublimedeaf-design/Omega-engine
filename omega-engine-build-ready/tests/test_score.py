import numpy as np
from omega.models.score import score_matrix, market_probabilities


def test_score_matrix_sums_to_one():
    m = score_matrix(1.6, 1.2, rho=-0.05)
    assert np.isclose(m.sum(), 1.0)
    assert np.all(m >= 0)


def test_joint_btts_over_is_exact_from_matrix():
    m = score_matrix(1.7, 1.4)
    p = market_probabilities(m)
    direct = sum(m[h, a] for h in range(1, m.shape[0]) for a in range(1, m.shape[1]) if h + a >= 3)
    assert np.isclose(p["btts_and_over_2_5"], direct)
    assert p["btts_and_over_2_5"] <= min(p["btts_yes"], p["over_2_5"])
