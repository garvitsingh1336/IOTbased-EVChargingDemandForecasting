# Executed verification — Boulder migration

## Latest verification: 2026-10-01

### Services confirmed running
- Docker Desktop: v29.8.1, Linux containers active.
- PostgreSQL 16.10-alpine: healthy, port 5432.
- Grafana 12.2.0: running, port 3000, commit 92f1fba9b4b6700328e99e97328d6639df8ddc3d.
- FastAPI/Uvicorn: responding on 127.0.0.1:8000.
- API health: ready=true, model_ready=true, database_ready=true, historical_data_ready=true, model_version=xgb-007fa5a4ccf4a14bec33.

### Tests
- 50 pytest tests passed; one non-failing pytest cache-permission warning (OneDrive lock).
- Tests cover: JSON recovery, source adapters, duplicates, DST, aggregation, forecast leakage, API validation, storage, replay idempotency, artifact checksums, and Grafana configuration.

### Smoke tests
- PostgreSQL + Uvicorn smoke passed: readiness, repeat bootstrap (idempotent), 3 unique arrival events ingested, repeated event rejected, resume deduplication confirmed, 24-hour forecast stored/retrieved, metadata/cutoff/model_version correct, OpenAPI 200, original source hash unchanged.
- REST replay: 10 Boulder arrival-only events accepted with --reset, no duplicates, correct site_id (boulder-carpenter-park).

### Grafana verification
- Datasource health: OK.
- Read-only role: verified (grafana_reader cannot write).
- All 18 data-panel SQL queries returned rows successfully.
- Visual browser check: not automated; manual browser QA recommended.

### Stale artifacts cleaned
- reports/p231-smoke.json → archived to reports/archive/ (contained old P_231 branding and ACN model).
- reports/simulator_smoke.txt → archived to reports/archive/ (contained old ACN 2018 events).
- reports/verification.json → archived to reports/archive/ (contained old Streamlit/336-hour values).

### Branding audit
- No active source code, configuration, or documentation contains P_231 branding.
- Only reference is in HANDOFF.md as historical context.

### Mojibake audit
- No mojibake patterns (â€", â†', garbled emoji) found in dashboard JSON, README.md, or docs/.

### Not verified
- Browser visual rendering of Grafana panels (SQL success ≠ visual QA).
- Concurrent ingestion stress testing.
- Clean virtual environment dependency installation from scratch.

## Previous verification (Boulder migration)

- Official source: 148,136 advertised record IDs retrieved; source edit version stable throughout download; raw SHA-256 stored in data/raw/boulder_download.json.
- Original ACN preserved; previous project outputs archived in runtime/before-boulder/.
- Full preprocessing, XGBoost tuning/training and chronological evaluation completed on real Boulder sessions.

Evidence: reports/evforecast-smoke.json, reports/grafana-verification.json, reports/test_metrics.csv, reports/training.json, reports/data_quality.json.
