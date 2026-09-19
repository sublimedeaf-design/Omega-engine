from __future__ import annotations
import json, urllib.request

BASE='https://api.openligadb.de'
def fetch_matches(league:str, season:int, timeout:float=15):
    url=f'{BASE}/getmatchdata/{league}/{season}'
    with urllib.request.urlopen(url,timeout=timeout) as r: return json.load(r)

def normalize_match(x:dict):
    t1=x.get('team1') or {}; t2=x.get('team2') or {}
    return {'provider':'openligadb','provider_fixture_id':str(x.get('matchID')),'kickoff':x.get('matchDateTimeUTC') or x.get('matchDateTime'), 'home':t1.get('teamName'),'away':t2.get('teamName'),'raw':x}
