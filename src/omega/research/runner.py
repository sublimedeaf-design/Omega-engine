from __future__ import annotations
from pathlib import Path
import csv, json, math
from datetime import datetime, timezone
from omega.models.dixon_coles import Match, fit_dixon_coles
from omega.models.score import score_matrix, market_probabilities

DATE_FORMATS=("%d/%m/%Y","%d/%m/%y","%Y-%m-%d")
def _date(s):
    for fmt in DATE_FORMATS:
        try:return datetime.strptime(s.strip(),fmt).replace(tzinfo=timezone.utc)
        except ValueError:pass
    raise ValueError(s)

def _devig(odds):
    q=[1.0/x for x in odds]; z=sum(q); return [x/z for x in q]

def _multiclass_brier(ps,y): return sum((p-(1.0 if j==y else 0.0))**2 for j,p in enumerate(ps))
def _logloss(ps,y): return -math.log(max(1e-12,min(1-1e-12,ps[y])))
def _ece(conf,correct,bins=10):
    n=len(conf); out=0.0
    for b in range(bins):
        lo,hi=b/bins,(b+1)/bins
        ids=[i for i,p in enumerate(conf) if lo<=p<hi or (b==bins-1 and p==1)]
        if ids: out += len(ids)/n*abs(sum(conf[i] for i in ids)/len(ids)-sum(correct[i] for i in ids)/len(ids))
    return out

def _summary(preds,ys):
    conf=[max(p) for p in preds]; correct=[int(max(range(3),key=lambda j:p[j])==y) for p,y in zip(preds,ys)]
    return {'n':len(ys),'multiclass_brier':sum(_multiclass_brier(p,y) for p,y in zip(preds,ys))/len(ys),
            'logloss':sum(_logloss(p,y) for p,y in zip(preds,ys))/len(ys),'top_class_ece':_ece(conf,correct)}

def run_csv_benchmark(csv_path, report_path, min_train=120, refit_every=1, decay_rate=0.002):
    raw=[]
    with open(csv_path,newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            req=('Date','HomeTeam','AwayTeam','FTHG','FTAG')
            if not all(r.get(k) not in (None,'') for k in req): continue
            m=Match(_date(r['Date']),r['HomeTeam'].strip(),r['AwayTeam'].strip(),int(r['FTHG']),int(r['FTAG']))
            raw.append((m,r))
    raw.sort(key=lambda x:x[0].kickoff)
    omega=[]; market=[]; ys=[]; details=[]; fit=None
    for i in range(min_train,len(raw)):
        target,row=raw[i]; train=[m for m,_ in raw[:i] if m.kickoff < target.kickoff]
        teams={t for m in train for t in (m.home_team,m.away_team)}
        if target.home_team not in teams or target.away_team not in teams: continue
        close=[]
        for k,fb in [('B365CH','B365H'),('B365CD','B365D'),('B365CA','B365A')]:
            v=row.get(k) or row.get(fb)
            try:v=float(v)
            except (TypeError,ValueError):v=0
            close.append(v)
        if any(x<=1 for x in close): continue
        if fit is None or (i-min_train)%refit_every==0:
            fit=fit_dixon_coles(train,as_of=target.kickoff,decay_rate=decay_rate,maxiter=300)
        lh,la=fit.expected_goals(target.home_team,target.away_team)
        mp=market_probabilities(score_matrix(lh,la,rho=fit.rho))
        op=[mp['home'],mp['draw'],mp['away']]; op=[x/sum(op) for x in op]
        bp=_devig(close)
        y=0 if target.home_goals>target.away_goals else 1 if target.home_goals==target.away_goals else 2
        omega.append(op); market.append(bp); ys.append(y)
        details.append({'kickoff':target.kickoff.isoformat(),'home':target.home_team,'away':target.away_team,'result':['H','D','A'][y],
                        'omega':op,'bet365_close_odds':close,'bet365_devig':bp})
    if not ys: raise ValueError('no benchmarkable rows')
    payload={'title':'OMEGA chronological 1X2 benchmark','metadata':{'source':str(csv_path),'min_train':min_train,'decay_rate':decay_rate,'closing_fallback':'B365C* then B365*'},
             'omega':_summary(omega,ys),'bet365_closing_market':_summary(market,ys),'details':details}
    p=Path(report_path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    return payload
