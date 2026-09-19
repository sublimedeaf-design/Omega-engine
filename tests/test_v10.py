from datetime import datetime, timezone
from omega.production import decide
from omega.research.report import summarize
from omega.backtest import ProbabilisticPrediction

def test_production_decision_rejects_below_min_odds():
    d=decide('f','btts','yes',.7,1.5,{'x':1})
    assert d.decision=='REJECT'
    assert len(d.fingerprint)==64

def test_report_summary():
    now=datetime.now(timezone.utc)
    s=summarize([ProbabilisticPrediction(now,'a',.8,1),ProbabilisticPrediction(now,'b',.2,0)])
    assert s.n==2 and s.brier < .05 and s.logloss < .3
