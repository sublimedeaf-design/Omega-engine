from __future__ import annotations
from dataclasses import dataclass
from omega.market import devig_proportional

@dataclass(frozen=True)
class BookMarket:
    bookmaker: str
    odds: tuple[float, ...]
    weight: float = 1.0


def consensus_probability(markets: list[BookMarket]) -> tuple[float,...]:
    if not markets: raise ValueError("no markets")
    n=len(markets[0].odds)
    if any(len(m.odds)!=n for m in markets): raise ValueError("outcome mismatch")
    acc=[0.0]*n; total=0.0
    for m in markets:
        p=devig_proportional(list(m.odds)); w=max(0.0,m.weight)
        total += w
        for i,x in enumerate(p): acc[i]+=w*x
    if total<=0: raise ValueError("zero total weight")
    return tuple(x/total for x in acc)
