"""Hourly update: fetch data → nowcast + forecast → write site/data/latest.json for the page.

Run:  python run_update.py
If a data source fails, nothing is written, so the page keeps showing the last good update
(with its time, so readers can see it is old).
"""
import sys

import pandas as pd

from vg import settings, results, fetch

cfg = settings.load()
now = pd.Timestamp.now(tz="UTC").floor("h")
out = settings.APP_DIR / "site" / "data" / "latest.json"
try:
    result = results.build(cfg, now)
except fetch.RateLimited as e:
    sys.exit(f"Update skipped: {e}")
results.write(result, out)
print(f"Wrote {out} for {now:%Y-%m-%d %H}:00 UTC")
