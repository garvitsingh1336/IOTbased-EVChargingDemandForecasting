# REST API

Start: `.\.venv\Scripts\python.exe -m uvicorn evforecast.api:app --host 127.0.0.1 --port 8000`.
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
| GET /forecasts/{id} | Stored predictions, metadata and matching historical actuals |
| GET /evaluation | Model/baseline MAE and RMSE |
| GET /data-quality | Dataset coverage, quality and warnings |

Arrival example (use the generation returned for the run):
```json
{"event_id":"example-arrival-1","timestamp":"2023-10-31T10:00:00-06:00","site_id":"boulder-carpenter-park","charger_id":"BOULDER / CARPENTER PARK1","generation":1}
```
First arrival returns `accepted: true, duplicate: false`; repeating it returns `accepted: false, duplicate: true`. Altering its fields or using a stale generation returns 409. Missing timezone/unknown extra fields return 422. No final energy/departure fields are accepted.

Forecast request:
```json
{"origin":"2023-10-31T06:00:00+00:00"}
```
Response (201) includes `forecast_id`, `origin`, `model_version`, `training_cutoff`, `site_timezone`, `units`, `last_observation`, `kind`, 24 `points`, matching `actuals`, `predicted_total_arrivals`, and `busiest_hour`. Historical actuals are queried separately after prediction. A request before the training cutoff or without 168 prior usable hours returns 422. Missing model/database returns 503. Training is never triggered by inference.

Local-only prototype: no production authentication. Database operations use bound parameters. Grafana uses a separate read-only role; replay rows never contribute to training aggregates.
