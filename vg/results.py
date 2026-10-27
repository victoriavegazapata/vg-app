"""Write results: turn the nowcast and forecast tables into one data file the page reads (site/data/latest.json).

The nowcast and the forecast are kept in separate parts of the file, so the page never joins them into one line.
"""
import json
import math

import numpy as np
import pandas as pd

from vg import fetch, forecast, live, nowcast


def _num(x, d=2):
    """A number for the file, or null when there is no value."""
    if x is None or (isinstance(x, float) and math.isnan(x)) or pd.isna(x):
        return None
    return round(float(x), d)


def _series(s, d=2):
    return [_num(v, d) for v in s]


def _local(times, cfg):
    off = pd.Timedelta(hours=cfg["local_time"]["utc_offset_h"])
    return [(t + off).strftime("%Y-%m-%dT%H:%M") for t in times]


def _when(t, cfg):
    return None if t is None or pd.isna(t) else _local([pd.Timestamp(t)], cfg)[0]


def _slug(name):
    return name.lower().replace("í", "i").replace(" ", "-")


def build(cfg, now):
    src = cfg["data_sources"]
    data = live.inputs(cfg, now)
    cycle = fetch.latest_short_range_cycle(now, src)
    sr_flow, sr_rain, version = fetch.nwm_short_range(cycle, src["nwm_reach_at_point"], live.all_masks(cfg), src)
    window = data["hours"][live.WARM_UP_H:]
    lu = data["last_update"]
    points = []

    for name, pt in cfg["test_points"].items():
        nc, info = nowcast.test_point(name, data["Q"], data["P"], data["H"], cfg)
        nc = nc.loc[window]
        ol = data["open_loop"][name].reindex(window)
        fc, finfo = forecast.test_point(name, data, sr_rain, sr_flow, cfg, now)
        t_vg = nc["virtual gage flow cfs"].last_valid_index()
        t_obs = nc["USGS observed flow cfs"].last_valid_index()
        tp, qp, dry = forecast.peak(fc, "virtual gage flow cfs")
        gauges = [pt["gage_a"], pt["gage_b"], pt["gage_point"]]
        points.append({
            "id": _slug(name), "name": name, "kind": "test", "lat_lon": pt["lat_lon"],
            "description": f"Virtual gage at USGS {pt['gage_point']['site']} {pt['gage_point']['name']}, from upstream gages "
                           f"{pt['gage_a']['site']} {pt['gage_a']['name']} + {pt['gage_b']['site']} {pt['gage_b']['name']}",
            "method": f"M13, K {pt['K_h']} h, lag {pt['lag_h']} h, c {pt['c']}, p {pt['p']}, r {info['r']:.2f}",
            "nws": {"lid": pt["nws_lid"], "stages_ft": pt["nws_stages_ft"]},
            "nowcast": {
                "t": _local(window, cfg),
                "usgs_q": _series(nc["USGS observed flow cfs"], 1), "vg_q": _series(nc["virtual gage flow cfs"], 1),
                "nwm_ol_q": _series(ol, 1),
                "usgs_h": _series(nc["USGS observed stage ft"]), "vg_h_hand": _series(nc["virtual gage stage ft (HAND rating)"]),
                "vg_h_usgs": _series(nc["virtual gage stage ft (USGS rating)"]),
                "below_table": [bool(x) for x in nc["below HAND table"]],
                "now": {
                    "vg_time": _when(t_vg, cfg), "vg_q": _num(nc.at[t_vg, "virtual gage flow cfs"], 0) if t_vg is not None else None,
                    "vg_h_hand": _num(nc.at[t_vg, "virtual gage stage ft (HAND rating)"]) if t_vg is not None else None,
                    "vg_h_usgs": _num(nc.at[t_vg, "virtual gage stage ft (USGS rating)"]) if t_vg is not None else None,
                    "usgs_time": _when(t_obs, cfg), "usgs_q": _num(nc.at[t_obs, "USGS observed flow cfs"], 0) if t_obs is not None else None,
                    "usgs_h": _num(nc["USGS observed stage ft"].dropna().iloc[-1]) if nc["USGS observed stage ft"].notna().any() else None,
                    "nwm_ol_time": _when(ol.last_valid_index(), cfg), "nwm_ol_q": _num(ol.dropna().iloc[-1], 0) if ol.notna().any() else None,
                },
            },
            "last_update": {**{f"USGS {g['site']} {g['name']}": _when(lu[f"USGS {g['name']} {g['site']}"], cfg) for g in gauges},
                            "MRMS rain": _when(lu["MRMS"], cfg), "NWM Open Loop": _when(lu["NWM Open Loop"], cfg)},
            "forecast": {
                "t": _local(fc.index, cfg), "vg_q": _series(fc["virtual gage flow cfs"], 1),
                "vg_h_hand": _series(fc["virtual gage stage ft (HAND rating)"]), "vg_h_usgs": _series(fc["virtual gage stage ft (USGS rating)"]),
                "nwm_sr_q": _series(fc["NWM short-range cfs"], 1),
                "hour_type": list(fc["hour type"]), "dry_day": [bool(x) for x in fc["R is dry-day default"]],
                "peak": {"time": _when(tp, cfg), "vg_q": _num(qp, 0), "dry_day": dry, "hour_type": fc.at[tp, "hour type"],
                         "vg_h_hand": _num(fc.at[tp, "virtual gage stage ft (HAND rating)"]),
                         "vg_h_usgs": _num(fc.at[tp, "virtual gage stage ft (USGS rating)"])},
                "nwm_sr_peak": {"time": _when(fc["NWM short-range cfs"].idxmax(), cfg), "q": _num(fc["NWM short-range cfs"].max(), 0)},
            },
        })

    for name, pt in cfg["no_gage_points"].items():
        nc, info = nowcast.no_gage_point(name, data["Q"], data["P"], cfg)
        nc = nc.loc[window]
        ol = data["open_loop"][name].reindex(window)
        fc, finfo = forecast.no_gage_point(name, data, sr_rain, sr_flow, cfg, now)
        t_vg = nc["virtual gage flow cfs, low"].last_valid_index()
        tp, qp, dry = forecast.peak(fc, "virtual gage flow cfs, high")
        col = lambda df, k: df[f"virtual gage flow cfs, {k}"]
        gauges = [pt["gage_a"], pt["gage_b"]]
        points.append({
            "id": _slug(name), "name": name, "kind": "no_gage", "lat_lon": pt["lat_lon"],
            "description": f"No gage here. Estimated from upstream gages {pt['gage_a']['site']} {pt['gage_a']['name']} + "
                           f"{pt['gage_b']['site']} {pt['gage_b']['name']}",
            "method": "No-gage default M2, K 1 h, lag 1 h, two area ratios r = "
                      + " / ".join(f"{v:.3f}" for v in pt["r_values"].values())
                      + "; Manning n " + " / ".join(str(n) for n in pt["manning_n_options"]),
            "hand_min_depth_m": info["HAND table smallest depth m"],
            "nowcast": {
                "t": _local(window, cfg),
                "vg_low": _series(col(nc, "low"), 1), "vg_high": _series(col(nc, "high"), 1),
                "band_low": _series(col(nc, "band low"), 1), "band_high": _series(col(nc, "band high"), 1),
                "nwm_ol_q": _series(ol, 1),
                "depth_low": _series(nc["depth m, low"]), "depth_high": _series(nc["depth m, high"]),
                "below_table": [bool(x) for x in nc["below HAND table"]],
                "now": {"vg_time": _when(t_vg, cfg),
                        "vg_low": _num(col(nc, "low")[t_vg], 0), "vg_high": _num(col(nc, "high")[t_vg], 0),
                        "band_low": _num(col(nc, "band low")[t_vg], 0), "band_high": _num(col(nc, "band high")[t_vg], 0),
                        "depth_low": _num(nc.at[t_vg, "depth m, low"]), "depth_high": _num(nc.at[t_vg, "depth m, high"]),
                        "below_table": bool(nc.at[t_vg, "below HAND table"]),
                        "nwm_ol_time": _when(ol.last_valid_index(), cfg), "nwm_ol_q": _num(ol.dropna().iloc[-1], 0) if ol.notna().any() else None},
            },
            "last_update": {**{f"USGS {g['site']} {g['name']}": _when(lu[f"USGS {g['name']} {g['site']}"], cfg) for g in gauges},
                            "MRMS rain": _when(lu["MRMS"], cfg), "NWM Open Loop": _when(lu["NWM Open Loop"], cfg)},
            "forecast": {
                "t": _local(fc.index, cfg),
                "vg_low": _series(col(fc, "low"), 1), "vg_high": _series(col(fc, "high"), 1),
                "band_low": _series(col(fc, "band low"), 1), "band_high": _series(col(fc, "band high"), 1),
                "depth_low": _series(fc["depth m, low"]), "depth_high": _series(fc["depth m, high"]),
                "nwm_sr_q": _series(fc["NWM short-range cfs"], 1),
                "hour_type": list(fc["hour type"]), "dry_day": [bool(x) for x in fc["R is dry-day default"]],
                "peak": {"time": _when(tp, cfg), "vg_low": _num(col(fc, "low")[tp], 0), "vg_high": _num(qp, 0),
                         "band_low": _num(col(fc, "band low")[tp], 0), "band_high": _num(col(fc, "band high")[tp], 0),
                         "dry_day": dry, "hour_type": fc.at[tp, "hour type"]},
                "nwm_sr_peak": {"time": _when(fc["NWM short-range cfs"].idxmax(), cfg), "q": _num(fc["NWM short-range cfs"].max(), 0)},
            },
        })

    return {
        "generated": _when(pd.Timestamp.now(tz="UTC"), cfg), "now": _when(now, cfg),
        "local_time": cfg["local_time"]["name"], "method_version": cfg["method_version"],
        "status_label": cfg["status_label"], "low_flow_note": cfg["low_flow_note"], "recipes_url": cfg["recipes_url"],
        "palette": cfg["palette"],
        "nws_stages": {"source": cfg["nws_stages"]["source"], "labels": cfg["nws_stages"]["labels"],
                       "show": cfg["nws_stages"]["show_on_stage_charts"]},
        "forecast_info": {"nwm_cycle": _when(cycle, cfg), "nwm_cycle_utc": f"{cycle:%Y-%m-%d %H}z", "nwm_version": version,
                          "known_weakness": " ".join(cfg["forecast"]["known_weakness"].split()),
                          "dry_day_note": " ".join(cfg["forecast"]["dry_day_peak_note"].split()),
                          "dry_day_marker_note": cfg["forecast"]["dry_day_marker_note"],
                          "reliable_horizon_h": cfg["forecast"]["reliable_horizon_h"],
                          "horizon_label": cfg["forecast"]["horizon_label"],
                          "upstream_rule": cfg["forecast"]["upstream_after_last_reading"],
                          "rain_rule": cfg["forecast"]["rain_after_last_mrms"]},
        "points": points,
    }


def write(result, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))
