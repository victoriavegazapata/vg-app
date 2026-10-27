"""Water level from flow (Recipe 5): HAND channel geometry + Manning equation."""
import numpy as np
import pandas as pd


def manning_n_from_slope(S, n_rule):
    """Slope-class rule: flat channels get a fixed n, steep ones n = a·S^b."""
    if S < n_rule["slope_break"]:
        return n_rule["n_flat"]
    return n_rule["a"] * S ** n_rule["b"]


class HandRating:
    """Synthetic rating Q(h) = 35.3147·(1/n)·A(h)·R(h)^(2/3)·S^(1/2), read backwards to get h for a flow."""

    def __init__(self, geometry_csv, slope, n, stage_cfg):
        geo = pd.read_csv(geometry_csv)
        g = stage_cfg["depth_grid_m"]
        self.depth = np.linspace(g["start"], g["stop"], g["count"])
        area = np.interp(self.depth, geo.depth_m, geo.area_m2)
        radius = np.interp(self.depth, geo.depth_m, geo.hyd_radius_m)
        self.q_cfs = (1 / n) * area * radius ** (2 / 3) * np.sqrt(slope) * stage_cfg["cfs_per_m3s"]
        # Smallest flow the HAND table can describe (at its first depth row). Below it the depth is not known.
        self.min_depth_m = float(geo.depth_m.iloc[0])
        self.min_q_cfs = float(np.interp(self.min_depth_m, self.depth, self.q_cfs))

    def depth_m(self, Q):
        """Depth above the DEM channel (m) for a flow (cfs)."""
        return np.interp(np.asarray(Q, float), self.q_cfs, self.depth)


def read_usgs_rating(rating_csv, site):
    """USGS rating (exsa) saved in the project: stage (ft) vs flow (cfs), sorted by flow."""
    u = pd.read_csv(rating_csv, dtype={"site": str})
    u = u[u.site == site].rename(columns={"stage_ft": "s", "q_cfs": "q"})
    return u.drop_duplicates("q").sort_values("q").query("q > 0")[["s", "q"]]


def usgs_stage_ft(rating, Q):
    """Stage (ft) from the USGS rating for a flow (cfs)."""
    return np.interp(np.asarray(Q, float), rating.q.values, rating.s.values)


def datum_offset_ft(hand, rating, fit_cfs):
    """c = median(USGS rating stage − HAND stage) over 60 flows spread on a log scale in fit_cfs (Cell 124)."""
    q0, q1 = fit_cfs
    Qs = np.geomspace(max(rating.q.min(), q0), q1, 60)
    return float(np.median(usgs_stage_ft(rating, Qs) - hand.depth_m(Qs) / 0.3048))
