from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PlayerValue:
    player_id: str
    attack: float
    defence: float
    minutes_reliability: float = 1.0

@dataclass(frozen=True)
class ReplacementImpact:
    delta_attack: float
    delta_defence: float
    confidence: float

def replacement_impact(starter: PlayerValue, replacement: PlayerValue) -> ReplacementImpact:
    c=max(0.,min(1., starter.minutes_reliability*replacement.minutes_reliability))
    return ReplacementImpact((starter.attack-replacement.attack)*c,(starter.defence-replacement.defence)*c,c)

def lineup_adjustment(changes: list[tuple[PlayerValue,PlayerValue]]) -> ReplacementImpact:
    impacts=[replacement_impact(a,b) for a,b in changes]
    if not impacts: return ReplacementImpact(0.,0.,1.)
    return ReplacementImpact(sum(x.delta_attack for x in impacts),sum(x.delta_defence for x in impacts),min(x.confidence for x in impacts))
