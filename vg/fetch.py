"""Fetch live data: USGS flow and gage height, MRMS rain basin means, NWM Open Loop and short-range forecast.

Only downloads and reshapes the data into hourly tables. No method math here.
Reading rules copied from the notebook (Cells 32, 47, 49b, 83, 84).
"""
import gzip
import io
import os
import time

import eccodes
import h5py
import numpy as np
import pandas as pd
import requests
from pyproj import Transformer

session = requests.Session()
EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
M3S_TO_CFS = 35.3147
MAX_WAIT_S = 120  # if USGS asks to wait longer than this, stop with a clear message


class RateLimited(RuntimeError):
    """USGS says too many requests from this computer in the last hour."""


def _get(url, params=None, tries=5, headers=None):
    """Download with a few retries. Returns None when the file does not exist (404)."""
    for k in range(tries):
        try:
            r = session.get(url, params=params, headers=headers, timeout=(20, 90))
            if r.status_code == 404:
                return None
            if r.status_code == 429:  # too many requests: wait only if the wait is short
                wait = int(r.headers.get("Retry-After", 30))
                if wait > MAX_WAIT_S:
                    raise RateLimited(f"USGS request limit reached; it asks to wait {wait} s. Try again later "
                                      "or set a free USGS API key in the environment variable USGS_API_KEY.")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if k == tries - 1:
                raise
            time.sleep(3 * (k + 1))
    raise IOError(f"No answer from {url}")


# ---------------------------------------------------------------- USGS

def usgs_readings(site, parameter, start, end, src):
    """All USGS readings (5-15 min) of one site and parameter (00060 flow cfs, 00065 gage height ft)."""
    url = src["usgs"]["url"]
    params = {"monitoring_location_id": f"USGS-{site}", "parameter_code": parameter,
              "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}",
              "limit": 10000, "skipGeometry": "true", "properties": "time,value", "f": "json"}
    # Optional free API key (higher request limit). Kept outside the code, in an environment variable.
    key = os.environ.get("USGS_API_KEY")
    headers = {"X-Api-Key": key} if key else None
    rows = []
    while url:
        js = _get(url, params, headers=headers).json()
        rows += [(f["properties"]["time"], f["properties"]["value"]) for f in js.get("features", [])]
        url = next((l["href"] for l in js.get("links", []) if l.get("rel") == "next"), None)
        params = None
    if not rows:
        return pd.Series(dtype=float)
    d = pd.DataFrame(rows, columns=["time", "value"])
    s = pd.to_numeric(d.set_index(pd.to_datetime(d.time, utc=True, format="ISO8601"))["value"], errors="coerce")
    return s[~s.index.duplicated()].sort_index()


def usgs_hourly(site, parameter, hours, src):
    """Hourly value = the reading nearest each hour, if within 15 min. Also returns the last reading time."""
    s = usgs_readings(site, parameter, hours[0] - pd.Timedelta("1h"), hours[-1] + pd.Timedelta("1h"), src)
    tol = pd.Timedelta(minutes=src["usgs"]["hour_tolerance_min"])
    hourly = s.reindex(hours, method="nearest", tolerance=tol) if len(s) else pd.Series(np.nan, index=hours)
    return hourly, (s.index.max() if len(s) else None)


# ---------------------------------------------------------------- MRMS

class MrmsBasinMeans:
    """Basin means of MRMS hourly rain on the NWM 1-km masks (same weights as Cell 47)."""

    def __init__(self, masks, src):
        self.masks, self.src = masks, src
        nwm = src["nwm"]
        self.to_lcc = Transformer.from_crs(4326, nwm["grid_proj"], always_xy=True)
        to_ll = Transformer.from_crs(nwm["grid_proj"], 4326, always_xy=True)
        xs = nwm["grid_x0"] + nwm["grid_step_m"] * np.arange(nwm["grid_nx"])
        ys = nwm["grid_y0"] + nwm["grid_step_m"] * np.arange(nwm["grid_ny"])
        yi, xj = np.where(np.any(np.stack(list(masks.values())), axis=0))
        lon, lat = to_ll.transform(xs[xj], ys[yi])
        self.box = (lon.min() - 0.03, lon.max() + 0.03, lat.min() - 0.03, lat.max() + 0.03)  # area to read, with a margin
        self.xs, self.ys, self.cache = xs, ys, {}

    def _weights(self, la1, lo1, dd):
        """Share of each MRMS cell that falls inside each basin (5 x 5 points per cell)."""
        key = (la1, lo1, dd)
        if key in self.cache:
            return self.cache[key]
        b, n = self.box, self.src["mrms"]["subsamples"]
        i0, i1 = int((la1 - b[3]) / dd), int((la1 - b[2]) / dd) + 1
        j0, j1 = int((b[0] % 360 - lo1) / dd), int((b[1] % 360 - lo1) / dd) + 1
        sub = (np.arange(n) + 0.5) / n - 0.5
        I, J, a, c = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1), sub, sub, indexing="ij")
        X, Y = self.to_lcc.transform(((lo1 + (J + c) * dd) - 360).ravel(), (la1 - (I + a) * dd).ravel())
        step = self.src["nwm"]["grid_step_m"]
        jx, iy = np.rint((X - self.xs[0]) / step).astype(int), np.rint((Y - self.ys[0]) / step).astype(int)
        inside = (iy >= 0) & (iy < len(self.ys)) & (jx >= 0) & (jx < len(self.xs))
        W = {}
        for name, m in self.masks.items():
            v = np.zeros(len(jx))
            v[inside] = m[iy[inside], jx[inside]]
            W[name] = v.reshape(I.shape).mean(axis=(2, 3))
        self.cache[key] = (i0, i1, j0, j1, W)
        return self.cache[key]

    def hour(self, t):
        """Basin means (mm) and coverage for the hour ending at t. None if MRMS has no file yet."""
        base = self.src["mrms"]["url"]
        for prod in self.src["mrms"]["products"]:
            r = _get(f"{base}/{prod}/{t:%Y%m%d}/MRMS_{prod}_{t:%Y%m%d-%H%M%S}.grib2.gz")
            if r is not None:
                break
        else:
            return None
        g = eccodes.codes_new_from_message(gzip.decompress(r.content))
        ni, nj = eccodes.codes_get(g, "Ni"), eccodes.codes_get(g, "Nj")
        la1 = eccodes.codes_get(g, "latitudeOfFirstGridPointInDegrees")
        lo1 = eccodes.codes_get(g, "longitudeOfFirstGridPointInDegrees")
        dd = eccodes.codes_get(g, "iDirectionIncrementInDegrees")
        v = eccodes.codes_get_values(g).reshape(nj, ni)
        eccodes.codes_release(g)
        i0, i1, j0, j1, W = self._weights(la1, lo1, dd)
        win = v[i0:i1, j0:j1].astype(float)
        win[(win < 0) | (win >= 9999)] = np.nan  # missing values
        row = {"source": prod.split("_")[3]}
        for name, w in W.items():
            ok = np.isfinite(win) & (w > 0)
            p = w[ok].sum()
            row[name] = (w[ok] * win[ok]).sum() / p if p > 0 else np.nan
            row[f"{name} coverage"] = round(p / w.sum(), 3)
        return row

    def hours(self, hours):
        rows = {t: self.hour(t) for t in hours}
        return pd.DataFrame({t: r for t, r in rows.items() if r is not None}).T.reindex(hours)


