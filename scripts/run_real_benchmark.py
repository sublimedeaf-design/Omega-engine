#!/usr/bin/env python3
from pathlib import Path
import sys
from omega.research.runner import run_csv_benchmark
if len(sys.argv)!=2:
    raise SystemExit('usage: run_real_benchmark.py E0_2023-24.csv')
src=Path(sys.argv[1]); out=Path('reports')/'E0_2023-24-omega-vs-b365-close.json'
r=run_csv_benchmark(src,out,min_train=120,refit_every=10)
print(out)
print('OMEGA',r['omega'])
print('B365 closing',r['bet365_closing_market'])
