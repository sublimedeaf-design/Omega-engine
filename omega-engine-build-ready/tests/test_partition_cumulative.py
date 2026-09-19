from pathlib import Path
from omega.research.partitioned_runner import _partition_meta, _market_rows

def test_partition_meta_hive_path():
    assert _partition_meta(Path('/x/season=2024-25/league=E0/part-000.csv')) == ('2024-25','E0')

def test_market_rows_missing_file_columns(tmp_path):
    p=tmp_path/'x.csv'; p.write_text('Date,HomeTeam,AwayTeam,FTHG,FTAG\n01/08/2024,A,B,1,0\n')
    assert _market_rows(p)=={}
