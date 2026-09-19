from datetime import datetime, timezone, timedelta
from omega.market_consensus import BookMarket, consensus_probability
from omega.data.quality import Observation, consensus
from omega.decision.robust import robust_value
from omega.models.elo import EloRatings
from omega.research.champion import ModelScore, compare
from omega.pipeline import Candidate, evaluate_candidate

def test_market_consensus_sums_one():
    p=consensus_probability([BookMarket('a',(2.0,3.5,4.0)),BookMarket('b',(1.9,3.6,4.2))])
    assert abs(sum(p)-1)<1e-12

def test_point_in_time_consensus_ignores_future():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    obs=[Observation('status','OUT','a',t,1),Observation('status','FIT','b',t+timedelta(hours=1),1)]
    assert consensus(obs,t)[0]=='OUT'

def test_robust_value_distribution():
    r=robust_value([.55,.57,.59],2.0)
    assert r.mean_ev>0 and r.probability_positive_ev==1

def test_elo_updates():
    e=EloRatings.empty(); before=e.expected_home('A','B'); e.update('A','B',2,0)
    assert e.expected_home('A','B')>before

def test_challenger_requires_all_quality_improvements():
    c=ModelScore('c',1000,.20,.60,.03); x=ModelScore('x',1000,.19,.58,.02)
    assert compare(c,x).promote

def test_pipeline_rejects_failed_stress():
    c=Candidate('f','BTTS',2.0,.65,.01,.9,(.49,.61))
    assert evaluate_candidate(c).decision=='REJECT'
