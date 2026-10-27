"""Nowcast: virtual-gage flow and water level from hourly flow (USGS) and rain (MRMS).

Test points:      M13 flow (Recipe 2) -> stage in ft from the HAND rating (+ datum c) and from the USGS rating.
No-gage points:   M2 range (Recipe 4) -> depth range in m above the DEM channel (Cells A5, 95).

Two display rules (the math is the same as the thesis):
- When an upstream gage has no reading, the smoothing holds its last value (as in the thesis).
  Those hours are left blank here, so the page never shows a held value as new data.
- When a flow is below the smallest flow in the HAND table, the depth is not known: it is left
  blank and flagged "below HAND table".
"""
import numpy as np
import pandas as pd

from vg import flow, stage, saved_data


def _areas(cfg, pt):
    return saved_data.mask_areas(pt["mask_path"])


def test_point(name, Q, P, Hobs, cfg):
    """Hourly nowcast table for one test point.

    Q = hourly USGS flow (cfs) by gage name, P = MRMS basin means (mm, coverage already applied),
    Hobs = hourly USGS gage height (ft) by gage name.
    """
    pt = cfg["test_points"][name]
    a, b, v = pt["gage_a"]["name"], pt["gage_b"]["name"], pt["gage_point"]["name"]
    A = _areas(cfg, pt)
    r = (A[v] - A[a] - A[b]) / (A[a] + A[b])
    S = Q[a] + Q[b]
    UP = flow.smooth_and_lag(S, pt["K_h"], pt["lag_h"])
    R, R_raw = flow.rain_ratio(P[a], P[b], P[v], A[a], A[b], A[v], cfg["rain"], cfg["rain"]["R_max_m13"])
    has_upstream = S.shift(pt["lag_h"]).notna()  # both upstream gages reported for this hour
    vg_q = flow.m13(UP, R, r, pt["c"], pt["p"]).where(has_upstream)

    rating = stage.read_usgs_rating(cfg["stage"]["usgs_ratings_file"], pt["gage_point"]["site"])
    hand = stage.HandRating(pt["hand_geometry"], pt["hand_slope"], pt["manning_n"], cfg["stage"])
    c_ft = stage.datum_offset_ft(hand, rating, pt["datum_fit_cfs"])
    ok = vg_q.notna()
    below = ok & (vg_q < hand.min_q_cfs)
    stage_hand = pd.Series(np.nan, index=vg_q.index)
    stage_usgs = pd.Series(np.nan, index=vg_q.index)
    stage_hand[ok & ~below] = hand.depth_m(vg_q[ok & ~below]) / 0.3048 + c_ft
    stage_usgs[ok] = stage.usgs_stage_ft(rating, vg_q[ok])

    return pd.DataFrame({
        "USGS observed flow cfs": Q[v],
        "upstream sum cfs": S,
        "upstream smoothed+lagged cfs": UP.where(has_upstream),
        "rain ratio R": R,
        "rain ratio R (raw, blank = R set to 1)": R_raw,
        "virtual gage flow cfs": vg_q,
        "USGS observed stage ft": Hobs[v],
        "virtual gage stage ft (HAND rating)": stage_hand,
        "virtual gage stage ft (USGS rating)": stage_usgs,
        "below HAND table": below,
    }), {"r": r, "datum c ft": c_ft, "HAND table smallest flow cfs": hand.min_q_cfs}


def no_gage_point(name, Q, P, cfg):
    """Hourly nowcast table for one point without a gage: flow range and depth range."""
    pt, ng = cfg["no_gage_points"][name], cfg["no_gage_default"]
    a, b, v = pt["gage_a"]["name"], pt["gage_b"]["name"], pt["point_mask_name"]
    A = _areas(cfg, pt)
    R, R_raw = flow.rain_ratio(P[a], P[b], P[v], A[a], A[b], A[v], cfg["rain"], cfg["rain"]["R_max_m2"])
    rng = flow.m2_range(Q[a], Q[b], R, pt["r_values"], ng)
    lim = ng["fill_gap_max_h"]
    has_upstream = (flow.fill_short_gaps(Q[a], lim) + flow.fill_short_gaps(Q[b], lim)).shift(ng["lag_h"]).notna()
    rng = rng.where(has_upstream, axis=0)

    # Depth range: smallest depth = low flow with the smallest n; largest = high flow with the largest n
    hands = [stage.HandRating(pt["hand_geometry"], pt["hand_slope"], n, cfg["stage"]) for n in pt["manning_n_options"]]
    lo, hi = pd.Series(np.nan, index=rng.index), pd.Series(np.nan, index=rng.index)
    ok = rng["low"].notna()
    d_lo = np.min([np.where(rng["low"][ok] < h.min_q_cfs, np.nan, h.depth_m(rng["low"][ok])) for h in hands], axis=0)
    d_hi = np.max([np.where(rng["high"][ok] < h.min_q_cfs, np.nan, h.depth_m(rng["high"][ok])) for h in hands], axis=0)
    lo[ok], hi[ok] = d_lo, d_hi
    # Below the table with ANY n option -> the low end of the depth range is not known
    below = ok & pd.Series(False, index=rng.index)
    below[ok] = np.any([rng["low"][ok] < h.min_q_cfs for h in hands], axis=0)
    lo[below] = np.nan

    out = pd.DataFrame({"upstream sum cfs": Q[a] + Q[b], "rain ratio R": R,
                        "rain ratio R (raw, blank = R set to 1)": R_raw})
    for col in rng.columns:
        out[f"virtual gage flow cfs, {col}"] = rng[col]
    out["depth m, low"], out["depth m, high"], out["below HAND table"] = lo, hi, below
    return out, {"r values": pt["r_values"], "Manning n options": pt["manning_n_options"],
                 "HAND table smallest depth m": hands[0].min_depth_m,
                 "HAND table smallest flow cfs (per n)": [round(h.min_q_cfs, 1) for h in hands]}
