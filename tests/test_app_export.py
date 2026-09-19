import json
from omega.app_export import export_value_snapshot

def test_export_filters_and_orders(tmp_path):
    rows=[
      {"kickoff":"2026-09-20T20:00:00+02:00","match":"B-C","market":"1X2","selection":"B","odds":2.1,"probability":0.52,"fair_odds":1.92,"ev":0.092,"verified":True},
      {"kickoff":"2026-09-20T18:00:00+02:00","match":"A-D","market":"BTTS","selection":"Yes","odds":1.95,"probability":0.55,"fair_odds":1.82,"ev":0.0725,"verified":True},
      {"kickoff":"2026-09-20T17:00:00+02:00","match":"X-Y","market":"O2.5","selection":"Over","odds":1.8,"probability":0.7,"fair_odds":1.43,"ev":0.26,"verified":True},
      {"kickoff":"2026-09-20T16:00:00+02:00","match":"U-V","market":"1X2","selection":"U","odds":2.2,"probability":0.6,"fair_odds":1.67,"ev":0.32,"verified":False},
    ]
    p=tmp_path/'value.json'; result=export_value_snapshot(rows,p)
    assert [x['match'] for x in result['value']]==['A-D','B-C']
    assert json.loads(p.read_text())['value'][0]['odds']==1.95
