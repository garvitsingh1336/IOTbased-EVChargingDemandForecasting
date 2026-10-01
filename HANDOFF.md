# Handoff: EV Charging Demand Forecasting

Project root: C:\Users\seema\OneDrive\Desktop\EVChargingForecasting
Handoff date: 2026-10-01

## 1. Purpose and current goal

This is a local college prototype titled "IoT-Based EV Charging Demand Forecasting".

Official specification:

- Technology: Embedded IOT
- Subdomain: Charging Infrastructure
- Required stack: REST API, Python, XGBoost, Grafana
- Objective: forecast EV charging demand

The active target is site-wide charging-session arrivals for each hour of the next 24 elapsed hours, measured in sessions/hour. This is session-arrival demand, not electrical load, hourly kWh, queue length, waiting time, charger occupancy, or capacity shortage.

The current goal is to maintain and polish the Boulder-based implementation, keep Grafana as the primary frontend, preserve the original ACN source and earlier implementation for provenance, and complete final environment/browser verification.

There is no Git repository at the project root. The change inventory below was inferred from the current tree, timestamps, migration notes, reports, and preserved pre-migration copies.

## 2. Work completed so far

### Dataset migration

The active training source was migrated from the earlier truncated Caltech ACN sample to an official City of Boulder Open Data ArcGIS snapshot.

Active raw source:

- data/raw/boulder_sessions.json
- URL: https://services.arcgis.com/ePKBjXrBZ2vEEgWd/arcgis/rest/services/Electric_Vehicle_Charging_Station_Data/FeatureServer/0
- 148,136 records
- SHA-256: 9e51a08da5d0cb9f59d66bcfd84574bac3b109ee7c0e8fe530b70ef305aa9e8f
- All advertised ObjectId2 values were retrieved.
- Source edit information was checked before and after download.
- The manifest records CC0 per official item metadata.
- A complete advertised table snapshot does not prove continuous station reporting.

Configured site:

- Boulder - Scott Carpenter Park
- Address: 1505 30th St
- Site ID: boulder-carpenter-park
- Timezone: America/Denver
- Period: 2022-12-01 through 2023-12-01 exclusive
- Latest source observation: 2023-11-30; this is not current-day data.

Selected-window results:

- Selected source rows: 7,787
- Duplicate ObjectId2 values: 0
- Exact export-payload duplicates removed: 1,163
- Usable arrivals after deduplication: 6,624
- Boundary-day arrivals excluded: 20
- Included arrivals: 6,604
- Hourly rows: 8,712
- Interior local days: 363
- Distinct station names: 2
- Missing doneChargingTime: 6,624; this optional field is not required for arrival forecasting.
- Invalid/negative energy: 0
- Invalid/missing disconnect: 0
- Negative duration: 0
- Known missing hours: 0
- Long silent runs marked unknown coverage: 0
- Zero-event hours are assumptions, not proof that the source feed was working.

The original ACN file remains preserved outside the project at C:\Users\seema\Downloads\acndata_sessions.json. The old implementation/data/reports are preserved under runtime/before-boulder/ and runtime/pre-p231-migration/. The old recovered ACN data remains in data/recovered_sessions.json.

### Forecasting

- XGBoost is the primary ML model.
- Random Forest is retained as an optional benchmark.
- Baselines: same hour last week and historical hour-of-week average.
- The 24-hour forecast is recursive.
- Features: local hour, weekday, weekend, sine/cosine hour encoding, lags 1/24/168, and shifted rolling mean/std over 24 and 168 hours.
- Future unavailable lag values use predictions, never future held-out actuals.
- Predictions are clipped at zero.
- Fractional outputs are expected counts; evaluation uses unrounded values.
- Local calendar features use America/Denver; database timestamps are UTC.
- Chronological rolling-origin evaluation uses complete 24-hour targets.

Split:

- Training starts: 2022-12-02T07:00:00+00:00
- Validation starts: 2023-10-01T06:00:00+00:00
- Test starts: 2023-10-31T06:00:00+00:00
- Test end exclusive: 2023-11-30T07:00:00+00:00
- Validation: 30 origins
- Test: 30 origins and 720 target hours

Held-out metrics:

