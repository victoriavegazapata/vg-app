"""Fetch the last 48 h of live data for all 6 points and save it, to look at before computing anything.

Run:  python checks/fetch_live_sample.py
Saves CSV tables in data/live_sample/ and prints a short summary.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vg import settings, fetch  # noqa: E402

cfg = settings.load()
src, d = cfg["data_sources"], cfg["paths"]["data_dir"]
out = settings.APP_DIR / "data" / "live_sample"
out.mkdir(parents=True, exist_ok=True)
now = pd.Timestamp.now(tz="UTC").floor("h")
hours = pd.date_range(now - pd.Timedelta("47h"), now, freq="h")

# Gages and masks used by the 6 points
gages, masks, points = {}, {}, {**cfg["test_points"], **cfg["no_gage_points"]}
for pt in points.values():
    for key in ("gage_a", "gage_b", "gage_point"):
        if key in pt:
            gages[pt[key]["name"]] = pt[key]["site"]
    m = np.load(pt["mask_path"])
    masks.update({k.replace("_", " "): m[k].astype(bool) for k in m.files})
stage_sites = {pt["gage_point"]["name"]: pt["gage_point"]["site"] for pt in cfg["test_points"].values()}

print(f"Now (UTC): {now:%Y-%m-%d %H:%M}. Window: {hours[0]:%m-%d %H}h to {hours[-1]:%m-%d %H}h\n")

# USGS
flow, stage, last = {}, {}, {}
for name, site in gages.items():
    flow[name], last[name] = fetch.usgs_hourly(site, "00060", hours, src)
for name, site in stage_sites.items():
    stage[name], _ = fetch.usgs_hourly(site, "00065", hours, src)
flow, stage = pd.DataFrame(flow), pd.DataFrame(stage)
flow.to_csv(out / "usgs_flow_cfs.csv"); stage.to_csv(out / "usgs_gage_height_ft.csv")
print("USGS flow (cfs): hours with data out of 48, latest value, last reading time")
for name, site in gages.items():
    s = flow[name]
    lv = f"{s.dropna().iloc[-1]:,.0f}" if s.notna().any() else "none"
    lt = f"{last[name]:%m-%d %H:%M}" if last[name] is not None else "none"
    print(f"  {name:12s} {site}  {s.notna().sum():2d}/48  now {lv:>7s}  last reading {lt}")
print("USGS gage height (ft) at the 4 test points:",
      {n: (f"{s.dropna().iloc[-1]:.2f}" if s.notna().any() else "none") for n, s in stage.items()})

# MRMS
mrms = fetch.MrmsBasinMeans(masks, src).hours(hours)
mrms.to_csv(out / "mrms_basin_means_mm.csv")
got = mrms["source"].notna()
print(f"\nMRMS: {got.sum()}/48 hours posted (Pass2 {int((mrms.source == 'Pass2').sum())}, Pass1 {int((mrms.source == 'Pass1').sum())}); "
      f"last hour {mrms.index[got][-1]:%m-%d %H}h")
rain48 = mrms[[c for c in masks]].astype(float).sum()
print("  48-h rain (mm):", {k: round(v, 1) for k, v in rain48.items()})

# NWM Open Loop
reaches = {k: v for k, v in src["nwm_reach_at_point"].items()}
ol = fetch.nwm_open_loop(hours, reaches, src)
ol.to_csv(out / "nwm_open_loop_cfs.csv")
print(f"\nNWM Open Loop: {ol.notna().all(axis=1).sum()}/48 hours; last {ol.dropna().index[-1]:%m-%d %H}h")
print("  now (cfs):", {k: round(v, 1) for k, v in ol.dropna().iloc[-1].items()})

# NWM short range
cycle = fetch.latest_short_range_cycle(now, src)
sr_q, sr_p, rain_src = fetch.nwm_short_range(cycle, reaches, masks, src)
sr_q.to_csv(out / f"nwm_short_range_flow_cfs_{cycle:%Y%m%d_%H}z.csv"); sr_p.to_csv(out / f"nwm_short_range_rain_mm_{cycle:%Y%m%d_%H}z.csv")
print(f"\nNWM short range: cycle {cycle:%Y-%m-%d %H}z, {len(sr_q)} flow hours, {len(sr_p)} rain hours "
      f"({sr_q.index[0]:%m-%d %H}h to {sr_q.index[-1]:%m-%d %H}h); NWM version {rain_src} (rain = NBM since v3.1)")
print("  forecast peak flow (cfs):", {k: round(v, 1) for k, v in sr_q.max().items()})
print("  forecast total rain (mm):", {k: round(v, 1) for k, v in sr_p.sum().items()})
print(f"\nSaved in {out}")
