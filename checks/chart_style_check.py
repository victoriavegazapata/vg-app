"""Checks for the NWS-style charts (Chart_Style_Brief_NWS, Section 5). Drawing only, so nothing here changes a number.

1. NWS category stages in config.yaml = the saved NWPS replies.
2. Right-axis table reproduces the current USGS rating; flow on that rating at each category stage vs the NWPS
   category flow (reported, not forced).
3. Points without a gage: right axis = HAND rating at the config Manning n; depth m × 3.28084 = ft.

Run:  python checks/chart_style_check.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vg import results, settings, stage  # noqa: E402

cfg = settings.load()
extras, info = results.chart_extras(cfg)
ok = True


def check(name, passed, detail):
    global ok
    ok &= passed
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")


print("Test points: rating flow at each NWS category stage vs the NWPS category flow")
for name, pt in cfg["test_points"].items():
    ch = extras[results._slug(name)]
    nw, ar = ch["nwps"], ch["axis_rating"]
    print(f"{name} ({nw['lid']}, USGS {pt['gage_point']['site']}, {ar['label']})")
    same = {k: v["stage"] for k, v in nw["categories"].items()} == pt["nws_stages_ft"]
    check("config stages = NWPS stages", same, pt["nws_stages_ft"])
    # the right-axis table must give the rating's own flow at the table stages
    r = stage.read_usgs_rating(cfg["stage"]["usgs_ratings_file"], pt["gage_point"]["site"]).sort_values("s")
    s = np.array(ar["stage_ft"])
    err = np.max(np.abs(np.array(ar["q_cfs"]) - np.interp(s, r.s, r.q)))
    check("right-axis table = USGS rating", err < 0.01, f"largest difference {err:.3f} cfs over {len(s)} stages")
    for k in ("action", "minor", "moderate", "major"):
        c = nw["categories"][k]
        q = float(np.interp(c["stage"], s, ar["q_cfs"]))
        print(f"      {k:9s} {c['stage']:>5} ft   rating {q:>9,.0f} cfs   NWPS {c['flow']:>7,} cfs   difference {100 * (q / c['flow'] - 1):+6.1f} %")
    rec = nw["record"]
    crest = f"{rec['stage']} ft, {rec['date']}" if rec else "not drawn (config nws_chart.hide_record_crest)"
    print(f"      record crest: {crest}; low threshold {nw['low_ft']} ft; datum {nw['datum']['abbrev']} {nw['datum']['value_ft']} ft; reach {nw['reach_id']}")

print("\nPoints without a gage: right-axis HAND rating and m → ft")
ft = cfg["nws_chart"]["m_to_ft"]
check("1 m = 3.28084 ft in config", ft == 3.28084, ft)
for name, pt in cfg["no_gage_points"].items():
    ch = extras[results._slug(name)]
    ar = ch["axis_rating"]
    n = cfg["nws_chart"]["right_axis_n"][name]
    print(f"{name} ({ar['label']})")
    check("no NWS categories", ch["nwps"] is None, "no bands drawn")
    h = stage.HandRating(pt["hand_geometry"], pt["hand_slope"], n, cfg["stage"])
    # depth (ft) → flow from the table must equal the HAND rating at depth ft / 3.28084 m
    s = np.array(ar["stage_ft"])
    err = np.max(np.abs(np.array(ar["q_cfs"]) - np.interp(s / ft, h.depth, h.q_cfs)))
    check("right-axis table = HAND rating", err < 0.01, f"largest difference {err:.3f} cfs over {len(s)} depths")
    for d_m in (h.min_depth_m, 0.5, 1.0, 2.0):
        print(f"      {d_m:5.2f} m = {d_m * ft:6.2f} ft → {float(np.interp(d_m, h.depth, h.q_cfs)):>9,.0f} cfs")

print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