| Method | MAE | RMSE |
|---|---:|---:|
| xgboost | 0.5097 | 0.8764 |
| random_forest | 0.5112 | 0.8836 |
| same_hour_last_week | 0.5832 | 1.2360 |
| hour_of_week_average | 0.6874 | 0.9953 |

XGBoost won validation and had the lowest measured test MAE for this selected site. No universal accuracy claim is made.

Active artifact:

- artifacts/current_model.json points to xgb-007fa5a4ccf4a14bec33
- Native model: artifacts/models/xgb-007fa5a4ccf4a14bec33/xgboost.ubj
- Metadata/checksum/feature schema are beside the model.
- artifacts/forecast_bundle.joblib is the trusted local bundle used by tests/bootstrap.

### REST API and database

FastAPI is implemented in evforecast/api.py. Endpoints:

- GET /health
- GET /history
- GET /data-quality
- GET /evaluation
- POST /replay-runs/{run_id}
- GET /replay-runs/{run_id}/events
- POST /replay-runs/{run_id}/events
- POST /replay-runs/{run_id}/reset
- POST /forecasts
- GET /forecasts
- GET /forecasts/{forecast_id}

The API validates timezone-aware timestamps, rejects unknown fields, requires hourly forecast origins, prevents duplicate event IDs from double counting, rejects stale replay generations, and never trains during an ordinary prediction request.

PostgreSQL is the normal backend. SQLite is used by isolated tests. The schema contains datasets, hourly_demand, replay_runs, arrival_events, forecast_runs, forecast_points, and evaluation_results.

Forecast runs are immutable and retain origin, model version, training cutoff, dataset ID, timezone, units, and actuals when available. Grafana uses a separate SELECT-only grafana_reader account with read-only transactions.

### Grafana and Streamlit

Grafana is the primary frontend:

http://localhost:3000/d/evforecast-demand

Active dashboard/provisioning files:

- infra/grafana/dashboards/evforecast.json
- infra/grafana/provisioning/dashboards/evforecast.yaml
- infra/grafana/provisioning/datasources/postgres.yaml
- scripts/build_dashboard.py

The dashboard has a branded header, Boulder scope/timezone, data-quality cards, historical arrivals, typical day/week charts, weekday/hour heatmap, next-24-hour forecast, predicted total, busiest hour, actual-vs-predicted comparison, validation/test metrics, warnings, and replay activity. It opens on the historical test period and uses America/Denver.

app.py retains Streamlit as an optional legacy interface. Grafana is the supported frontend.

### Simulated IoT feed

The simulator is historical replay, not live sensor data.

Primary command:

.\.venv\Scripts\python.exe -m evforecast simulate --api-url http://127.0.0.1:8000 --run-id demo --speed 3600 --reset

It:

- replays processed arrivals chronologically;
- sends event ID, timestamp, site ID, source station/charger ID, and generation;
- does not send energy, disconnect, departure, duration, or final-session fields;
- retries transient transport/server failures;
- uses API-side idempotency;
- supports reset scoped to one run;
- resumes without duplicating accepted events;
- stores replay events separately from training history.

A legacy file replay remains available through simulate-legacy and runtime/cli_arrivals.jsonl.

## 3. Files changed and current roles

### Root/configuration

- README.md: current Boulder setup, Grafana-first instructions, results, limitations, references.
- requirements.txt: pinned Python stack including NumPy, pandas, scikit-learn, XGBoost, FastAPI, Uvicorn, SQLAlchemy, psycopg, Streamlit, Plotly, joblib, pytest, and dotenv.
- config.json: Boulder source/site/timezone/period, evaluation windows, seed, XGBoost grid, and official-stack metadata.
- .env.example: non-secret credential/database template.
- .env: ignored local credentials; never publish or print.
- compose.yaml: evforecast Compose project with PostgreSQL 16, Grafana 12.2, local ports, persistent volumes, provisioning mounts, dark theme, and default dashboard.
- .gitignore: excludes venv/cache/data/artifacts/runtime/logs/.env.

### evforecast package

