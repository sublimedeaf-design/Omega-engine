from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable

from omega.models.dixon_coles import Match, fit_dixon_coles
from omega.models.score import score_matrix, market_probabilities

@dataclass(frozen=True)
class Fixture:
    kickoff: datetime
    home_team: str
    away_team: str

@dataclass(frozen=True)
class Prediction:
    kickoff: str
    home_team: str
    away_team: str
    model: str
    probability_label: str
    trained_matches: int
    lambda_home: float
    lambda_away: float
    probabilities: dict[str, float]
    fair_odds: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


def _fair(p: float) -> float:
    return round(1.0 / p, 4) if p > 0 else float('inf')


def predict_fixture(history: Iterable[Match], fixture: Fixture, *, decay_rate: float = 0.002, maxiter: int = 300, max_goals: int = 12) -> Prediction:
    """Generate a point-in-time pre-match forecast; future matches are excluded."""
    ko = fixture.kickoff
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=timezone.utc)
    train = [m for m in history if m.kickoff < ko]
    fit = fit_dixon_coles(train, as_of=ko, decay_rate=decay_rate, maxiter=maxiter)
    if not fit.success:
        raise RuntimeError('Dixon-Coles optimizer did not converge')
    lh, la = fit.expected_goals(fixture.home_team, fixture.away_team)
    probs = market_probabilities(score_matrix(lh, la, max_goals=max_goals, rho=fit.rho))
    probs = {k: round(v, 8) for k, v in probs.items()}
    return Prediction(
        kickoff=ko.isoformat(), home_team=fixture.home_team, away_team=fixture.away_team,
        model='dixon-coles', probability_label='MODELLED', trained_matches=len(train),
        lambda_home=round(lh, 6), lambda_away=round(la, 6), probabilities=probs,
        fair_odds={k: _fair(v) for k, v in probs.items()},
    )


def predict_fixtures(history: Iterable[Match], fixtures: Iterable[Fixture], **kwargs) -> list[Prediction]:
    data=list(history)
    return [predict_fixture(data, f, **kwargs) for f in sorted(fixtures, key=lambda x: x.kickoff)]
