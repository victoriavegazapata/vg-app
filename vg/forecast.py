"""Experimental forecast (kept apart from the nowcast). NOT tested.

Same math as the nowcast (vg/nowcast.py), run on inputs extended into the future:
- each upstream gage keeps its last measured value (config: forecast.upstream_after_last_reading);
- rain after the last MRMS hour = NWM short-range forecast rain on the same masks.
Each forecast hour gets a label:
- "upstream measured": hours 1 to lag after the last upstream reading; the flow arriving is already measured upstream.
- "held flow + forecast rain": later hours.
Each hour also says whether R came from rain or from the dry-day rule (R = 1); a peak at a
dry-day hour is flagged on the page (config: forecast.dry_day_peak_note).
"""
import pandas as pd

from vg import nowcast

KNOWN, GUESS = "upstream measured", "held flow + forecast rain"


def extend_inputs(data, sr_rain, end):
    """Hourly inputs from the start of the live window to the forecast end.

    data    = live.inputs(...) result (measured)
    sr_rain = NWM short-range forecast rain, mm per hour by mask name
    """
    hours = pd.date_range(data["hours"][0], end, freq="h")
    P = data["P"].reindex(hours)
    last_mrms = data["P"].dropna(how="all").index.max()
    future = hours > last_mrms
    P.loc[future] = sr_rain.reindex(hours[future])[P.columns].values
    return hours, P, last_mrms


def _mark_dry_day(out):
    """True where R was set to 1 by the dry-day rule (upstream 24-h rain < 2 mm, or missing), not computed from rain."""
    out["R is dry-day default"] = out.pop("rain ratio R (raw, blank = R set to 1)").isna()
    return out


def peak(out, flow_col):
    """Forecast peak: (time, flow, True if that hour's R is the dry-day default)."""
    t = out[flow_col].idxmax()
    return t, out.at[t, flow_col], bool(out.at[t, "R is dry-day default"])


def _hold(q, t_last, hours):
    """Keep a gage at its value at t_last for every later hour."""
    q = q.reindex(hours)
    q[q.index > t_last] = q.get(t_last)
    return q


def _last_both(Q, a, b):
    """Last hour when both upstream gages have a reading."""
    both = Q[a].notna() & Q[b].notna()
    return both[both].index.max()


def test_point(name, data, sr_rain, sr_flow, cfg, now):
    pt = cfg["test_points"][name]
    a, b = pt["gage_a"]["name"], pt["gage_b"]["name"]
    end = sr_flow.index.max()
    hours, P, last_mrms = extend_inputs(data, sr_rain, end)
    t_up = _last_both(data["Q"], a, b)
    Q = data["Q"].reindex(hours)
    Q[a], Q[b] = _hold(data["Q"][a], t_up, hours), _hold(data["Q"][b], t_up, hours)
    tab, info = nowcast.test_point(name, Q, P, data["H"].reindex(hours), cfg)
    keep = ["upstream sum cfs", "rain ratio R", "virtual gage flow cfs",
            "virtual gage stage ft (HAND rating)", "virtual gage stage ft (USGS rating)", "below HAND table",
            "rain ratio R (raw, blank = R set to 1)"]
    out = tab.loc[tab.index > now, keep].copy()
    out = _mark_dry_day(out)
    out["hour type"] = [KNOWN if t <= t_up + pd.Timedelta(hours=pt["lag_h"]) else GUESS for t in out.index]
    out["rain source"] = ["MRMS" if t <= last_mrms else "NWM forecast" for t in out.index]
    out["NWM short-range cfs"] = sr_flow[name].reindex(out.index)
    info.update({"last upstream reading hour": t_up, "last MRMS hour": last_mrms, "lag h": pt["lag_h"]})
    return out, info


def no_gage_point(name, data, sr_rain, sr_flow, cfg, now):
    pt, ng = cfg["no_gage_points"][name], cfg["no_gage_default"]
    a, b = pt["gage_a"]["name"], pt["gage_b"]["name"]
    end = sr_flow.index.max()
    hours, P, last_mrms = extend_inputs(data, sr_rain, end)
    t_up = _last_both(data["Q"], a, b)
    Q = data["Q"].reindex(hours)
    Q[a], Q[b] = _hold(data["Q"][a], t_up, hours), _hold(data["Q"][b], t_up, hours)
    tab, info = nowcast.no_gage_point(name, Q, P, cfg)
    out = _mark_dry_day(tab.loc[tab.index > now].copy())
    out["hour type"] = [KNOWN if t <= t_up + pd.Timedelta(hours=ng["lag_h"]) else GUESS for t in out.index]
    out["rain source"] = ["MRMS" if t <= last_mrms else "NWM forecast" for t in out.index]
    out["NWM short-range cfs"] = sr_flow[name].reindex(out.index)
    info.update({"last upstream reading hour": t_up, "last MRMS hour": last_mrms, "lag h": ng["lag_h"]})
    return out, info
