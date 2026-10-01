"""Parameterized SQLAlchemy storage. PostgreSQL is the Grafana production path.
SQLite is supported explicitly for automated tests and a service-free API smoke test.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import uuid4

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from sqlalchemy import (create_engine, MetaData, Table, Column, String, Integer, Float,
                        DateTime, JSON, ForeignKey, select, delete, update, text)
from sqlalchemy.engine import URL
from sqlalchemy.pool import StaticPool
from .config import ROOT

schema = MetaData()
datasets = Table("datasets", schema,
    Column("dataset_id", String(64), primary_key=True),
    Column("site_id", String(40), nullable=False),
    Column("site_timezone", String(80), nullable=False),
    Column("quality", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False))
hourly = Table("hourly_demand", schema,
    Column("dataset_id", ForeignKey("datasets.dataset_id"), primary_key=True),
    Column("timestamp", DateTime(timezone=True), primary_key=True),
    Column("arrivals", Float),
    Column("coverage_status", String(32), nullable=False))
replays = Table("replay_runs", schema,
    Column("run_id", String(80), primary_key=True),
    Column("generation", Integer, nullable=False),
    Column("label", String(120), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False))
events = Table("arrival_events", schema,
    Column("run_id", ForeignKey("replay_runs.run_id"), primary_key=True),
    Column("event_id", String(200), primary_key=True),
    Column("generation", Integer, nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False, index=True),
    Column("site_id", String(40), nullable=False),
    Column("charger_id", String(100), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False))
forecasts = Table("forecast_runs", schema,
    Column("forecast_id", String(36), primary_key=True),
    Column("dataset_id", ForeignKey("datasets.dataset_id"), nullable=False, index=True),
    Column("origin", DateTime(timezone=True), nullable=False, index=True),
    Column("model_version", String(80), nullable=False),
    Column("model_name", String(40), nullable=False),
    Column("training_cutoff", DateTime(timezone=True), nullable=False),
    Column("site_timezone", String(80), nullable=False),
    Column("units", String(40), nullable=False),
    Column("kind", String(40), nullable=False),
    Column("last_observation", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False))
points = Table("forecast_points", schema,
    Column("forecast_id", ForeignKey("forecast_runs.forecast_id"), primary_key=True),
    Column("timestamp", DateTime(timezone=True), primary_key=True),
    Column("horizon", Integer, nullable=False),
    Column("prediction", Float, nullable=False))
evaluations = Table("evaluation_results", schema,
    Column("model_version", String(80), primary_key=True),
    Column("split", String(20), primary_key=True),
    Column("model", String(40), primary_key=True),
    Column("dataset_id", ForeignKey("datasets.dataset_id"), nullable=False),
    Column("mae", Float, nullable=False),
    Column("rmse", Float, nullable=False),
    Column("origins", Integer, nullable=False),
    Column("forecast_hours", Integer, nullable=False),
    Column("period_start", DateTime(timezone=True), nullable=False),
    Column("period_end", DateTime(timezone=True), nullable=False),
    Column("details", JSON, nullable=False))

def utc(value):
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        # DB SQLite rows are naive UTC; external timestamps are validated before this layer.
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC").to_pydatetime()

def now():
    return datetime.now(timezone.utc)

def configured_url():
    load_dotenv(ROOT / ".env", override=False)
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Database not configured. Run scripts/setup_env.py, then docker compose up -d.")
    return URL.create("postgresql+psycopg", username="ev_app", password=password,
                      host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
                      port=int(os.getenv("POSTGRES_PORT", "5432")), database="evforecast")

class ConflictError(ValueError):
    pass

class Store:
    def __init__(self, url=None):
        address = url if url is not None else configured_url()
        options = {"pool_pre_ping": True}
        if str(address).startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}
            if str(address).endswith(":memory:"):
                options["poolclass"] = StaticPool
        else:
            options["connect_args"] = {"connect_timeout": 3}
        self.engine = create_engine(address, **options)

    def initialize(self):
        schema.create_all(self.engine)

    def healthy(self):
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True

    def insert_ignore(self, connection, table, values):
        if self.engine.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        elif self.engine.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise ValueError("Only PostgreSQL and explicit SQLite testing are supported.")
        # psycopg can report rowcount=-1; RETURNING reliably identifies an insert.
        statement = insert(table).values(values).on_conflict_do_nothing().returning(*table.primary_key.columns)
        return connection.execute(statement).first() is not None

    def dataset(self, dataset_id):
        with self.engine.connect() as connection:
            row = connection.execute(select(datasets).where(datasets.c.dataset_id == dataset_id)).mappings().first()
            return dict(row) if row else None

    def import_dataset(self, dataset_id, site_id, timezone_name, quality, frame):
        with self.engine.begin() as connection:
            result = self.insert_ignore(connection, datasets, dict(dataset_id=dataset_id, site_id=site_id,
                      site_timezone=timezone_name, quality=quality, created_at=now()))
            if not result:
                return False
            rows = [dict(dataset_id=dataset_id, timestamp=utc(row.timestamp),
                         arrivals=None if pd.isna(row.arrivals) else float(row.arrivals),
                         coverage_status=row.coverage_status) for row in frame.itertuples()]
            connection.execute(hourly.insert(), rows)
        return True

    def history(self, dataset_id, start=None, end=None, limit=20000):
        query = select(hourly).where(hourly.c.dataset_id == dataset_id)
        if start is not None:
            query = query.where(hourly.c.timestamp >= utc(start))
        if end is not None:
            query = query.where(hourly.c.timestamp < utc(end))
        with self.engine.connect() as connection:
            rows = connection.execute(query.order_by(hourly.c.timestamp).limit(limit)).mappings().all()
        return [{**dict(row), "timestamp": utc(row["timestamp"])} for row in rows]

    def create_replay(self, run_id):
        with self.engine.begin() as connection:
            self.insert_ignore(connection, replays, dict(run_id=run_id, generation=1,
                label="Historical data replay â€” simulated IoT feed", created_at=now()))
            return dict(connection.execute(select(replays).where(replays.c.run_id == run_id)).mappings().one())

    def reset_replay(self, run_id):
        with self.engine.begin() as connection:
            row = connection.execute(select(replays).where(replays.c.run_id == run_id).with_for_update()).mappings().first()
            if row is None:
                raise KeyError(run_id)
            connection.execute(delete(events).where(events.c.run_id == run_id))
            connection.execute(update(replays).where(replays.c.run_id == run_id).values(generation=row["generation"]+1))
            return {"run_id": run_id, "generation": row["generation"]+1, "reset": True}

    def ingest(self, run_id, event):
        event = {**event, "timestamp": utc(event["timestamp"])}
        with self.engine.begin() as connection:
            run = connection.execute(select(replays).where(replays.c.run_id == run_id).with_for_update()).mappings().first()
            if run is None:
                raise KeyError(run_id)
            if event["generation"] != run["generation"]:
                raise ConflictError("Stale replay generation; retrieve/create the replay run again after reset.")
            result = self.insert_ignore(connection, events, {**event, "run_id": run_id, "received_at": now()})
            existing = connection.execute(select(events).where(
                events.c.run_id == run_id, events.c.event_id == event["event_id"])).mappings().one()
            if any(existing[key] != event[key] for key in ("site_id", "charger_id", "generation")) or utc(existing["timestamp"]) != event["timestamp"]:
                raise ConflictError("Event ID already exists with different arrival fields.")
            return result

    def replay_events(self, run_id):
        with self.engine.connect() as connection:
            rows = connection.execute(select(events).where(events.c.run_id == run_id)
                .order_by(events.c.timestamp, events.c.event_id)).mappings().all()
        return [{**dict(row), "timestamp": utc(row["timestamp"]), "received_at": utc(row["received_at"])} for row in rows]

    def save_forecast(self, metadata, predictions):
        # Every request creates a new immutable run, including repeat requests at the same origin.
        identifier = str(uuid4())
        origin = utc(metadata["origin"])
        expected = pd.date_range(origin, periods=24, freq="h")
        if len(predictions) != 24 or not predictions.index.equals(expected) or not np.isfinite(predictions.to_numpy()).all() or (predictions < 0).any():
            raise ValueError("Forecast storage requires 24 finite, nonnegative, consecutive hourly predictions.")
        with self.engine.begin() as connection:
            connection.execute(forecasts.insert().values(forecast_id=identifier, **metadata, created_at=now()))
            connection.execute(points.insert(), [dict(forecast_id=identifier, timestamp=utc(ts),
                horizon=i+1, prediction=float(value)) for i, (ts, value) in enumerate(predictions.items())])
        return identifier

    def get_forecast(self, identifier):
        with self.engine.connect() as connection:
            row = connection.execute(select(forecasts).where(forecasts.c.forecast_id == identifier)).mappings().first()
            if row is None:
                return None
            result = dict(row)
            rows = connection.execute(select(points.c.timestamp, points.c.horizon, points.c.prediction)
                .where(points.c.forecast_id == identifier).order_by(points.c.timestamp)).mappings().all()
            result["points"] = [{**dict(item), "timestamp": utc(item["timestamp"])} for item in rows]
            # One-to-one join within a single forecast; actual counts are never summed over runs.
            actual = connection.execute(select(points.c.timestamp, hourly.c.arrivals).select_from(
                points.outerjoin(hourly, (hourly.c.dataset_id == row["dataset_id"]) &
                                 (hourly.c.timestamp == points.c.timestamp)))
                .where(points.c.forecast_id == identifier).order_by(points.c.timestamp)).mappings().all()
            result["actuals"] = [{**dict(item), "timestamp": utc(item["timestamp"])} for item in actual]
        for field in ("origin", "training_cutoff", "last_observation", "created_at"):
            result[field] = utc(result[field])
        result["predicted_total_arrivals"] = sum(p["prediction"] for p in result["points"])
        result["busiest_hour"] = max(result["points"], key=lambda p: p["prediction"])
        return result

    def list_forecasts(self, dataset_id):
        with self.engine.connect() as connection:
            rows = connection.execute(select(forecasts).where(forecasts.c.dataset_id == dataset_id)
                                      .order_by(forecasts.c.created_at.desc()).limit(100)).mappings().all()
        return [{**dict(row), "origin": utc(row["origin"])} for row in rows]

    def save_evaluations(self, metadata, split, frame):
        begin = metadata["validation_start"] if split == "validation" else metadata["test_start"]
        end = metadata["test_start"] if split == "validation" else metadata["test_end_exclusive"]
        with self.engine.begin() as connection:
            for row in frame.itertuples():
                self.insert_ignore(connection, evaluations, dict(model_version=metadata["model_version"],
                    dataset_id=metadata["dataset_id"], split=split, model=row.model, mae=row.MAE, rmse=row.RMSE,
                    origins=row.origins, forecast_hours=row.forecast_hours,
                    period_start=utc(begin), period_end=utc(end), details=metadata))

    def metrics(self, version):
        with self.engine.connect() as connection:
            rows = connection.execute(select(evaluations).where(evaluations.c.model_version == version)).mappings().all()
        return [dict(row) for row in rows]
