"""Run the nowcast on live data and print the numbers (no page yet).

Run:  python checks/nowcast_live.py
Saves one CSV per point in data/nowcast_live/.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vg import settings, live, nowcast  # noqa: E402

cfg = settings.load()
now = pd.Timestamp.now(tz="UTC").floor("h")
data = live.inputs(cfg, now)
window = data["hours"][live.WARM_UP_H:]  # the 48 h shown on the page
out = settings.APP_DIR / "data" / "nowcast_live"
out.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 20)
f = lambda x, d=0: "—" if pd.isna(x) else f"{x:,.{d}f}"

print(f"Nowcast at {now:%Y-%m-%d %H}:00 UTC. Window {window[0]:%m-%d %H}h → {window[-1]:%m-%d %H}h.")
print("Research prototype, NOT validated, method pending review. Not an official NWS product.\n")

rows = []
for name in cfg["test_points"]:
    tab, info = nowcast.test_point(name, data["Q"], data["P"], data["H"], cfg)
    tab["NWM Open Loop cfs"] = data["open_loop"][name]
    tab = tab.loc[window]
    tab.to_csv(out / f"{name}.csv")
    t = tab["virtual gage flow cfs"].last_valid_index()  # latest hour the virtual gage can give
    rows.append({"point": name, "latest VG hour": f"{t:%m-%d %H}h", "VG flow cfs": f(tab.at[t, "virtual gage flow cfs"]),
                 "USGS flow cfs": f(tab.at[t, "USGS observed flow cfs"]), "NWM OL cfs": f(tab.at[t, "NWM Open Loop cfs"]),
                 "rain ratio R": f(tab.at[t, "rain ratio R"], 2),
                 "VG stage ft HAND": "below table" if tab.at[t, "below HAND table"] else f(tab.at[t, "virtual gage stage ft (HAND rating)"], 2),
                 "VG stage ft USGS rating": f(tab.at[t, "virtual gage stage ft (USGS rating)"], 2),
                 "USGS stage ft": f(tab.at[t, "USGS observed stage ft"], 2),
                 "VG hours /48": int(tab["virtual gage flow cfs"].notna().sum()), "datum c ft": f(info["datum c ft"], 2),
                 "HAND table min cfs": f(info["HAND table smallest flow cfs"])})
print("TEST POINTS (M13 flow; stage from HAND rating + datum c, and from the current USGS rating)")
print(pd.DataFrame(rows).to_string(index=False))

def depth_text(row, d0):
    lo = f"< {d0:.2f}" if row["below HAND table"] else f(row["depth m, low"], 2)
    hi = f"< {d0:.2f}" if pd.isna(row["depth m, high"]) else f(row["depth m, high"], 2)
    return lo if lo == hi else f"{lo} to {hi}"


rows = []
for name in cfg["no_gage_points"]:
    tab, info = nowcast.no_gage_point(name, data["Q"], data["P"], cfg)
    tab["NWM Open Loop cfs"] = data["open_loop"][name]
    tab = tab.loc[window]
    tab.to_csv(out / f"{name}.csv")
    t = tab["virtual gage flow cfs, low"].last_valid_index()
    c = lambda k: tab.at[t, f"virtual gage flow cfs, {k}"]
    rows.append({"point": name, "latest VG hour": f"{t:%m-%d %H}h", "VG flow range cfs": f"{f(c('low'))}–{f(c('high'))}",
                 "typical-error band cfs": f"{f(c('band low'))}–{f(c('band high'))}", "NWM OL cfs": f(tab.at[t, "NWM Open Loop cfs"]),
                 "rain ratio R": f(tab.at[t, "rain ratio R"], 2),
                 "depth range m": depth_text(tab.loc[t], info["HAND table smallest depth m"]),
                 "VG hours /48": int(tab["virtual gage flow cfs, low"].notna().sum())})
print("\nPOINTS WITHOUT A GAGE (M2 range with 2 area ratios; depth above the DEM channel, all Manning n options)")
print(pd.DataFrame(rows).to_string(index=False))

print("\nLAST UPDATE OF EACH SOURCE (UTC)")
for k, v in data["last_update"].items():
    print(f"  {k:28s} {v:%Y-%m-%d %H:%M}" if v is not None else f"  {k:28s} none")

print("\nGURABO, last 12 hours (to see the pieces of M13)")
g = pd.read_csv(out / "Gurabo.csv", index_col=0, parse_dates=True).tail(12)
print(g[["upstream sum cfs", "upstream smoothed+lagged cfs", "rain ratio R", "virtual gage flow cfs", "USGS observed flow cfs",
         "NWM Open Loop cfs", "virtual gage stage ft (HAND rating)", "USGS observed stage ft"]].round(2).to_string())
print(f"\nSaved in {out}")