- config.py: root/config/output helpers.
- data.py: ACN recovery/cleaning path, timezone parsing, duplicates, hourly aggregation, and Boulder dispatch.
- boulder.py: Boulder validation, mixed timestamp parsing, local timezone/DST handling, site/period selection, exact export duplicate removal, quality/recovery reports, CSV outputs.
- models.py: leakage-safe features, XGBoost, RF, baselines, recursive forecasts.
- evaluate.py: chronological split, validation-only tuning, refit, rolling 24-hour evaluation, metrics, prediction CSVs, Plotly reports.
- artifacts.py: native XGBoost UBJ save/load, checksum and feature-schema validation, active model pointer.
- service.py: forecast service with training cutoff and 168-hour history checks.
- database.py: SQLAlchemy tables, PostgreSQL/SQLite storage, idempotent replay ingestion, history, evaluations, immutable forecasts.
- bootstrap.py: imports history/evaluations and creates one idempotent demo forecast.
- api.py: FastAPI readiness, validation, replay, history, evaluation, quality, and forecast routes.
- replay.py: arrival-only local file replay and duplicate-safe ReplayFeed.
- replay_http.py: REST replay with speed, reset, retry, and resume.
- __main__.py: CLI commands preprocess, train, evaluate, all, simulate, simulate-legacy, bootstrap-db.
- __init__.py: package marker.

### Scripts

- scripts/setup_env.py: creates random local .env once.
- scripts/download_boulder.py: auditable ArcGIS download; refuses to overwrite existing raw data.
- scripts/check_official_download.py: earlier ACN access check.
- scripts/build_dashboard.py: generated Grafana JSON.
- scripts/refresh_docs.py: documentation regeneration helper.
- scripts/smoke_evforecast.py: current Boulder/PostgreSQL/REST smoke.
- scripts/verify_grafana.py: Grafana datasource/read-only/query verification.
- scripts/verify_project.py: legacy Streamlit/file-replay verification.

### Tests

- tests/test_data.py: recovery, cleaning, aggregation, missing coverage, timezone.
- tests/test_boulder.py: Boulder adapter, mixed timestamps, duplicates, DST.
- tests/test_models.py: features, recursive forecast, nonnegative values, leakage.
- tests/test_api.py: validation, readiness, history, replay idempotency/reset, metadata, immutable runs, future isolation.
- tests/test_replay.py: arrival-only payload and restart deduplication.
- tests/test_artifacts.py: native artifact checksum/schema/pointer.
- tests/test_dashboard.py: legacy dashboard checks.
- tests/test_grafana_config.py: static Grafana/provisioning/storage checks.

### Data/artifacts/reports

- data/raw/boulder_sessions.json: official 76 MB snapshot.
- data/raw/boulder_download.json: download manifest/hash/count/edit metadata/license.
- data/sessions.csv: cleaned sessions.
- data/hourly.csv: UTC hourly arrivals and coverage status.
- data/recovered_sessions.json: prior ACN recovery output.
- reports/recovery.json: snapshot status/hash.
- reports/data_quality.json and docs/reports/data_quality.md: quality results.
- reports/training.json: training/tuning provenance.
- reports/evaluation.json and docs/reports/model_evaluation.md: current evaluation.
- reports/test_metrics.csv, test_predictions.csv, validation_metrics.csv, validation_predictions.csv, errors_by_hour.csv: evidence.
- reports/evforecast-smoke.json: current REST smoke.
- reports/grafana-verification.json: current Grafana query/read-only smoke.
- reports/model_comparison.html, actual_vs_predicted.html, errors_by_hour.html: Plotly outputs.
- reports/official_access.json: earlier ACN attempt; no token and truncated web JSON.
- artifacts/current_model.json and artifacts/models/: active/immutable native models.

### Documentation/preservation

- docs/api.md: routes/examples.
- docs/architecture.md: Mermaid architecture.
- docs/demo_guide.md: five-minute demo.
- docs/project_report.md: report.
- docs/viva.md: viva questions/answers.
- docs/migration-notes.md: migration/redesign/verification.
- docs/reports/verification.md: current verification.
- docs/legacy-reports/: older docs.
- runtime/before-boulder/: earlier implementation/data/report snapshot.
- runtime/pre-p231-migration/: pre-branding/migration copy.
- runtime/migrate_branding.py: branding migration helper.
- runtime/: logs, replay output, smoke SQLite files.

