"""Real native model + isolated SQLite storage; PostgreSQL separately needs a running service."""
from pathlib import Path
import json
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, update
from evforecast.api import create_app
from evforecast.artifacts import load_native
from evforecast.bootstrap import bootstrap
from evforecast.config import load_config, ROOT
from evforecast.database import Store, hourly, forecasts, points
from evforecast.service import create_forecast

@pytest.fixture
def store():
    instance = Store("sqlite:///:memory:")
    bootstrap(load_config(), instance)
    yield instance
    instance.engine.dispose()

@pytest.fixture
def bundle():
    return load_native(ROOT)

@pytest.fixture
def client(store, bundle):
    with TestClient(create_app(store=store, bundle=bundle)) as result:
        yield result

def event(generation=1):
    return {"event_id": "arrival-1", "timestamp": "2023-11-01T08:10:00Z",
            "site_id": load_config()["site_id"], "charger_id": "charger-1", "generation": generation}

def quality():
    return json.loads((ROOT/"reports/data_quality.json").read_text())

def test_health_history_quality_metrics(client):
    assert client.get("/health").json()["ready"]
    rows = client.get("/history").json()
    assert len(rows["rows"]) == quality()["hourly_rows"] and rows["units"] == "sessions/hour"
    assert client.get("/data-quality").json()["quality"]["usable_arrivals"] == quality()["usable_arrivals"]
    assert any(r["model"] == "xgboost" for r in client.get("/evaluation").json()["metrics"])
    assert client.get("/history", params={"start":"2018-06-22T00:00:00"}).status_code == 422


def test_repeated_bootstrap_preserves_history_and_initial_forecast(store, bundle):
    dataset_id = bundle["metadata"]["dataset_id"]
    before = store.history(dataset_id)
    runs = store.list_forecasts(dataset_id)
    result = bootstrap(load_config(), store)
    assert store.history(dataset_id) == before
    assert len(store.list_forecasts(dataset_id)) == len(runs)
    assert result["forecast_id"] == runs[0]["forecast_id"]

def test_idempotent_ingestion_and_conflicting_payload(client):
    client.post("/replay-runs/demo")
    first = client.post("/replay-runs/demo/events", json=event())
    second = client.post("/replay-runs/demo/events", json=event())
    assert first.status_code == 200 and first.json()["accepted"]
    assert second.json()["duplicate"]
    assert client.get("/replay-runs/demo/events").json()["count"] == 1
    assert client.post("/replay-runs/demo/events", json={**event(),"charger_id":"other"}).status_code == 409
    assert len(client.get("/history").json()["rows"]) == quality()["hourly_rows"]

@pytest.mark.parametrize("changes", [
    {"timestamp":"2018-06-22T08:00:00"}, {"event_id":""}, {"site_id":"other"},
    {"generation":0}, {"kWhDelivered":5}, {"disconnectTime":"2018-06-22T10:00:00Z"},
])
def test_arrival_validation(client, changes):
    client.post("/replay-runs/demo")
    assert client.post("/replay-runs/demo/events", json={**event(), **changes}).status_code == 422

def test_reset_is_scoped_and_stale_retries_rejected(client):
    for run in ("demo", "unrelated"):
        client.post(f"/replay-runs/{run}")
        client.post(f"/replay-runs/{run}/events", json=event())
    assert client.post("/replay-runs/demo/reset").json()["generation"] == 2
    assert client.get("/replay-runs/demo/events").json()["count"] == 0
    assert client.get("/replay-runs/unrelated/events").json()["count"] == 1
    assert client.post("/replay-runs/demo/events", json=event()).status_code == 409
    assert client.post("/replay-runs/demo/events", json=event(2)).json()["accepted"]

def test_forecast_metadata_and_immutable_runs(client, bundle):
    origin = bundle["metadata"]["test_start"]
    response = client.post("/forecasts", json={"origin":origin})
    assert response.status_code == 201, response.text
    first = response.json()
    second = client.post("/forecasts", json={"origin":origin}).json()
    assert first["forecast_id"] != second["forecast_id"]
    assert first["points"] == second["points"]
    assert len(first["points"]) == len(first["actuals"]) == 24
    assert first["units"] == "sessions/hour" and first["kind"] == "historical_backtest"
    assert first["model_name"] == "xgboost" and first["model_version"].startswith("xgb-")
    stamps = pd.DatetimeIndex([p["timestamp"] for p in first["points"]])
    assert stamps.equals(pd.date_range(origin, periods=24, freq="h"))
    assert pd.Timestamp(first["training_cutoff"]) <= pd.Timestamp(first["origin"])
    assert client.get("/forecasts/"+first["forecast_id"]).json()["points"] == first["points"]

@pytest.mark.parametrize("origin,message", [
    ("2018-06-21T07:00:00Z","cutoff"),
    ("2018-06-22T07:30:00Z","hourly"),
    ("2018-06-22T07:00:00","timezone"),
    ("2026-09-30T07:00:00Z","history"),
])
def test_forecast_rejects_invalid_origin(client, origin, message):
    response = client.post("/forecasts",json={"origin":origin})
    assert response.status_code == 422
    assert message in response.text.lower()

def test_missing_model_returns_readiness_and_prediction_errors(store, tmp_path):
    with TestClient(create_app(store=store, root=tmp_path)) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/forecasts",json={"origin":"2018-06-22T07:00:00Z"}).status_code == 503

def test_service_never_uses_future_actuals(store, bundle):
    origin = pd.Timestamp(bundle["metadata"]["test_start"])
    first = create_forecast(store,bundle,origin)
    with store.engine.begin() as connection:
        connection.execute(update(hourly).where(hourly.c.timestamp >= origin.to_pydatetime()).values(arrivals=999999))
    second = create_forecast(store,bundle,origin)
    assert first["points"] == second["points"]
    assert first["actuals"] != second["actuals"]

def test_bootstrap_does_not_duplicate_history_or_demo(store):
    config=load_config()
    first=bootstrap(config,store)
    second=bootstrap(config,store)
    assert first==second
    with store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(hourly))==quality()["hourly_rows"]
        assert connection.scalar(select(func.count()).select_from(forecasts))==1
        assert connection.scalar(select(func.count()).select_from(points))==24
