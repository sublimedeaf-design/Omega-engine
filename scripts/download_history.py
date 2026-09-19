#!/usr/bin/env python3
from omega.data.football_data_bulk import download
SEASONS=['2021','2122','2223','2324','2425','2526']
DIVISIONS=['E0','E1','D1','D2','I1','I2','SP1','SP2','F1','F2','N1','B1','P1','T1']
files=download(SEASONS,DIVISIONS,'data/historical')
print(f'downloaded {len(files)} files')
