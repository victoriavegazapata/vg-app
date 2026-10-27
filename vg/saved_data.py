"""Read the saved project data (USGS hourly flow, MRMS basin means) used by the checks."""
import numpy as np
import pandas as pd


def _utc(df):
    df.index = pd.to_datetime(df.index, utc=True)
    return df[~df.index.duplicated()].sort_index()


def read_mrms(path, min_coverage):
    """MRMS basin means (mm); a value is kept only when its coverage ≥ min_coverage."""
    m = _utc(pd.read_csv(path, index_col=0))
    cols = [c for c in m.columns if not c.endswith("coverage") and c != "source"]
    return pd.DataFrame({c: m[c].where(m[f"{c} coverage"] >= min_coverage) for c in cols})


def mask_areas(path):
    """Number of NWM 1-km cells in each basin mask (= area in km²)."""
    m = np.load(path)
    return {k.replace("_", " "): int(m[k].sum()) for k in m.files}


def test_point_data(cfg, hours):
    """Hourly flow Q and rain P for the 4 test points, the same files as Cells 121 and 124."""
    d, cov = cfg["paths"]["data_dir"], cfg["rain"]["min_coverage"]
    P = pd.concat([read_mrms(d / "mrms_6basins_hourly_2020_2023.csv", cov),
                   read_mrms(d / "mrms_6basins_hourly_2025_2026.csv", cov)])
    P = P[~P.index.duplicated()].join(read_mrms(d / "mrms_loiza_hourly_2020_2026.csv", cov), how="outer").reindex(hours)
    Q6 = pd.concat([_utc(pd.read_csv(d / "usgs_flow_6stations_2008_2023.csv", index_col=0)),
                    _utc(pd.read_csv(d / "usgs_flow_6stations_2025_2026.csv", index_col=0))])
    Q = Q6[~Q6.index.duplicated()].join(_utc(pd.read_csv(d / "usgs_flow_loiza_5stations_2020_2026.csv", index_col=0)),
                                        how="outer").reindex(hours)
    return Q, P


NO_GAGE_FILES = {"Arecibo junction": ("usgs_flow_arecibo_2stations_2020_2026.csv", "mrms_arecibo_hourly_2020_2026.csv"),
                 "Río Nigua confluence": ("usgs_flow_nigua_2stations_2020_2026.csv", "mrms_nigua_hourly_2020_2026.csv")}


def no_gage_data(cfg, point, hours):
    """Hourly flow and rain for a point without a gage (Cell 125 files)."""
    d = cfg["paths"]["data_dir"]
    fq, fp = NO_GAGE_FILES[point]
    Q = _utc(pd.read_csv(d / fq, index_col=0)).reindex(hours)
    P = read_mrms(d / fp, cfg["rain"]["min_coverage"]).reindex(hours)
    return Q, P
