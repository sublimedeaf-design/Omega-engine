from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from omega.backtest import walk_forward, brier_score, log_loss


@dataclass
class Event:
    id: str
    t: datetime
    y: int


def test_walk_forward_never_exposes_future():
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    events = [Event(str(i), t0 + timedelta(days=i), i % 2) for i in range(8)]

    def predictor(train, target):
        assert all(e.t < target.t for e in train)
        return sum(e.y for e in train) / len(train)

    rows = walk_forward(events, 3, predictor, lambda e: e.y, lambda e: e.id, lambda e: e.t)
    assert len(rows) == 5
    assert 0 <= brier_score(rows) <= 1
    assert log_loss(rows) >= 0
