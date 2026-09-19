from datetime import datetime, timedelta, timezone
import math
from omega.models.dixon_coles import Match, fit_dixon_coles


def test_fit_uses_only_past_and_produces_positive_expected_goals():
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    matches = []
    for i in range(30):
        matches.append(Match(t0 + timedelta(days=i), "A", "B", 2, 1))
        matches.append(Match(t0 + timedelta(days=i, hours=1), "B", "A", 1, 1))
    # This future outlier must not influence the fit.
    matches.append(Match(t0 + timedelta(days=200), "A", "B", 20, 0))
    fit = fit_dixon_coles(matches, t0 + timedelta(days=100), decay_rate=0.0)
    lh, la = fit.expected_goals("A", "B")
    assert fit.success
    assert lh > 0 and la > 0
    assert lh < 10 and la < 10
    assert math.isfinite(fit.objective)
