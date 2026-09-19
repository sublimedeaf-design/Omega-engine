from __future__ import annotations
from pathlib import Path
from collections import defaultdict
import csv, json, re
from omega.data.partition import iter_partition_files
from omega.data.football_data_csv import load_results, _date
from omega.models.dixon_coles import fit_dixon_coles
from omega.models.score import score_matrix, market_probabilities
from omega.backtest import ProbabilisticPrediction
from omega.market import devig_proportional
from omega.research.report import summarize

_PART_RE = re.compile(r'(?:^|/)season=([^/]+)/league=([^/]+)/')

def _partition_meta(fp: Path):
    s=fp.as_posix()+'/'
    m=_PART_RE.search(s)
    if not m: return ('unknown','unknown')
    return m.group(1),m.group(2)

def _market_rows(fp: Path):
    out={}
    with fp.open(newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try:
                dt=_date(r.get('Date',''))
                key=(dt,r.get('HomeTeam','').strip(),r.get('AwayTeam','').strip())
                # Prefer closing Bet365 when present, then ordinary Bet365.
                cols=('B365CH','B365CD','B365CA') if all(r.get(c) for c in ('B365CH','B365CD','B365CA')) else ('B365H','B365D','B365A')
                if all(r.get(c) not in (None,'') for c in cols):
                    odds=[float(r[c]) for c in cols]
                    if all(o>1 for o in odds): out[key]=devig_proportional(odds)[0]
            except Exception: pass
    return out

def run_partitioned_benchmarks(root, report_dir, min_train=120, refit_every=1, decay_rate=0.002):
    """Leakage-safe cumulative walk-forward benchmark across partitioned seasons.

    Partitions are processed league-by-league and season-by-season. Earlier
    seasons remain in the training history; a season boundary never resets the
    model. This is intentionally different from benchmarking each shard in
    isolation, which would discard historical information and bias comparisons.
    """
    root=Path(root); out=Path(report_dir); out.mkdir(parents=True,exist_ok=True)
    groups=defaultdict(list)
    for fp in iter_partition_files(root):
        season,league=_partition_meta(fp); groups[league].append((season,fp))
    league_results=[]; all_dc=[]; all_market=[]
    for league, items in sorted(groups.items()):
        items.sort(key=lambda x:(x[0],str(x[1])))
        history=[]; dc_rows=[]; market_rows=[]; fit=None; since_refit=0; seen_files=[]
        for season,fp in items:
            seen_files.append(str(fp)); events=load_results(fp); mkt=_market_rows(fp)
            for target in events:
                # Strict point-in-time boundary; same-timestamp matches are excluded.
                train=[m for m in history if m.kickoff < target.kickoff]
                teams={x.home_team for x in train}|{x.away_team for x in train}
                if len(train)>=min_train and target.home_team in teams and target.away_team in teams:
                    if fit is None or since_refit>=refit_every:
                        fit=fit_dixon_coles(train,as_of=target.kickoff,decay_rate=decay_rate,maxiter=300); since_refit=0
                    lh,la=fit.expected_goals(target.home_team,target.away_team)
                    p=market_probabilities(score_matrix(lh,la,rho=fit.rho))['home_win']
                    fid=f'{target.home_team}-{target.away_team}-{target.kickoff.date()}'
                    y=int(target.home_goals>target.away_goals)
                    row=ProbabilisticPrediction(target.kickoff,fid,p,y); dc_rows.append(row); all_dc.append(row); since_refit+=1
                    mp=mkt.get((target.kickoff,target.home_team,target.away_team))
                    if mp is not None:
                        mr=ProbabilisticPrediction(target.kickoff,fid,mp,y); market_rows.append(mr); all_market.append(mr)
                history.append(target)
        models={}
        if dc_rows: models['dixon_coles_home_win']=summarize(dc_rows).__dict__
        if market_rows: models['market_devig_home_win']=summarize(market_rows).__dict__
        lr={'league':league,'files':seen_files,'historical_matches':len(history),'models':models}
        (out/f'league-{re.sub(r"[^A-Za-z0-9_.-]+","_",league)}.json').write_text(json.dumps(lr,indent=2,default=str),encoding='utf-8')
        league_results.append(lr)
    aggregate={'dixon_coles_home_win':summarize(all_dc).__dict__ if all_dc else None,
               'market_devig_home_win':summarize(all_market).__dict__ if all_market else None}
    summary={'root':str(root),'leagues':len(groups),'files_seen':sum(len(v) for v in groups.values()),'aggregate':aggregate,'items':league_results}
    (out/'partitioned-summary.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')
    return summary
