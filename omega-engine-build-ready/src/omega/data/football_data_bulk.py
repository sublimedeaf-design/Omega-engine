from __future__ import annotations
import pathlib, urllib.request

BASE='https://www.football-data.co.uk/mmz4281/{season}/{division}.csv'
def download(seasons,divisions,out_dir):
    out=pathlib.Path(out_dir); out.mkdir(parents=True,exist_ok=True); saved=[]
    for season in seasons:
      for div in divisions:
        dest=out/f'{season}_{div}.csv'
        try:
          urllib.request.urlretrieve(BASE.format(season=season,division=div),dest)
          if dest.stat().st_size>1000: saved.append(dest)
          else: dest.unlink(missing_ok=True)
        except Exception: dest.unlink(missing_ok=True)
    return saved
