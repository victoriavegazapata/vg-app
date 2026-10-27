"""Re-run the method on the saved project data and compare with the thesis numbers (brief Section 8).

Run:  python checks/thesis_numbers.py
It prints each check as PASS or FAIL. Nothing is shown on the page until all pass.
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vg import settings, flow, stage, floods, saved_data  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)

# Expected values (Table1_main_results.csv, Section 8 of the brief)
EXPECTED = {
    "test B": {"Gurabo": 3.9, "Ciales": 18.0, "Loíza Y1": 18.8, "Loíza Y2": 17.3},
    "test A": {"Gurabo": 18.7, "Ciales": 14.4, "Loíza Y1": 10.4, "Loíza Y2": 10.7},
    "stage B Gurabo (USGS rating, HAND rating) ft": (0.17, 0.26),
    "Fiona": {"Arecibo junction": ("2022-09-19 04:00", 51409, 59092),
              "Río Nigua confluence": ("2022-09-18 22:00", 13496, 14820)},
}
# Peak time of Fiona at each no-gage point = upstream peak time in virtual_gage_noGage_default_peaks.csv

cfg = settings.load()
fl, rain = cfg["floods"], cfg["rain"]
T = lambda s: pd.Timestamp(s, tz="UTC")
hours = pd.date_range(fl["selection_period"][0], fl["test_b_period"][1], freq="h", tz="UTC")
sel0, sel1 = map(T, fl["selection_period"])
tb0, tb1 = map(T, fl["test_b_period"])
GRID = floods.cp_grid(fl)
results = []


def check(name, got, expected, tol):
    ok = abs(got - expected) <= tol
    results.append((name, got, expected, "PASS" if ok else "FAIL"))


# ---------------------------------------------------------------- test points (M13)
Q, P = saved_data.test_point_data(cfg, hours)
storm_stage = pd.read_csv(cfg["paths"]["data_dir"] / "usgs_stage_00065_storm_windows_4points.csv",
                          dtype={"site": str}).dropna(subset=["time"])
rating_csv = cfg["stage"]["usgs_ratings_file"]


def measured_peak_stage(site, t):
    """Highest measured gage height (on the hour) in the flood window, if ≥ 90 % of hours are there."""
    c = storm_stage[(storm_stage.site == site) & (storm_stage["peak (UTC)"] == f"{t:%Y-%m-%d %H}")]
    h = pd.Series(c.stage_ft.values, index=pd.to_datetime(c.time, utc=True)).sort_index()
    w = floods.window(h[h.index.minute == 0], t, fl)
    n_hours = fl["window_before_h"] + fl["window_after_h"] + 1
    return w.max() if len(w) >= fl["min_fraction_present"] * n_hours else np.nan


stage_rows = []
for name, pt in cfg["test_points"].items():
    a, b, v = pt["gage_a"]["name"], pt["gage_b"]["name"], pt["gage_point"]["name"]
    A = saved_data.mask_areas(pt["mask_path"])
    r = (A[v] - A[a] - A[b]) / (A[a] + A[b])
    UP = flow.smooth_and_lag(Q[a] + Q[b], pt["K_h"], pt["lag_h"])
    R6, _ = flow.rain_ratio(P[a], P[b], P[v], A[a], A[b], A[v], rain, rain["R_max_m13"])
    qv = Q[v]
    ok = UP.notna() & qv.notna()
    in_sel = ok & (hours >= sel0) & (hours <= sel1)
    in_tb = ok & (hours >= tb0) & (hours <= tb1)
    pk_sel, pk_tb = floods.find_floods(qv[in_sel], qv, fl), floods.find_floods(qv[in_tb], qv, fl)

    # Peak error of every (c, p) on every selection flood
    E = [np.array([floods.peak_error_pct(flow.m13(UP, R6, r, c, p), qv, t, fl) for t in pk_sel]) for c, p in GRID]

    # c, p learned on all selection floods must equal the config values
    c_l, p_l = GRID[floods.learn_cp(E, list(range(len(pk_sel))))]
    results.append((f"{name}: c, p learned 2020-23 = config", f"{c_l}, {p_l}", f"{pt['c']}, {pt['p']}",
                    "PASS" if (c_l, p_l) == (pt["c"], pt["p"]) else "FAIL"))

    # Test A: leave each flood out (± 10 days), learn c, p on the rest, score the left-out flood
    errA = []
    for j, t in enumerate(pk_sel):
        train = [u for u, tu in enumerate(pk_sel) if abs((tu - t) / pd.Timedelta(days=1)) > fl["leave_out_days"]]
        errA.append(E[floods.learn_cp(E, train)][j])
    check(f"{name}: M13 |peak error| test A, % ({len(pk_sel)} floods)",
          round(float(np.median(np.abs(errA))), 1), EXPECTED["test A"][name], 0.05)

    # Test B: config c, p on the independent 2025-26 floods
    M = flow.m13(UP, R6, r, pt["c"], pt["p"])
    errB = [floods.peak_error_pct(M, qv, t, fl) for t in pk_tb]
    check(f"{name}: M13 |peak error| test B, % ({len(pk_tb)} floods)",
          round(float(np.median(np.abs(errB))), 1), EXPECTED["test B"][name], 0.05)
    check(f"{name}: r from masks vs Table 2", round(r, 2),
          {"Gurabo": 0.52, "Ciales": 0.85, "Loíza Y1": 1.42, "Loíza Y2": 0.80}[name], 0.005)

    # Stage, test B: M13 peak flow → stage, vs measured USGS gage height
    site = pt["gage_point"]["site"]
    rating = stage.read_usgs_rating(rating_csv, site)
    hand = stage.HandRating(pt["hand_geometry"], pt["hand_slope"], pt["manning_n"], cfg["stage"])
    c_ft = stage.datum_offset_ft(hand, rating, pt["datum_fit_cfs"])
    for t in pk_tb:
        qm, hm = floods.window(M, t, fl).max(), measured_peak_stage(site, t)
        stage_rows.append({"point": name, "peak": t, "measured ft": hm,
                           "USGS rating err ft": float(stage.usgs_stage_ft(rating, qm)) - hm,
                           "HAND rating err ft": float(hand.depth_m(qm)) / 0.3048 + c_ft - hm})

S = pd.DataFrame(stage_rows).dropna(subset=["measured ft"])
g = S[S.point == "Gurabo"]
e_usgs, e_hand = EXPECTED["stage B Gurabo (USGS rating, HAND rating) ft"]
check(f"Gurabo: stage |error| test B, USGS rating, ft ({len(g)} floods)",
      round(float(g["USGS rating err ft"].abs().median()), 2), e_usgs, 0.005)
check(f"Gurabo: stage |error| test B, HAND rating, ft ({len(g)} floods)",
      round(float(g["HAND rating err ft"].abs().median()), 2), e_hand, 0.005)
# Other points: printed for information, compared with Table 1
T1 = {"Ciales": (0.86, 0.93), "Loíza Y1": (0.44, 0.73), "Loíza Y2": (0.48, 0.79)}
for name, (eu, eh) in T1.items():
    g = S[S.point == name]
    check(f"{name}: stage |error| test B, USGS rating, ft (Table 1)", round(float(g["USGS rating err ft"].abs().median()), 2), eu, 0.005)
    check(f"{name}: stage |error| test B, HAND rating, ft (Table 1)", round(float(g["HAND rating err ft"].abs().median()), 2), eh, 0.005)

# ---------------------------------------------------------------- points without a gage (M2 range)
ng = cfg["no_gage_default"]
for name, pt in cfg["no_gage_points"].items():
    a, b, v = pt["gage_a"]["name"], pt["gage_b"]["name"], pt["point_mask_name"]
    Qn, Pn = saved_data.no_gage_data(cfg, name, hours)
    A = saved_data.mask_areas(pt["mask_path"])
    R4, _ = flow.rain_ratio(Pn[a], Pn[b], Pn[v], A[a], A[b], A[v], rain, rain["R_max_m2"])
    rng = flow.m2_range(Qn[a], Qn[b], R4, pt["r_values"], ng)
    t_str, lo_exp, hi_exp = EXPECTED["Fiona"][name]
    t = T(t_str)
    check(f"{name}: Fiona 2022 peak, low, cfs", round(floods.window(rng["low"], t, fl).max()), lo_exp, 1)
    check(f"{name}: Fiona 2022 peak, high, cfs", round(floods.window(rng["high"], t, fl).max()), hi_exp, 1)

# ---------------------------------------------------------------- report
pd.set_option("display.width", 200)
out = pd.DataFrame(results, columns=["check", "got", "expected", "result"])
print(out.to_string(index=False))
n_fail = (out.result == "FAIL").sum()
print(f"\n{len(out) - n_fail} of {len(out)} checks pass.")
sys.exit(1 if n_fail else 0)
