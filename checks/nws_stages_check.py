"""Check that the NWS stages in config.yaml match the saved NWPS replies (inputs/nwps_raw/).

Run:  python checks/nws_stages_check.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vg import settings  # noqa: E402

cfg = settings.load()
ok = True
for name, pt in cfg["test_points"].items():
    site = pt["gage_point"]["site"]
    j = json.load(open(cfg["paths"]["inputs_dir"] / "nwps_raw" / f"{site}.json"))
    nwps = {k: j["flood"]["categories"][k]["stage"] for k in pt["nws_stages_ft"]}
    same = nwps == pt["nws_stages_ft"] and j["lid"] == pt["nws_lid"] and j["flood"]["stageUnits"] == "ft"
    ok &= same
    print(f"{'PASS' if same else 'FAIL'}  {name:9s} {site} {pt['nws_lid']}  config {pt['nws_stages_ft']}  NWPS {nwps}")
sys.exit(0 if ok else 1)
