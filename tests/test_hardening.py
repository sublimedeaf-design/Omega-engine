import pytest
from omega.decision.value_gate import value_gate, GateConfig
from omega.health import healthcheck

def test_healthcheck_core_is_ok():
    r=healthcheck()
    assert r.ok and r.numpy and r.scipy and r.schema_present

def test_value_gate_rejects_invalid_inputs():
    with pytest.raises(ValueError): value_gate(0.5, 1.0, 0, 1)
    with pytest.raises(ValueError): value_gate(1.1, 2.0, 0, 1)
    with pytest.raises(ValueError): value_gate(0.5, 2.0, 0, 1.1)
    with pytest.raises(ValueError): value_gate(0.5, 2.0, 0, 1, GateConfig(min_odds=1.0))

def test_partition_csv_streaming(tmp_path):
    from omega.data.partition import partition_football_data_csv, iter_partition_files
    src=tmp_path/'x.csv'
    src.write_text('Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nE0,01/08/2024,A,B,1,0\nE0,02/08/2024,C,D,2,2\nE0,01/08/2025,A,C,0,1\n',encoding='utf-8')
    m=partition_football_data_csv(src,tmp_path/'parts',max_rows_per_file=1)
    assert m.rows==3 and m.partitions==3
    assert len(list(iter_partition_files(tmp_path/'parts')))==3
    assert (tmp_path/'parts'/'manifest.json').exists()

def test_partition_rejects_bad_key(tmp_path):
    import pytest
    from omega.data.partition import partition_football_data_csv
    src=tmp_path/'x.csv'; src.write_text('Date\n01/08/2024\n')
    with pytest.raises(ValueError): partition_football_data_csv(src,tmp_path/'p',partition_by=('bad',))