## 4. Current status

Working:

- Boulder raw snapshot and manifest are present and hash-checked.
- Preprocessing, training, evaluation, and dashboard generation completed.
- XGBoost is active; RF and seasonal baselines are evaluated.
- API currently responds on 127.0.0.1:8000.
- Latest health check returned ready=true, model_ready=true, database_ready=true, historical_data_ready=true, model_version=xgb-007fa5a4ccf4a14bec33.
- PostgreSQL/REST smoke passed.
- Grafana datasource and all 18 configured SQL panel queries passed.
- REST replay accepted events and deduplicated retries/resume.
- Streamlit was previously started successfully by the legacy verifier.

Not fully verified:

- No latest browser visual inspection of Grafana was possible because no browser was available to the automation tool.
- SQL query success does not prove rendered panel layout.
- A fresh clean virtual environment was not retested after migration.
- Concurrent ingestion stress testing was not performed.
- Docker CLI was not available on the current PowerShell PATH during inspection; previous session evidence says Compose/Grafana/PostgreSQL worked, but recheck in a fresh terminal.

## 5. Known bugs, stale artifacts, and limitations

1. reports/p231-smoke.json is stale and still contains P_231 plus old ACN dataset/model values. A repository search found this as the remaining active old-branding match. Do not confuse it with reports/evforecast-smoke.json. Decide whether to archive, rename, or regenerate it if old branding must disappear everywhere.

2. reports/simulator_smoke.txt contains old ACN 2018 events with site ID 0002. Current Boulder REST replay evidence is in reports/evforecast-smoke.json. Regenerate or clearly archive the old text report before final submission.

3. reports/verification.json is an older Streamlit/file-replay report with old test-hour values. Current primary verification is docs/reports/verification.md plus the REST/Grafana JSON reports.

4. Several strings appear as mojibake such as â€”, â†’, or garbled emoji in PowerShell output and possibly dashboard text. Verify actual file encoding and rendered UI before fixing. If confirmed, normalize source/docs/dashboard generation to UTF-8 and rerun checks.

5. In the current PowerShell, docker was not recognized. Reopen PowerShell after Docker Desktop startup/install and verify Linux containers, docker --version, and docker compose ps.

6. Boulder data ends in November 2023. Never present this as a validated forecast for today.

7. Complete advertised source IDs do not prove feed uptime. Zero-event hours are assumptions; populated hours can also undercount missing transactions.

8. Two station names are not guaranteed physical port count. Do not infer waiting times, queues, occupancy, shortages, or power from arrivals alone.

9. Boulder is a US municipal dataset and does not establish performance at an Indian college.

## 6. Important technical decisions

- Active stack follows the official requirement: FastAPI + Python + XGBoost + Grafana.
- Streamlit is optional legacy UI.
- PostgreSQL supports persistence/Grafana.
- No cloud, paid service, hardware, MQTT broker, or synthetic training data is required.
- Replay is explicitly historical simulated IoT feed.
- Arrival events contain only fields known at arrival.
- Replay data cannot inflate training aggregates.
- Training is offline.
- Forecast runs are immutable.
- Native XGBoost artifacts are checksum/schema validated.
- Storage timestamps are UTC; local calendar/display is America/Denver.
- Evaluation uses chronological complete 24-hour origins.
- MAE/RMSE are used instead of MAPE as the main metrics.
- Session energy/duration are descriptive only.
- Original ACN and old implementation remain preserved.
- Replay reset never deletes Docker volumes or training history.
- Grafana uses a read-only database account without plugins.

## 7. Commands already run and results

Run from C:\Users\seema\OneDrive\Desktop\EVChargingForecasting.

Setup/download:

- .\.venv\Scripts\python.exe scripts/setup_env.py
  Result: ignored local .env created or preserved.
- .\.venv\Scripts\python.exe scripts/download_boulder.py
  Result: 148,136 records, all advertised IDs, stable edit information, manifest/hash.
- .\.venv\Scripts\python.exe -m evforecast all
  Result: preprocessing, XGBoost tuning/training, chronological evaluation completed.
- .\.venv\Scripts\python.exe scripts/build_dashboard.py
  Result: generated current 25-panel dashboard.

