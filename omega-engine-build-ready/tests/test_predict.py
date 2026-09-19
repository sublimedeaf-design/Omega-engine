from datetime import datetime, timezone, timedelta
from omega.models.dixon_coles import Match
from omega.predict import Fixture, predict_fixture

def test_predict_emits_probabilities_and_ignores_future():
    t=datetime(2025,1,1,tzinfo=timezone.utc)
    hist=[]
    for i in range(20):
        hist += [Match(t+timedelta(days=i), 'A','B',2,1), Match(t+timedelta(days=i), 'B','A',1,1)]
    ko=t+timedelta(days=30)
    hist.append(Match(ko+timedelta(days=1),'A','B',0,9))
    p=predict_fixture(hist,Fixture(ko,'A','B'),maxiter=100)
    assert p.probability_label == 'MODELLED'
    assert p.trained_matches == 40
    assert abs(p.probabilities['home']+p.probabilities['draw']+p.probabilities['away']-1)<1e-6
    assert p.fair_odds['home'] > 1
