"""EV Forecasting FastAPI: no training inside ordinary HTTP prediction requests."""
from contextlib import asynccontextmanager
from typing import Annotated
from datetime import timezone
import logging

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, AwareDatetime, Field, ConfigDict, field_validator
from sqlalchemy.exc import SQLAlchemyError

from .artifacts import load_native
from .config import ROOT
from .database import Store, ConflictError
from .service import create_forecast

RunId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,80}$")]

class Arrival(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=200)
    timestamp: AwareDatetime
    site_id: str = Field(min_length=1, max_length=40)
    charger_id: str = Field(min_length=1, max_length=100)
    generation: int = Field(ge=1)

    @field_validator("event_id", "site_id", "charger_id")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Identifier cannot be blank.")
        return value

class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: AwareDatetime

    @field_validator("origin")
    @classmethod
    def hourly(cls, value):
        if value.minute or value.second or value.microsecond:
            raise ValueError("Origin must be an exact hourly boundary.")
        return value.astimezone(timezone.utc)

def create_app(store=None, bundle=None, root=ROOT):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = store
        app.state.bundle = bundle
        app.state.model_error = None
        app.state.database_error = None
        if app.state.bundle is None:
            try:
                app.state.bundle = load_native(root)
            except (FileNotFoundError, ValueError, KeyError) as error:
                app.state.model_error = str(error)
        if app.state.store is None:
            try:
                app.state.store = Store()
            except ValueError as error:
                app.state.database_error = str(error)
        yield
        if store is None and app.state.store is not None:
            app.state.store.engine.dispose()

    app = FastAPI(title="IoT-Based EV Charging Demand Forecasting", version="2.0.0",
                  description="Historical replay; site-wide session-arrival demand in sessions/hour.", lifespan=lifespan)

    def require_store():
        if app.state.store is None:
            raise HTTPException(503, app.state.database_error or "Database unavailable.")
        try:
            app.state.store.healthy()
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable. Start PostgreSQL and run bootstrap-db.")
        return app.state.store

    def require_model():
        if app.state.bundle is None:
            raise HTTPException(503, app.state.model_error or "Model missing; train offline, then restart API.")
        return app.state.bundle

    @app.exception_handler(SQLAlchemyError)
    async def database_failure(request, error):
        logging.getLogger(__name__).error("Database operation failed (%s)", type(error).__name__)
        return JSONResponse(status_code=503, content={"detail": "Database unavailable or schema missing. Run bootstrap-db."})

    @app.get("/health")
    def health():
        database_ok = False
        data_ready = False
        try:
            db = require_store()
            database_ok = True
            if app.state.bundle:
                data_ready = db.dataset(app.state.bundle["metadata"]["dataset_id"]) is not None
        except (HTTPException, SQLAlchemyError):
            pass
        ready = bool(app.state.bundle) and database_ok and data_ready
        return JSONResponse(status_code=200 if ready else 503, content={
            "ready": ready, "model_ready": app.state.bundle is not None,
            "database_ready": database_ok, "historical_data_ready": data_ready,
            "model_version": app.state.bundle["metadata"]["model_version"] if app.state.bundle else None,
            "model_error": app.state.model_error})

    @app.post("/replay-runs/{run_id}")
    def replay_run(run_id: RunId):
        return require_store().create_replay(run_id)

    @app.post("/replay-runs/{run_id}/reset")
    def reset_run(run_id: RunId):
        try:
            return require_store().reset_replay(run_id)
        except KeyError:
            raise HTTPException(404, "Replay run does not exist.")

    @app.post("/replay-runs/{run_id}/events")
    def receive(run_id: RunId, arrival: Arrival):
        model = require_model()
        if arrival.site_id != model["metadata"]["configuration"]["site_id"]:
            raise HTTPException(422, "This model supports only its configured site.")
        try:
            inserted = require_store().ingest(run_id, arrival.model_dump())
        except KeyError:
            raise HTTPException(404, "Create the replay run first.")
        except ConflictError as error:
            raise HTTPException(409, str(error))
        return {"run_id": run_id, "event_id": arrival.event_id,
                "accepted": inserted, "duplicate": not inserted,
                "label": "Historical data replay — simulated IoT feed"}

    @app.get("/replay-runs/{run_id}/events")
    def incoming(run_id: RunId):
        rows = require_store().replay_events(run_id)
        return {"run_id": run_id, "count": len(rows), "events": rows,
                "label": "Historical data replay — simulated IoT feed"}

    @app.get("/history")
    def history(start: AwareDatetime | None = None, end: AwareDatetime | None = None,
                limit: int = Query(20000, ge=1, le=20000)):
        if start is not None and end is not None and start >= end:
            raise HTTPException(422, "start must precede end (exclusive).")
        metadata = require_model()["metadata"]
        return {"dataset_id": metadata["dataset_id"], "timezone": metadata["timezone"],
                "units": "sessions/hour", "end_exclusive": True, "limit": limit,
                "rows": require_store().history(metadata["dataset_id"], start, end, limit)}

    @app.post("/forecasts", status_code=201)
    def predict(request: ForecastRequest):
        try:
            return create_forecast(require_store(), require_model(), request.origin)
        except ValueError as error:
            raise HTTPException(422, str(error))

    @app.get("/forecasts")
    def list_predictions():
        return require_store().list_forecasts(require_model()["metadata"]["dataset_id"])

    @app.get("/forecasts/{forecast_id}")
    def get_prediction(forecast_id: str):
        result = require_store().get_forecast(forecast_id)
        if result is None:
            raise HTTPException(404, "Forecast run not found.")
        return result

    @app.get("/evaluation")
    def evaluation():
        metadata = require_model()["metadata"]
        return {"model_version": metadata["model_version"], "primary_ml_model": "xgboost",
                "validation_winner": metadata["selected_model"], "units": "sessions/hour",
                "metrics": require_store().metrics(metadata["model_version"])}

    @app.get("/data-quality")
    def data_quality():
        row = require_store().dataset(require_model()["metadata"]["dataset_id"])
        if row is None:
            raise HTTPException(503, "Historical data missing; run bootstrap-db.")
        return row

    return app

app = create_app()
