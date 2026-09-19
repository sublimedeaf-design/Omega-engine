from __future__ import annotations
import argparse, json
from omega.research.runner import run_csv_benchmark
from omega.health import healthcheck
from omega.data.partition import partition_football_data_csv
from omega.research.partitioned_runner import run_partitioned_benchmarks
from omega.app_export import export_value_snapshot
from omega.predict import Fixture, predict_fixtures
from omega.data.football_data_csv import load_results
from datetime import datetime, timezone


def main():
    p=argparse.ArgumentParser(prog='omega',description='OMEGA football forecasting/value engine')
    sp=p.add_subparsers(dest='cmd',required=True)
    sp.add_parser('health')
    part=sp.add_parser('partition'); part.add_argument('csv'); part.add_argument('output'); part.add_argument('--league'); part.add_argument('--max-rows',type=int,default=5000)
    pb=sp.add_parser('benchmark-partitions'); pb.add_argument('root'); pb.add_argument('--report-dir',default='reports/partitions'); pb.add_argument('--min-train',type=int,default=120); pb.add_argument('--refit-every',type=int,default=1)
    ex=sp.add_parser('export-app'); ex.add_argument('input_json'); ex.add_argument('output_json')
    pr=sp.add_parser('predict'); pr.add_argument('history_csv'); pr.add_argument('fixtures_json'); pr.add_argument('--output'); pr.add_argument('--decay-rate',type=float,default=0.002)
    b=sp.add_parser('benchmark'); b.add_argument('csv'); b.add_argument('--report',default='omega-benchmark.json'); b.add_argument('--min-train',type=int,default=120); b.add_argument('--refit-every',type=int,default=1)
    args=p.parse_args()
    if args.cmd=='health':
        r=healthcheck().to_dict(); print(json.dumps(r,indent=2)); raise SystemExit(0 if r['ok'] else 1)
    if args.cmd=='partition':
        print(json.dumps(partition_football_data_csv(args.csv,args.output,args.league,max_rows_per_file=args.max_rows).to_dict(),indent=2)); return
    if args.cmd=='benchmark-partitions':
        print(json.dumps(run_partitioned_benchmarks(args.root,args.report_dir,args.min_train,args.refit_every),indent=2,default=str)); return
    if args.cmd=='export-app':
        rows=json.loads(open(args.input_json,encoding='utf-8').read())
        print(json.dumps(export_value_snapshot(rows,args.output_json),indent=2)); return
    if args.cmd=='predict':
        raw=json.loads(open(args.fixtures_json,encoding='utf-8').read())
        def dt(x):
            d=datetime.fromisoformat(x.replace('Z','+00:00')); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        fixtures=[Fixture(dt(r['kickoff']),r['home_team'],r['away_team']) for r in raw]
        out=[x.to_dict() for x in predict_fixtures(load_results(args.history_csv),fixtures,decay_rate=args.decay_rate)]
        payload=json.dumps(out,indent=2)
        if args.output: open(args.output,'w',encoding='utf-8').write(payload+'\n')
        print(payload); return
    if args.cmd=='benchmark':
        out=run_csv_benchmark(args.csv,args.report,args.min_train,args.refit_every)
        print(json.dumps(out,indent=2))
if __name__=='__main__': main()
