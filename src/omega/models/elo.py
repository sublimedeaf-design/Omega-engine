from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass
class EloRatings:
    ratings: dict[str, float]
    k: float = 20.0
    home_advantage: float = 55.0
    base: float = 1500.0

    @classmethod
    def empty(cls, **kwargs):
        return cls({}, **kwargs)

    def rating(self, team: str) -> float:
        return self.ratings.get(team, self.base)

    def expected_home(self, home: str, away: str) -> float:
        diff = self.rating(home) + self.home_advantage - self.rating(away)
        return 1.0 / (1.0 + 10.0 ** (-diff / 400.0))

    def update(self, home: str, away: str, home_goals: int, away_goals: int) -> None:
        exp = self.expected_home(home, away)
        actual = 1.0 if home_goals > away_goals else 0.5 if home_goals == away_goals else 0.0
        margin = max(1.0, math.log1p(abs(home_goals-away_goals)))
        delta = self.k * margin * (actual-exp)
        self.ratings[home] = self.rating(home) + delta
        self.ratings[away] = self.rating(away) - delta
