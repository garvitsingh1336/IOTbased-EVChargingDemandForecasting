# IoT-Based EV Charging Demand Forecasting

**Python + FastAPI REST API + XGBoost + Grafana**, with PostgreSQL for local storage.
Forecast the number of sessions starting at one site in each of the next 24 elapsed hours: **sessions/hour**.
Grafana is the primary frontend. Streamlit is retained as an optional legacy interface.

## Current dataset

The official snapshot contains 148,136 records dated 2018-01-01 17:49:00 to 2023-11-30 23:27:00. The configured location is Scott Carpenter Park, 1505 30th St, Boulder, Colorado. The selected December 2022–November 2023 window contains 7,787 source rows. After removing 1,163 exact export duplicates, 6,624 sessions remain. Excluding both boundary days leaves 6,604 arrivals across 8,712 hours and 363 local days. The two station names are not a count of individual connectors.

Source: [City of Boulder Open Data](https://open-data.bouldercolorado.gov/datasets/95992b3938be4622b07f0b05eba95d4c_0/explore), CC0 per its official metadata. The actual latest observation is **30 November 2023**, not 2026. This is a historical demonstration, not today's operational forecast.
The download checks all advertised IDs and a stable source edit version; completeness of the exported table does not prove continuous station reporting.

## Windows setup and startup

Python 3.11–3.13 and Docker Desktop with WSL 2 / Linux containers are required. Docker runs PostgreSQL and Grafana; Python runs locally. No paid service or sensors are required.
The existing dataset and environment are already prepared; for a normal restart use only the final three startup commands below.

```powershell
cd "C:\Users\seema\OneDrive\Desktop\EVChargingForecasting"
# First setup only (skip if the existing environment works):
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/setup_env.py

# First download only: refuses to overwrite the preserved raw snapshot.
.\.venv\Scripts\python.exe scripts/download_boulder.py

# Rebuild data, tune, evaluate, and generate the dashboard:
.\.venv\Scripts\python.exe -m evforecast all
.\.venv\Scripts\python.exe scripts/build_dashboard.py

# Start Docker Desktop with Linux containers before this command:
docker compose up -d --wait
.\.venv\Scripts\python.exe -m evforecast bootstrap-db
.\.venv\Scripts\python.exe -m uvicorn evforecast.api:app --host 127.0.0.1 --port 8000
```

Open [Grafana](http://localhost:3000/d/evforecast-demand) and [API docs](http://127.0.0.1:8000/docs).
Login: `admin`, using `GRAFANA_ADMIN_PASSWORD` in the ignored `.env` file. Do not publish that file.
If `docker` is not recognized after installation, reopen PowerShell. This computer also has the executable at `C:\Users\seema\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe`.
The dashboard uses America/Denver and opens on the historical test period. Its top cards and saved forecast panels use their stated dataset/run scope; only the historical time-series panel follows the time picker.

In another PowerShell terminal in this folder:

```powershell
.\.venv\Scripts\python.exe -m evforecast simulate --api-url http://127.0.0.1:8000 --run-id demo --speed 3600 --reset
```

**Historical data replay — simulated IoT feed.** Ctrl+C pauses; rerun without `--reset` to resume. Reset affects only the selected run. Events contain only event ID, historical timestamp, site ID and source station ID, plus reset generation. They never increase training counts. Grafana displays events; it does not control replay.

## Results and checks

| Model | MAE | RMSE |
|---|---:|---:|
| xgboost | 0.5097 | 0.8764 |
| random_forest | 0.5112 | 0.8836 |
| same_hour_last_week | 0.5832 | 1.2360 |
| hour_of_week_average | 0.6874 | 0.9953 |

Errors are sessions/hour, using unrounded nonnegative predictions. XGBoost won validation. Test: 30 origins / 720 hours on identical timestamps for every method. These scores cannot be compared directly with old ACN scores because the population changed.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/smoke_evforecast.py
.\.venv\Scripts\python.exe scripts/verify_grafana.py
```

50 tests passed, with a non-failing pytest cache-permission warning. PostgreSQL/REST smoke checks passed for readiness, repeat bootstrap, arrival ingestion, duplicate retries, replay resume, and stored 24-hour forecasts. All 18 Grafana data-panel queries passed and its reader account rejected writes. Browser visual inspection was unavailable in this session.
Machine-readable evidence: `reports/evforecast-smoke.json`, `reports/grafana-verification.json`. Python dependencies are pinned; a fresh isolated dependency installation was not retested.

## Method and limitations

- Recursive XGBoost uses local calendar features, lags 1/24/168 and shifted rolling statistics. Unavailable future lags use predictions, never held-out observations.
- Site selection used activity before October 2023 only. Chronological validation and test each span 30 local calendar days; forecasts start 24 elapsed hours apart. DST may shift the local forecast clock; targets always contain exactly 24 elapsed hours.
- Training cutoff is 2023-10-31T06:00:00+00:00 (exclusive). Requests earlier than that are rejected. Training is an offline command, never part of a prediction request.
- Parse both official date formats. Interpret local clocks in America/Denver; report conflicting timezone labels, use valid labels for fall-back folds, and mask local days with unresolvable DST times. No selected arrival had a timezone conflict.
- Keep first source ObjectId2, then remove exact duplicate charging payloads (all fields except export IDs). Less exact matches remain flagged. Source IDs are export-row identifiers, not guaranteed physical session identifiers.
- Zero hours are assumed, not proven. Mask seven-day silent runs as unknown coverage. No such run was detected at the chosen site.
- Session energy and duration are descriptive only. Counts cannot establish hourly kWh, queues, waiting times, occupancy or charger shortages.
- US municipal behaviour does not establish performance at an Indian college. Real deployment needs local validation, feed-uptime monitoring, ingestion delays, authentication and operational security.

## Structure and preservation

`evforecast/`: adapters, features, training, REST, storage and replay. `scripts/`: download, dashboard generation and checks. `infra/`: Grafana provisioning and PostgreSQL read-only role. `docs/`: report, demo, viva, architecture and API guide.
Raw Boulder records: `data/raw/`; cleaned sessions/hourly series: `data/`; metrics and quality: `reports/`; versioned native XGBoost: `artifacts/models/`.
Original ACN download is unchanged. The previous implementation/data/reports are archived in `runtime/before-boulder/`; old model versions remain immutable. Earlier stopped Docker containers and volumes were preserved. The active Compose project is now `evforecast` with separate volumes.

Stop the foreground API with Ctrl+C, then `docker compose stop`. Restarting preserves database data. Never use volume deletion as a replay reset.

## References

[Boulder dataset](https://open-data.bouldercolorado.gov/datasets/95992b3938be4622b07f0b05eba95d4c_0/explore) · [ACN original source](https://ev.caltech.edu/dataset.html) · [XGBoost](https://xgboost.readthedocs.io/en/stable/python/python_api.html) · [FastAPI](https://fastapi.tiangolo.com/) · [Grafana PostgreSQL](https://grafana.com/docs/grafana/latest/datasources/postgres/) · [Docker Windows setup](https://docs.docker.com/desktop/setup/install/windows-install/).
