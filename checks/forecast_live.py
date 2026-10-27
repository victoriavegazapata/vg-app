"""Run the EXPERIMENTAL forecast on live data and print the numbers (no page yet).

Run:  python checks/forecast_live.py
Saves one CSV per point in data/forecast_live/.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vg import settings, live, fetch, forecast  # noqa: E402

cfg = settings.load()
src = cfg["data_sources"]
now = pd.Timestamp.now(tz="UTC").floor("h")
data = live.inputs(cfg, now)
cycle = fetch.latest_short_range_cycle(now, src)
sr_flow, sr_rain, version = fetch.nwm_short_range(cycle, src["nwm_reach_at_point"], live.all_masks(cfg), src)
out = settings.APP_DIR / "data" / "forecast_live"
out.mkdir(parents=True, exist_ok=True)
f = lambda x, d=0: "—" if pd.isna(x) else f"{x:,.{d}f}"

print("EXPERIMENTAL FORECAST. Research prototype, NOT validated, method pending review. Not an official NWS product.")
print(f"Issued {now:%Y-%m-%d %H}:00 UTC. NWM short-range cycle {cycle:%Y-%m-%d %H}z ({version}), "
      f"forecast to {sr_flow.index.max():%m-%d %H}h. Last MRMS hour {data['P'].dropna(how='all').index.max():%m-%d %H}h.")
print("Known weakness: " + cfg["forecast"]["known_weakness"] + "\n")

rows = []
for name in cfg["test_points"]:
    tab, info = forecast.test_point(name, data, sr_rain, sr_flow, cfg, now)
    tab.to_csv(out / f"{name}.csv")
    q = tab["virtual gage flow cfs"]
    tp, _, dry = forecast.peak(tab, "virtual gage flow cfs")
    known = tab[tab["hour type"] == forecast.KNOWN]
    rows.append({"point": name, "last upstream reading": f"{info['last upstream reading hour']:%m-%d %H}h",
                 "upstream-measured hours after now": len(known),
                 "VG peak cfs": f(q.max()), "VG peak time": f"{tp:%m-%d %H}h", "peak hour type": tab.at[tp, "hour type"],
                 "DRY-DAY FLAG": "YES" if dry else "no",
                 "VG peak stage ft (HAND)": "below table" if tab.at[tp, "below HAND table"] else f(tab.at[tp, "virtual gage stage ft (HAND rating)"], 2),
                 "VG peak stage ft (USGS rating)": f(tab.at[tp, "virtual gage stage ft (USGS rating)"], 2),
                 "NWM SR peak cfs": f(tab["NWM short-range cfs"].max()),
                 "NWM SR peak time": f"{tab['NWM short-range cfs'].idxmax():%m-%d %H}h",
                 "R max": f(tab["rain ratio R"].max(), 2)})
print("TEST POINTS")
print(pd.DataFrame(rows).to_string(index=False))

rows = []
for name in cfg["no_gage_points"]:
    tab, info = forecast.no_gage_point(name, data, sr_rain, sr_flow, cfg, now)
    tab.to_csv(out / f"{name}.csv")
    hi = tab["virtual gage flow cfs, high"]
    tp, _, dry = forecast.peak(tab, "virtual gage flow cfs, high")
    rows.append({"point": name, "last upstream reading": f"{info['last upstream reading hour']:%m-%d %H}h",
                 "VG peak range cfs": f"{f(tab.at[tp, 'virtual gage flow cfs, low'])}–{f(hi.max())}",
                 "typical-error band cfs": f"{f(tab.at[tp, 'virtual gage flow cfs, band low'])}–{f(tab.at[tp, 'virtual gage flow cfs, band high'])}",
                 "VG peak time": f"{tp:%m-%d %H}h", "peak hour type": tab.at[tp, "hour type"],
                 "DRY-DAY FLAG": "YES" if dry else "no",
                 "NWM SR peak cfs": f(tab["NWM short-range cfs"].max()),
                 "NWM SR peak time": f"{tab['NWM short-range cfs'].idxmax():%m-%d %H}h"})
print("\nPOINTS WITHOUT A GAGE")
print(pd.DataFrame(rows).to_string(index=False))

print("\nGURABO, first 12 forecast hours")
g = pd.read_csv(out / "Gurabo.csv", index_col=0, parse_dates=True).head(12)
print(g[["hour type", "rain source", "upstream sum cfs", "rain ratio R", "virtual gage flow cfs",
         "virtual gage stage ft (HAND rating)", "NWM short-range cfs"]].round(2).to_string())
print("\nDRY-DAY FLAG note shown on the page: " + cfg["forecast"]["dry_day_peak_note"])
print(f"\nSaved in {out}")
