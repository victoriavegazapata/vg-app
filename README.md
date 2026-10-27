# Puerto Rico Virtual Gages (research prototype)

Victoria Vega Zapata, NOAA NERTO / CESSRST-II.
**Research prototype, NOT validated, method pending review. Not an official NWS product.**

A web page where you search or click one of 6 points in Puerto Rico and see:
- the **nowcast** (tested on past floods): virtual-gage flow and water level for the last 48 h;
- an **experimental forecast** (not tested), in its own section.

## Where things are

| What | Where |
|---|---|
| All method settings (points, K, lag, c, p, Manning n, slopes, limits, notes) | `config.yaml` |
| Method code, in small steps | `vg/`: `fetch.py` → `flow.py` (M13 / M2) → `stage.py` (HAND) → `nowcast.py` → `forecast.py` → `results.py` |
| Hourly update | `run_update.py` (writes `site/data/latest.json`) |
| The page | `site/` (`index.html`, `app.js`, `style.css`) |
| Small project files the update needs | `inputs/` (basin masks, HAND geometry, USGS ratings, NWPS replies) |
| Checks against the thesis numbers | `checks/thesis_numbers.py` (needs the saved thesis data on Victoria's Mac) |

## Run it on your Mac

```bash
pip install -r requirements.txt
python run_update.py
python -m http.server 8765 --directory site
```
Then open http://localhost:8765.

## Checks (run after any change to config.yaml or vg/)

```bash
python checks/thesis_numbers.py
python checks/nws_stages_check.py
```

## Hosting

GitHub runs `.github/workflows/update.yml` every hour (25 min past the hour, UTC) and publishes `site/` with GitHub Pages.
Optional: a free USGS API key in the repository secret `USGS_API_KEY` raises the USGS request limit.
