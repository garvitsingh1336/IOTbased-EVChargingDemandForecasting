"""Refresh dataset-dependent documentation after the verified Boulder migration."""
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

def main():
    q=json.loads((ROOT/"reports/data_quality.json").read_text())
    e=json.loads((ROOT/"reports/evaluation.json").read_text())
    c=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
    metrics=pd.read_csv(ROOT/"reports/test_metrics.csv")
    table="| Model | MAE | RMSE |\n|---|---:|---:|\n"+"\n".join(f"| {r.model} | {r.MAE:.4f} | {r.RMSE:.4f} |" for r in metrics.itertuples())
    facts=(f"The official snapshot contains {q['source_records']:,} records dated {q['source_first_connection_local']} to {q['source_last_connection_local']}. "
        f"The configured location is Scott Carpenter Park, {q['selected_address']}, Boulder, Colorado. "
        f"The selected December 2022–November 2023 window contains {q['input_records']:,} source rows. "
        f"After removing {q['duplicate_export_payloads']:,} exact export duplicates, {q['usable_arrivals']:,} sessions remain. "
        f"Excluding both boundary days leaves {q['included_arrivals']:,} arrivals across {q['hourly_rows']:,} hours and {q['local_days']} local days. "
        "The two station names are not a count of individual connectors.")
    source="https://open-data.bouldercolorado.gov/datasets/95992b3938be4622b07f0b05eba95d4c_0/explore"
    commands=r'''```powershell
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
```'''
    replay=r'''.\.venv\Scripts\python.exe -m evforecast simulate --api-url http://127.0.0.1:8000 --run-id demo --speed 3600 --reset'''
    readme=f'''# IoT-Based EV Charging Demand Forecasting

**Python + FastAPI REST API + XGBoost + Grafana**, with PostgreSQL for local storage.
Forecast the number of sessions starting at one site in each of the next 24 elapsed hours: **sessions/hour**.
Grafana is the primary frontend. Streamlit is retained as an optional legacy interface.

## Current dataset

{facts}

Source: [City of Boulder Open Data]({source}), CC0 per its official metadata. The actual latest observation is **30 November 2023**, not 2026. This is a historical demonstration, not today's operational forecast.
The download checks all advertised IDs and a stable source edit version; completeness of the exported table does not prove continuous station reporting.

## Windows setup and startup

Python 3.11–3.13 and Docker Desktop with WSL 2 / Linux containers are required. Docker runs PostgreSQL and Grafana; Python runs locally. No paid service or sensors are required.
The existing dataset and environment are already prepared; for a normal restart use only the final three startup commands below.

{commands}

Open [Grafana](http://localhost:3000/d/evforecast-demand) and [API docs](http://127.0.0.1:8000/docs).
Login: `admin`, using `GRAFANA_ADMIN_PASSWORD` in the ignored `.env` file. Do not publish that file.
If `docker` is not recognized after installation, reopen PowerShell. This computer also has the executable at `C:\\Users\\seema\\AppData\\Local\\Programs\\DockerDesktop\\resources\\bin\\docker.exe`.
The dashboard uses America/Denver and opens on the historical test period. Its top cards and saved forecast panels use their stated dataset/run scope; only the historical time-series panel follows the time picker.

In another PowerShell terminal in this folder:

```powershell
{replay}
```

**Historical data replay — simulated IoT feed.** Ctrl+C pauses; rerun without `--reset` to resume. Reset affects only the selected run. Events contain only event ID, historical timestamp, site ID and source station ID, plus reset generation. They never increase training counts. Grafana displays events; it does not control replay.

## Results and checks

{table}

Errors are sessions/hour, using unrounded nonnegative predictions. XGBoost won validation. Test: {e['test_origins']} origins / {e['unique_test_hours']} hours on identical timestamps for every method. These scores cannot be compared directly with old ACN scores because the population changed.

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
- Training cutoff is {e['test_start']} (exclusive). Requests earlier than that are rejected. Training is an offline command, never part of a prediction request.
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

[Boulder dataset]({source}) · [ACN original source](https://ev.caltech.edu/dataset.html) · [XGBoost](https://xgboost.readthedocs.io/en/stable/python/python_api.html) · [FastAPI](https://fastapi.tiangolo.com/) · [Grafana PostgreSQL](https://grafana.com/docs/grafana/latest/datasources/postgres/) · [Docker Windows setup](https://docs.docker.com/desktop/setup/install/windows-install/).
'''
    (ROOT/"README.md").write_text(readme,encoding="utf-8")
    docs={
    "project_report.md":f'''# Project report: IoT-Based EV Charging Demand Forecasting

## Problem
Estimate next-day hourly session arrivals at one site to help operators identify periods needing further capacity study. Arrival counts alone cannot determine power demand or queues.

## Dataset
{facts}
Downloaded from [the official City of Boulder source]({source}); source bytes and ID completeness are recorded in data/raw/boulder_download.json. The 2018 ACN dataset is preserved as an archive and does not train the current model.

## Methodology
The site was selected by pre-validation activity. Normalize source fields, remove ID/exact-payload duplicates, convert local timestamps to UTC, exclude boundary days and aggregate arrivals hourly. Missing-feed coverage is not known; zeros are assumptions. Optional completion/energy anomalies do not invalidate arrival times. No identities or final-session attributes enter the model.

Chronological training begins {e['training_start']}; validation begins {e['validation_start']}; test begins {e['test_start']} and ends {e['test_end_exclusive']} exclusive. Three modest XGBoost settings were compared on validation only. Refit on training+validation, then freeze. Each of {e['test_origins']} test origins predicts a complete next 24 hours recursively; later lag updates use predictions. All methods share target timestamps.

## Results
{table}

XGBoost won validation and had the lowest measured test MAE. Fractional outputs are expected counts. No accuracy percentage or calibrated prediction interval is claimed. The test contains {e['unique_test_hours']} hours; DST leaves the final available hour outside the last full 24-hour forecast rather than inventing an extra partial forecast.

## Implemented system
Historical preprocessing/training → saved XGBoost. Replay → FastAPI → PostgreSQL. Forecast service → immutable saved runs → Grafana. The dashboard has summary cards, forecast comparison, hourly history, weekday/hour patterns, baseline metrics, provenance and replay events. Grafana reads through a restricted database account.

## Limitations and future scope
The latest raw date is November 2023. Export duplicates, assumed feed availability, ambiguous source identifiers and local-time assumptions limit confidence. A municipal US site differs from an Indian college. Deployment requires new local data, availability monitoring, ingestion watermarks, security and independent evaluation. Weather is a possible extension only when its values are available at prediction time. No hardware or live sensing is claimed.
''',
    "architecture.md":'''# Architecture

```mermaid
flowchart LR
  B[Official Boulder snapshot] --> P[Validate / deduplicate / UTC hourly arrivals]
  P --> T[Chronological XGBoost and baseline evaluation]
  T --> M[Versioned model and reports]
  P --> H[(PostgreSQL historical observations)]
  B --> R[Historical arrival replay]
  R --> A[FastAPI REST ingestion]
  A --> E[(Separate replay events)]
  M --> F[24-hour forecast service]
  H --> F
  F --> S[(Immutable forecast runs)]
  H --> G[Grafana read-only dashboard]
  E --> G
  S --> G
```

Python runs on Windows; Docker hosts PostgreSQL and Grafana. Grafana is the primary frontend. Training stays offline. Replay never modifies historical aggregates. Timestamps are stored in UTC and displayed in America/Denver. Dataset hashes, model versions, training cutoffs and separate forecast IDs preserve provenance.
''',
    "demo_guide.md":f'''# Five-minute demonstration

Before presenting, start Docker Desktop, run `docker compose up -d --wait`, `python -m evforecast bootstrap-db`, and `python -m uvicorn evforecast.api:app --host 127.0.0.1 --port 8000` using the project virtual environment.

1. **0:00–0:45:** Open http://localhost:3000/d/evforecast-demand. Explain sessions/hour, historical Boulder dates, and the two source station names.
2. **0:45–1:30:** Show dataset coverage, timestamp checks and removal of {q['duplicate_export_payloads']:,} repeated export rows. Explain that zeros assume reporting coverage.
3. **1:30–2:30:** Show the forecast origin, training cutoff, expected total, peak hour and blue actual/orange forecast comparison. All predictions are historical.
4. **2:30–3:30:** Compare the model table: XGBoost MAE {metrics.loc[metrics.model.eq('xgboost'),'MAE'].iloc[0]:.3f}, over 30 full forecast origins. Explain chronological validation and recursive lags.
5. **3:30–4:30:** In a second terminal run `{replay}`. Scroll to **Historical data replay — simulated IoT feed** and refresh. Ctrl+C pauses; rerun without reset to resume without duplicate counts.
6. **4:30–5:00:** Explain REST ingestion, PostgreSQL storage and Grafana's read-only role. State the Indian-campus generalization and missing-coverage limitations.

Use the existing `.env` admin credentials. For a quicker replay use `--speed 100000000 --limit 10`. Do not call 2023 observations live data.
''',
    "viva.md":'''# Viva questions and answers

**What makes this IoT-related?** Software replays timestamped charging arrivals through a REST ingestion endpoint with validation, retries and duplicate suppression, representing the data path of connected chargers. There are no physical sensors; it is historical replay.

**Why public data?** It provides real observed charging behaviour without hardware or commercial access. The source, license, download checks and quality limitations are documented.

**Why Boulder?** Its official public records extend to November 2023 and support a full year at one location, instead of the earlier short ACN sample. It is not current/live data.

**Why session arrivals?** Start timestamps directly establish counts per hour. Total energy per session cannot reveal hourly power or energy distribution.

**Why XGBoost?** It is the required ML method, handles nonlinear relationships in calendar/lag features and runs on a local CPU. Modest validation-only tuning and seasonal baselines test whether it adds value.

**How was leakage prevented?** Chronological splits, no future session details, shifted rolling inputs, and a forecast-origin cutoff. Recursive forecasts substitute predictions for unavailable future arrivals. Test observations do not tune models.

**How does it compare?** XGBoost won validation. Test MAE/RMSE were 0.5097/0.8764 sessions/hour; same-hour-last-week was 0.5832/1.2360, on 30 origins and 720 matching hours. These are measured results for the selected site, not universal accuracy.

**Why not MAPE?** Many hourly counts are zero, making percentage errors undefined or unstable. MAE and RMSE retain sessions/hour units.

**Why fractional counts?** They are expected counts. Evaluation uses unrounded values; formatting does not change scores.

**How are duplicate records handled?** First deduplicate export IDs, then exact payload repeats across all charging fields. Keep the first and audit removed IDs. Records differing in other fields remain, with review flags.

**How does DST work?** Store UTC instants and use America/Denver for calendar features/display. Repeated hours have distinct UTC instants. Use timezone labels to resolve folds; mask unresolvable days. Forecasts always span 24 elapsed hours.

**Are the two station names two charging ports?** Not necessarily. The dataset lacks individual connector IDs; no physical capacity claim is made.

**Can forecasts establish waiting time?** No. Queues also need service durations, physical port counts, availability and queueing assumptions.

**Why PostgreSQL and Grafana?** PostgreSQL stores immutable history and separate forecast/replay records. Grafana queries it with read-only permissions and provides the primary dashboard. FastAPI handles ingestion and predictions; the CLI controls replay.

**What is needed at an Indian college?** Anonymized local arrivals covering seasonal/academic patterns, charger/site identifiers, consent/access permission, feed uptime and latency monitoring, operational security, and fresh chronological evaluation. US results do not automatically transfer.
''',
    "api.md":f'''# REST API

Start: `.\\.venv\\Scripts\\python.exe -m uvicorn evforecast.api:app --host 127.0.0.1 --port 8000`.
Interactive schemas and responses: http://127.0.0.1:8000/docs. The model loads once per process; restart after retraining.

| Endpoint | Purpose |
|---|---|
| GET /health | Database, history and model readiness; 503 when unavailable |
| GET /history | Hourly history, units, timezone; optional aware start/end and limit |
| POST /replay-runs/demo | Create/get replay run and current generation |
| POST /replay-runs/demo/events | Validate and ingest arrival, idempotent by run/event ID |
| GET /replay-runs/demo/events | Received arrivals and count |
| POST /replay-runs/demo/reset | Reset only this run and increment generation |
| POST /forecasts | Create a separate immutable 24-hour forecast |
| GET /forecasts | List current dataset's runs |
| GET /forecasts/{{id}} | Stored predictions, metadata and matching historical actuals |
| GET /evaluation | Model/baseline MAE and RMSE |
| GET /data-quality | Dataset coverage, quality and warnings |

Arrival example (use the generation returned for the run):
```json
{{"event_id":"example-arrival-1","timestamp":"2023-10-31T10:00:00-06:00","site_id":"boulder-carpenter-park","charger_id":"BOULDER / CARPENTER PARK1","generation":1}}
```
First arrival returns `accepted: true, duplicate: false`; repeating it returns `accepted: false, duplicate: true`. Altering its fields or using a stale generation returns 409. Missing timezone/unknown extra fields return 422. No final energy/departure fields are accepted.

Forecast request:
```json
{{"origin":"{e['demo_origin']}"}}
```
Response (201) includes `forecast_id`, `origin`, `model_version`, `training_cutoff`, `site_timezone`, `units`, `last_observation`, `kind`, 24 `points`, matching `actuals`, `predicted_total_arrivals`, and `busiest_hour`. Historical actuals are queried separately after prediction. A request before the training cutoff or without 168 prior usable hours returns 422. Missing model/database returns 503. Training is never triggered by inference.

Local-only prototype: no production authentication. Database operations use bound parameters. Grafana uses a separate read-only role; replay rows never contribute to training aggregates.
''',
    "migration-notes.md":f'''# Boulder migration and dashboard redesign

## Retained
Existing Python modules, XGBoost inference, recursive forecast-origin safeguards, chronological validation/test logic, baselines, REST API, idempotent storage, replay simulator, tests and optional Streamlit interface. The original ACN file, old native artifacts and pre-migration project copy remain preserved.

## Changed
Added an official Boulder downloader with stable edit-version, advertised-ID and SHA-256 checks. Added a source adapter for mixed timestamps, local timezone/DST handling, export duplicate removal, location selection and coverage reporting. The active dataset is Scott Carpenter Park, December 2022–November 2023. {facts}

Removed the former project-number branding from active code/configuration, documentation, API title, Grafana titles/UIDs, filenames and Compose project name. Immutable archived artifacts and backups retain historical provenance. Renamed smoke script to scripts/smoke_evforecast.py. Existing old Docker volumes were preserved; the new evforecast stack uses its own volumes.

Grafana now has a dark default theme, branded introduction, four summary cards, numbered sections, consistent blue actual/orange forecast colours, paired forecast comparisons, a weekday/hour colour matrix, performance panels, quality notes and separate replay activity. Its default range is historical and site timezone is America/Denver. Version-controlled generation is scripts/build_dashboard.py.

## Results
{table}

XGBoost won validation. Both validation and test use 30 origins of 24 elapsed hours each. Results are not directly comparable with earlier ACN scores. No current-day or Indian-campus accuracy is claimed.

## Verification and remaining limitations
50 tests passed with one non-failing pytest cache-permission warning. The full Boulder pipeline completed. Live PostgreSQL/REST smoke and 18 Grafana data-panel queries passed; Grafana reader write access was rejected. Browser automation had no available browser, so rendered visual inspection could not be completed. Concurrent-ingestion stress tests and a fresh dependency installation were not performed. Full logs and machine-readable results are in reports/ and runtime/.
''',
    "reports/verification.md":'''# Executed verification — Boulder migration

- Official source: 148,136 advertised record IDs retrieved; source edit version stable throughout download; raw SHA-256 stored in data/raw/boulder_download.json.
- Original ACN preserved; previous project outputs archived in runtime/before-boulder/.
- Full preprocessing, XGBoost tuning/training and chronological evaluation completed on real Boulder sessions.
- 50 pytest tests passed; one non-failing pytest cache-permission warning. Tests cover JSON recovery, source adapters, duplicates, DST, aggregation, forecast leakage, API validation, storage and legacy dashboard controls.
- Live PostgreSQL + Uvicorn smoke passed: readiness, repeat bootstrap, 3 arrival events, repeated event suppression, resume deduplication, 24-hour forecast storage/retrieval, metadata and raw-source hash.
- Live Grafana datasource health OK; all 18 data-panel queries returned successfully; read-only account rejected writes.
- Browser rendering unverified: the browser automation inventory contained no available browser. Do not interpret successful SQL queries as visual QA.
- Concurrent ingestion stress testing and a new clean dependency environment were not exercised.

Evidence: reports/evforecast-smoke.json, reports/grafana-verification.json, reports/test_metrics.csv, reports/training.json, reports/data_quality.json.
'''}
    for name,text in docs.items():
        (ROOT/"docs"/name).write_text(text,encoding="utf-8")
    print("Updated README and project, architecture, demo, viva, API, migration and verification documents.")

if __name__ == "__main__":
    main()
