from datetime import datetime, timezone
import numpy as np
from omega.models.negative_binomial import score_matrix_nb
from omega.models.score import market_probabilities
from omega.calibration import IsotonicCalibrator
from omega.decision import value_gate, GateConfig, stress_probabilities
from omega.research import clv, calibration_error

def test_nb_matrix_and_markets():
    m=score_matrix_nb(1.6,1.2,5,5)
    assert abs(m.sum()-1)<1e-12
    p=market_probabilities(m)
    assert abs(p['home']+p['draw']+p['away']-1)<1e-12

def test_isotonic_monotone():
    c=IsotonicCalibrator().fit([.1,.2,.3,.4,.5,.6],[0,0,1,0,1,1])
    q=c.predict([.15,.25,.35,.45,.55])
    assert np.all(np.diff(q)>=-1e-12)

def test_gate_rejects_and_passes():
    cfg=GateConfig(min_ev=.01,min_edge=.01,max_uncertainty=.08,min_data_quality=.7)
    assert value_gate(.65,2.0,.03,.9,cfg).decision=='VALUE'
    assert value_gate(.65,1.8,.03,.9,cfg).reason=='ODDS_BELOW_MINIMUM'
    assert value_gate(.65,2.0,.10,.9,cfg).reason=='UNCERTAINTY'

def test_stress_and_metrics():
    s=stress_probabilities(.6,[lambda p:p-.05,lambda p:p+.02])
    assert abs(s.worst_probability-.55)<1e-12
    assert round(clv(2.1,2.0),4)==.05
    assert calibration_error([.1,.9],[0,1]) <= .1 + 1e-12
