from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from omega.decision.value_gate import GateConfig, value_gate
from omega.storage.db import input_fingerprint

@dataclass(frozen=True)
class ProductionDecision:
    prediction_id: str
    fixture_id: str
    created_at: datetime
    market: str
    selection: str
    probability: float
    odds: float
    fair_odds: float
    edge: float
    ev: float
    decision: str
    fingerprint: str


def decide(fixture_id, market, selection, probability, odds, payload, uncertainty=0.0, data_quality=1.0, config=None):
    config=config or GateConfig()
    r=value_gate(probability,odds,uncertainty,data_quality,config)
    return ProductionDecision(str(uuid.uuid4()),fixture_id,datetime.now(timezone.utc),market,selection,probability,odds,1.0/r.decision_probability,r.edge,r.ev,r.decision,input_fingerprint(payload))
