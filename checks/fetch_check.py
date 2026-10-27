"""Check the fetch module: download a few past hours and compare with the saved project files.

Run:  python checks/fetch_check.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vg import settings, fetch  # noqa: E402

cfg = settings.load()
src, d = cfg["data_sources"], cfg["paths"]["data_dir"]
T = lambda s: pd.Timestamp(s, tz="UTC")
read = lambda f: pd.read_csv(d / f, index_col=0, parse_dates=True)


def all_masks():
    masks = {}
    for f in ("basin_masks_1km.npz", "basin_masks_loiza_1km.npz", "basin_masks_arecibo_1km.npz", "basin_masks_nigua_1km.npz"):
        m = np.load(d / f)
        masks.update({k.replace("_", " "): m[k].astype(bool) for k in m.files})
    return masks


def compare(label, new, saved):
    diff = (new - saved).abs()
    print(f"  {label}: {int(new.notna().sum())} hours fetched, largest difference {diff.max():.4g}")


# 1) USGS: 2026-10-03 → 10-05 vs saved hourly flow
print("1) USGS hourly flow vs saved files")
hours = pd.date_range("2026-10-03", "2026-10-05 23:00", freq="h", tz="UTC")
s6, sl = read("usgs_flow_6stations_2025_2026.csv"), read("usgs_flow_loiza_5stations_2020_2026.csv")
for name, site, saved in (("Gurabo", "50057000", s6), ("HWY 183", "50051800", sl)):
    q, _ = fetch.usgs_hourly(site, "00060", hours, src)
    compare(f"{name} {site}", q, saved[name].reindex(hours))

# 2) MRMS: the 3 rainiest saved hours at Gurabo in 2025-26, all 21 basins
print("2) MRMS basin means vs saved files")
masks = all_masks()
mrms = fetch.MrmsBasinMeans(masks, src)
saved = pd.concat([read(f) for f in ("mrms_6basins_hourly_2025_2026.csv",)], axis=1)
other = {f: read(f) for f in ("mrms_loiza_hourly_2020_2026.csv", "mrms_arecibo_hourly_2020_2026.csv", "mrms_nigua_hourly_2020_2026.csv")}
for t in saved["Gurabo"].nlargest(3).index:
    row = mrms.hour(t)
    worst = 0.0
    for name in masks:
        for tab in [saved, *other.values()]:
            if name in tab.columns and t in tab.index:
                worst = max(worst, abs(row[name] - tab.loc[t, name]))
    print(f"  {t:%Y-%m-%d %H}h ({row['source']}): Gurabo {row['Gurabo']:.2f} mm (saved {saved.loc[t, 'Gurabo']:.2f}); "
          f"largest difference over 21 basins {worst:.2g} mm")

# 3) NWM Open Loop: compare with saved file if the old hours are still on the server
print("3) NWM Open Loop vs saved files")
reaches = {"Gurabo": 800034059, "Ciales": 800037673}
hours = pd.date_range("2026-10-05 00:00", periods=3, freq="h", tz="UTC")
ol = fetch.nwm_open_loop(hours, reaches, src)
sv = read("nwm_openloop_6reaches_hourly_2025_2026.csv").reindex(hours)
if ol.notna().any().any():
    for n in reaches:
        compare(f"{n} reach {reaches[n]}", ol[n], sv[n])
else:
    print("  old hours no longer on the NWM server; checked with live data only")
