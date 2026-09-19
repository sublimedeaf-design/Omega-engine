from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime
import csv, json, hashlib
from .football_data_csv import _date

@dataclass(frozen=True)
class PartitionManifest:
    source: str
    output_dir: str
    rows: int
    partitions: int
    skipped_rows: int
    partition_by: tuple[str, ...]
    files: tuple[str, ...]
    sha256: str

    def to_dict(self): return asdict(self)


def _season(dt: datetime) -> str:
    y=dt.year if dt.month >= 7 else dt.year-1
    return f"{y}-{str(y+1)[-2:]}"


def partition_football_data_csv(source: str | Path, output_dir: str | Path,
                                league: str | None = None,
                                partition_by: tuple[str, ...] = ('season','league'),
                                max_rows_per_file: int = 5000) -> PartitionManifest:
    """Stream a Football-Data CSV into small Hive-style CSV partitions.

    Does not load the complete dataset in memory. Supported partition keys:
    season, league, year, month. Raw columns are retained and normalized
    metadata columns (_omega_*) are appended.
    """
    if max_rows_per_file < 1: raise ValueError('max_rows_per_file must be >= 1')
    allowed={'season','league','year','month'}
    if not partition_by or any(k not in allowed for k in partition_by):
        raise ValueError(f'partition_by must use {sorted(allowed)}')
    source=Path(source); root=Path(output_dir); root.mkdir(parents=True,exist_ok=True)
    handles={}; writers={}; counts={}; files=[]; rows=skipped=0
    digest=hashlib.sha256()
    try:
        with source.open(newline='',encoding='utf-8-sig') as f:
            reader=csv.DictReader(f)
            if not reader.fieldnames or 'Date' not in reader.fieldnames:
                raise ValueError('CSV must contain Date')
            fields=list(reader.fieldnames)+['_omega_season','_omega_league','_omega_year','_omega_month']
            for raw in reader:
                try: dt=_date(raw.get('Date',''))
                except Exception:
                    skipped+=1; continue
                lg=(league or raw.get('Div') or raw.get('League') or 'unknown').strip()
                meta={'season':_season(dt),'league':lg,'year':str(dt.year),'month':f'{dt.month:02d}'}
                p=root
                for k in partition_by: p=p/f'{k}={meta[k]}'
                key=str(p); idx=counts.get(key,0)//max_rows_per_file
                file_key=(key,idx)
                if file_key not in writers:
                    p.mkdir(parents=True,exist_ok=True)
                    fp=p/f'part-{idx:05d}.csv'
                    h=fp.open('w',newline='',encoding='utf-8')
                    w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
                    handles[file_key]=h; writers[file_key]=w; files.append(str(fp.relative_to(root)))
                out=dict(raw); out.update({f'_omega_{k}':v for k,v in meta.items()})
                writers[file_key].writerow(out); counts[key]=counts.get(key,0)+1; rows+=1
                digest.update(json.dumps(out,sort_keys=True,separators=(',',':')).encode())
    finally:
        for h in handles.values(): h.close()
    manifest=PartitionManifest(str(source),str(root),rows,len(files),skipped,partition_by,tuple(files),digest.hexdigest())
    (root/'manifest.json').write_text(json.dumps(manifest.to_dict(),indent=2),encoding='utf-8')
    return manifest


def iter_partition_files(root: str | Path):
    yield from sorted(Path(root).glob('**/part-*.csv'))
