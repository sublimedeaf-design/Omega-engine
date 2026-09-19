from __future__ import annotations
import math

def calibration_error(probabilities, outcomes, bins: int=10) -> float:
    pairs=list(zip(probabilities,outcomes))
    if not pairs: raise ValueError("no rows")
    total=len(pairs); ece=0.0
    for b in range(bins):
        lo=b/bins; hi=(b+1)/bins
        bucket=[(p,y) for p,y in pairs if lo <= p < hi or (b==bins-1 and p==1)]
        if bucket:
            mp=sum(p for p,_ in bucket)/len(bucket); my=sum(y for _,y in bucket)/len(bucket)
            ece += len(bucket)/total*abs(mp-my)
    return ece

def roi(profits) -> float:
    xs=list(profits)
    if not xs: raise ValueError("no bets")
    return sum(xs)/len(xs)

def clv(bet_odds: float, closing_odds: float) -> float:
    if bet_odds <= 1 or closing_odds <= 1: raise ValueError("decimal odds must exceed 1")
    return bet_odds/closing_odds-1
