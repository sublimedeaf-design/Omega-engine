#!/usr/bin/env python3
import argparse,json
from omega.live.openligadb import fetch_matches,normalize_match
p=argparse.ArgumentParser(); p.add_argument('--league',default='bl1'); p.add_argument('--season',type=int,required=True); a=p.parse_args()
for x in fetch_matches(a.league,a.season): print(json.dumps(normalize_match(x),ensure_ascii=False))