# ---------------------------------------------------------------- NWM

def _nwm_url(src, kind, cycle, lead=None):
    nwm = src["nwm"]
    path = nwm[kind].format(H=f"{cycle:%H}", L=f"{lead:03d}" if lead is not None else "")
    return f"{nwm['url']}/nwm.{cycle:%Y%m%d}/{path}"


def _nwm_flow(content, reaches):
    """Flow (cfs) at the given NWM reaches, and the valid time of the file."""
    with h5py.File(io.BytesIO(content), "r") as h:
        fid = h["feature_id"][:]
        q = h["streamflow"]
        sf = float(q.attrs.get("scale_factor", [1.0])[0])
        fill = int(q.attrs.get("_FillValue", [-999900])[0])
        q = q[:]
        valid = EPOCH + pd.Timedelta(minutes=int(h["time"][0]))
    pos = {f: i for i, f in enumerate(fid)}
    out = {}
    for name, f in reaches.items():
        v = q[pos[f]] if f in pos else fill
        out[name] = np.nan if v == fill else v * sf * M3S_TO_CFS
    return valid, out


def nwm_open_loop(hours, reaches, src):
    """NWM Open Loop (analysis_assim_no_da, tm00) flow in cfs at each reach, per hour."""
    rows = {}
    for t in hours:
        r = _get(_nwm_url(src, "open_loop", t))
        if r is not None:
            rows[t] = _nwm_flow(r.content, reaches)[1]
    return pd.DataFrame(rows).T.reindex(hours)


def latest_short_range_cycle(now, src, look_back_h=12):
    """Most recent short-range cycle whose last file (f048) is already posted."""
    t = now.floor("h")
    for k in range(look_back_h + 1):
        c = t - pd.Timedelta(hours=k)
        if session.head(_nwm_url(src, "short_range_flow", c, src["nwm"]["max_lead_h"]), timeout=30).status_code == 200:
            return c
    return None


def nwm_short_range(cycle, reaches, masks, src):
    """Short-range forecast of one cycle: flow (cfs) at each reach and rain (mm/h) on each basin mask, f001-f048."""
    flow, rain = {}, {}
    for L in range(1, src["nwm"]["max_lead_h"] + 1):
        r = _get(_nwm_url(src, "short_range_flow", cycle, L))
        if r is not None:
            valid, q = _nwm_flow(r.content, reaches)
            flow[valid] = q
        r = _get(_nwm_url(src, "short_range_rain", cycle, L))
        if r is not None:
            with h5py.File(io.BytesIO(r.content), "r") as h:
                d = h["RAINRATE"]
                rr = d[0].astype(float)
                rr[rr == float(d.attrs.get("_FillValue", [-999999.0])[0])] = np.nan  # missing cells
                rr *= 3600  # mm/s -> mm in the hour
                valid = EPOCH + pd.Timedelta(minutes=int(h["time"][0]))
                version = h.attrs.get("NWM_version_number", b"?")
            rain[valid] = {name: float(np.nanmean(rr[m])) for name, m in masks.items()}
    flow, rain = pd.DataFrame(flow).T.sort_index(), pd.DataFrame(rain).T.sort_index()
    # NWM version: since v3.1 (2026-08-18) the forecast rain is NBM, not WRF-ARW (the file does not name it)
    return flow, rain, (version.decode() if isinstance(version, bytes) else str(version))
