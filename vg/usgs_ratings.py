"""Download the current USGS ratings (exsa) and save them as one table: site, stage_ft, q_cfs.

Run:  python -m vg.usgs_ratings
Same source and reading rule as Cell 124 (column 1 = stage, column 3 = flow).
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from vg import settings

URL = "https://waterdata.usgs.gov/nwisweb/get_ratings"


def parse_exsa(text, site):
    rows = []
    for line in text.splitlines():
        parts = line.split("\t")
        try:
            rows.append((site, float(parts[0]), float(parts[2])))
        except (ValueError, IndexError):
            pass  # header and comment lines
    return pd.DataFrame(rows, columns=["site", "stage_ft", "q_cfs"])


def main():
    cfg = settings.load()
    raw_dir = cfg["paths"]["inputs_dir"] / "ratings" / "ratings_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    tables = []
    for name, pt in cfg["test_points"].items():
        site = pt["gage_point"]["site"]
        text = requests.get(URL, params={"site_no": site, "file_type": "exsa"}, timeout=60).text
        (raw_dir / f"{site}.exsa.rdb").write_text(text)  # keep the original file too
        if f'RATING ID="{pt["usgs_rating_id"]}"' not in text:
            sys.exit(f"{name}: USGS rating is no longer {pt['usgs_rating_id']}. Check before using it.")
        tables.append(parse_exsa(text, site))
    out = cfg["paths"]["inputs_dir"] / "ratings" / f"usgs_ratings_exsa_4gages_{date.today():%Y-%m-%d}.csv"
    pd.concat(tables).to_csv(out, index=False)
    print("Saved", out)


if __name__ == "__main__":
    main()
