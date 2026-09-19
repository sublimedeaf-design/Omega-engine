import csv
from omega.research.runner import run_csv_benchmark

def test_benchmark_compares_full_1x2_to_closing_market(tmp_path):
    p=tmp_path/'x.csv'; teams=['A','B','C','D']
    with p.open('w',newline='') as f:
        w=csv.writer(f); w.writerow(['Date','HomeTeam','AwayTeam','FTHG','FTAG','B365H','B365D','B365A','B365CH','B365CD','B365CA'])
        for i in range(32):
            h=teams[i%4]; a=teams[(i+1)%4]; hg=(i*3)%4; ag=(i*5+1)%3
            w.writerow([f'{1+i%28:02d}/{1+(i//28):02d}/2023',h,a,hg,ag,2.4,3.3,2.8,2.3,3.4,2.9])
    out=run_csv_benchmark(p,tmp_path/'r.json',min_train=12,refit_every=4)
    assert out['omega']['n']==out['bet365_closing_market']['n']>0
    assert {'multiclass_brier','logloss','top_class_ece'} <= set(out['omega'])
    assert out['details'][0]['bet365_close_odds']==[2.3,3.4,2.9]
