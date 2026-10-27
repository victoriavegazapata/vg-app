"""Gather all live inputs for the 6 points in one call (USGS, MRMS, NWM Open Loop)."""
import numpy as np
import pandas as pd

from vg import fetch

WARM_UP_H = 24  # extra hours before the 48-h window, so the 24-h rain sums and the smoothing are complete


def all_masks(cfg):
    masks = {}
    for group in ("test_points", "no_gage_points"):
        for pt in cfg[group].values():
            m = np.load(pt["mask_path"])
            masks.update({k.replace("_", " "): m[k].astype(bool) for k in m.files})
    return masks


def gages(cfg):
    out = {}
    for group in ("test_points", "no_gage_points"):
        for pt in cfg[group].values():
            for key in ("gage_a", "gage_b", "gage_point"):
                if key in pt:
                    out[pt[key]["name"]] = pt[key]["site"]
    return out


def inputs(cfg, now, window_h=48):
    """Hourly inputs from (now − window − warm-up) to now, and the last update time of each source."""
    src = cfg["data_sources"]
    hours = pd.date_range(now - pd.Timedelta(hours=window_h - 1 + WARM_UP_H), now, freq="h")
    Q, H, last = {}, {}, {}
    for name, site in gages(cfg).items():
        Q[name], last[f"USGS {name} {site}"] = fetch.usgs_hourly(site, "00060", hours, src)
    for pt in cfg["test_points"].values():
        g = pt["gage_point"]
        H[g["name"]], _ = fetch.usgs_hourly(g["site"], "00065", hours, src)
    raw = fetch.MrmsBasinMeans(all_masks(cfg), src).hours(hours)
    # Keep an MRMS value only when its coverage is high enough (same rule as the saved data)
    names = [c for c in raw.columns if c != "source" and not c.endswith("coverage")]
    P = pd.DataFrame({c: raw[c].astype(float).where(raw[f"{c} coverage"].astype(float) >= cfg["rain"]["min_coverage"])
                      for c in names})
    ol = fetch.nwm_open_loop(hours, src["nwm_reach_at_point"], src)
    last["MRMS"] = raw.index[raw["source"].notna()].max()
    last["NWM Open Loop"] = ol.dropna(how="all").index.max()
    return {"hours": hours, "Q": pd.DataFrame(Q), "H": pd.DataFrame(H), "P": P, "mrms_source": raw["source"],
            "open_loop": ol, "last_update": last}
