"""Flood rule and peak error, used by the checks (Section 8 of the brief)."""
import numpy as np
import pandas as pd


def window(s, t, fl):
    """The hours from −24 h to +48 h around a peak time t."""
    return s[t - pd.Timedelta(hours=fl["window_before_h"]): t + pd.Timedelta(hours=fl["window_after_h"])]


def find_floods(q, q_full, fl):
    """USGS peaks ≥ 1,000 cfs, ≥ 3 days apart, with ≥ 90 % of the window hours present.

    q      = observed flow, only the hours allowed for picking peaks
    q_full = the whole observed record (used to check the hours present)
    """
    o, peaks = q.dropna(), []
    gap = pd.Timedelta(days=fl["min_days_apart"])
    while len(o) and o.max() >= fl["min_peak_cfs"]:
        t = o.idxmax()
        peaks.append(t)
        o = o[(o.index < t - gap) | (o.index > t + gap)]
    return [t for t in peaks if window(q_full, t, fl).notna().mean() >= fl["min_fraction_present"]]


def peak_error_pct(estimate, observed, t, fl):
    """(max estimate in window − USGS peak) ÷ USGS peak, in %."""
    return 100 * (window(estimate, t, fl).max() / window(observed, t, fl).max() - 1)


def cp_grid(fl):
    g = fl["c_grid"]
    cs = np.round(np.arange(g["start"], g["stop"] + 0.01, g["step"]), 2)
    return [(c, p) for c in cs for p in fl["p_grid"]]


def learn_cp(errors_by_cp, flood_idx):
    """Pick the (c, p) with the smallest median |peak error| over the given floods (first one wins a tie)."""
    scores = [np.median(np.abs(e[flood_idx])) for e in errors_by_cp]
    return int(np.argmin(scores))
