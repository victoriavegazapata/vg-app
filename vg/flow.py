"""Flow at a virtual gage: M13 at test points (Recipe 2), M2 at points without a gage (Recipe 4).

All inputs are hourly pandas Series on the same UTC time index.
Flow in cfs, rain in mm, areas in km² (number of NWM 1-km cells).
"""
import numpy as np
import pandas as pd


def smooth_and_lag(S, K, lag):
    """Smooth the upstream sum with weight 1/(K+1), then shift it later by `lag` hours."""
    U = S if K == 0 else S.ewm(alpha=1 / (K + 1), adjust=False).mean()
    return U.shift(lag)


def rain_ratio(P_a, P_b, P_v, A_a, A_b, A_v, rain_cfg, R_max):
    """Rain ratio R = 24-h rain on the ungaged part ÷ 24-h rain upstream.

    Returns (R limited to 0-R_max with blanks set to 1, raw R before limits).
    """
    upstream = (P_a * A_a + P_b * A_b) / (A_a + A_b)
    ungaged = ((P_v * A_v - P_a * A_a - P_b * A_b) / (A_v - A_a - A_b)).clip(lower=0)
    n, n_min = rain_cfg["sum_hours"], rain_cfg["sum_min_hours"]
    sum_up = upstream.rolling(n, min_periods=n_min).sum()
    sum_ug = ungaged.rolling(n, min_periods=n_min).sum()
    R_raw = (sum_ug / sum_up).where(sum_up >= rain_cfg["min_upstream_sum_mm"])
    return R_raw.clip(0, R_max).fillna(1.0), R_raw


def m13(UP, R, r, c, p):
    """M13 = UP × (1 + r·c·R^p)."""
    return UP * (1 + r * c * R ** p)


def fill_short_gaps(s, max_h):
    """Fill gaps of ≤ max_h hours inside the record by a straight line."""
    return s.interpolate(method="time", limit=max_h, limit_area="inside")


def m2_range(Q_a, Q_b, R, r_values, ng_cfg):
    """No-gage default M2 = UP × (1 + r·R), once per area ratio r.

    Returns a DataFrame with one column per r, plus 'low', 'high',
    and the typical-error band 'band low' / 'band high' (± 30.1 %).
    """
    lim = ng_cfg["fill_gap_max_h"]
    UP = smooth_and_lag(fill_short_gaps(Q_a, lim) + fill_short_gaps(Q_b, lim), ng_cfg["K_h"], ng_cfg["lag_h"])
    out = pd.DataFrame({name: UP * (1 + r * R) for name, r in r_values.items()})
    e = ng_cfg["typical_error"]
    out["low"], out["high"] = out.min(axis=1), out.max(axis=1)
    out["band low"], out["band high"] = out["low"] * (1 - e), out["high"] * (1 + e)
    return out
