from omega.models.dynamic_state import DynamicTeamState
from omega.models.player_impact import PlayerValue,replacement_impact
from omega.ml.residual import ResidualLogit
from omega.ml.ood import MahalanobisOOD,ErrorPredictor
from omega.research.automation import decide_promotion
from omega.research.champion import ModelScore
import numpy as np

def test_dynamic_state_updates_and_uncertainty_falls():
    m=DynamicTeamState(); a=m.get('A'); b=m.update('A',1.0); c=m.update('A',1.0)
    assert b.mean>0 and c.mean>b.mean and c.variance<b.variance<a.variance

def test_replacement_impact():
    x=replacement_impact(PlayerValue('s',.4,.2,.9),PlayerValue('r',.1,.1,.8))
    assert x.delta_attack>0 and abs(x.confidence-.72)<1e-12

def test_residual_logit_learns_signal():
    X=np.array([[-2],[-1],[1],[2]],float); y=np.array([0,0,1,1])
    m=ResidualLogit(.01).fit(X,y); p=m.predict_proba([[-2],[2]])
    assert p[0]<.5<p[1]

def test_ood_and_error_predictor():
    X=np.array([[0,0],[.1,0],[0,.1],[-.1,0],[0,-.1]])
    o=MahalanobisOOD().fit(X); assert bool(o.is_ood([[10,10]])[0])
    e=ErrorPredictor().fit(X,[.5]*5,[0,1,0,1,0]); assert 0<=e.predict([[0,0]])[0]<=1

def test_champion_challenger_guardrail():
    c=ModelScore('c',600,.20,.60,.03); x=ModelScore('x',600,.19,.58,.03)
    assert decide_promotion(c,x).promote
    bad=ModelScore('b',600,.21,.57,.03); assert not decide_promotion(c,bad).promote