Services:

- docker compose up -d --wait
- .\.venv\Scripts\python.exe -m evforecast bootstrap-db
- .\.venv\Scripts\python.exe -m uvicorn evforecast.api:app --host 127.0.0.1 --port 8000
  Previous migration session result: PostgreSQL/Grafana stack and API started. Current inspection confirmed API health is ready. Current shell did not recognize docker, so recheck.

Smoke:

- .\.venv\Scripts\python.exe scripts/smoke_evforecast.py
  Result in reports/evforecast-smoke.json: PostgreSQL backend, readiness, repeat bootstrap, 3 unique arrivals, duplicate rejection, replay resume deduplication, 24 stored forecast points, metadata/cutoff, OpenAPI 200, source unchanged.
- .\.venv\Scripts\python.exe scripts/verify_grafana.py
  Result in reports/grafana-verification.json: datasource OK, read-only role verified, 18 panel queries returned rows, visual_browser_check=false.
- .\.venv\Scripts\python.exe -m evforecast simulate --api-url http://127.0.0.1:8000 --run-id demo --speed 100000000 --limit 10
  Result: current REST replay accepted 10 Boulder arrival-only events.

Tests:

- .\.venv\Scripts\python.exe -m pytest -q
  Recorded result: 50 passed, one non-failing pytest cache-permission warning.
- Evidence: reports/pytest_output.txt, docs/reports/verification.md, reports/evforecast-smoke.json, reports/grafana-verification.json.

Do not claim clean-environment dependency installation or browser visual QA as completed.

## 8. Next steps in priority order

1. Recheck services in a fresh PowerShell:
   - Start Docker Desktop with Linux containers.
   - Confirm docker --version and docker compose ps.
   - Confirm PostgreSQL/Grafana health.
   - Confirm http://127.0.0.1:8000/health.
   - Open http://localhost:3000/d/evforecast-demand.

2. Perform visual Grafana QA:
   - Historical Boulder period opens by default.
   - Dataset/forecast/replay selectors work.
   - Forecast, actual-vs-predicted, heatmap, metrics, quality, and replay panels render.
   - No mojibake is visible.
   - Record browser errors separately from SQL verification.

3. Clean stale evidence:
   - Regenerate current Boulder simulator evidence.
   - Decide how to handle reports/p231-smoke.json and reports/simulator_smoke.txt.
   - Preserve migration archives and provenance.

4. If encoding problems are confirmed, fix only the affected source/docs/dashboard generation, regenerate outputs, and rerun tests/Grafana verification.

5. Run a clean dependency/test pass in a temporary environment:
   - install requirements.txt;
   - run pytest;
   - run REST smoke;
   - run Grafana verification;
   - record exact results.

6. Check final specification language:
   - active branding has no P_231;
   - official stack metadata is correct;
   - every forecast states sessions/hour, origin, cutoff, timezone;
   - no live-data, load, queue, waiting-time, occupancy, or shortage claims.

7. Use docs/demo_guide.md and docs/viva.md for the final five-minute college demonstration. State Boulder is historical US data and does not automatically generalize to an Indian college.

## 9. Assumptions and risks

- The project is under OneDrive; synchronization or file locks may affect timestamps.
- .env contains secrets and must remain private.
- data/, artifacts/, and runtime/ are locally present even though ignored by Git.
- No Git history exists for a reliable diff.
- artifacts/current_model.json is the active-model source of truth; older model versions are retained intentionally.
- A new machine needs Docker Desktop, Linux containers/WSL support, a new .env, Python dependencies, and database bootstrap.
- The Boulder snapshot was retrieved in 2026 from a source whose recorded data edit date is 2023; it remains historical.
- The source has no doneChargingTime field; do not add completion-based features without new data.
- Forecast requests need an origin at/after the training cutoff and 168 usable prior hourly observations.
- Changing config.json, data/hourly.csv, or raw data invalidates artifact provenance and requires retraining.
- Future replay/test observations must not be used to tune or retrain the model.
- Do not delete Docker volumes to reset replay; use the scoped replay reset.
- This handoff creation modified only HANDOFF.md. No application code, configuration, dataset, artifact, report, or other documentation file was changed.

