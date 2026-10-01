"""Shared forecast service used by both REST and reproducible DB bootstrap."""
import pandas as pd
from .database import utc
from .models import forecast, feature_row

def create_forecast(store, bundle, origin):
    metadata = bundle["metadata"]
    origin = pd.Timestamp(origin).tz_convert("UTC")
    if origin != origin.floor("h"):
        raise ValueError("Forecast origin must be an exact hour boundary.")
    if origin < pd.Timestamp(metadata["training_cutoff_exclusive"]):
        raise ValueError("Requested origin precedes the model training cutoff; retrain an earlier model for this backtest.")
    if not store.dataset(metadata["dataset_id"]):
        raise ValueError("Model dataset is not in the database. Run python -m evforecast bootstrap-db.")
    start = origin - pd.Timedelta(hours=168)
    rows = store.history(metadata["dataset_id"], start=start, end=origin)
    if not rows:
        raise ValueError("Insufficient history: need 168 complete hourly observations before origin.")
    history = pd.Series([r["arrivals"] for r in rows], index=pd.DatetimeIndex([r["timestamp"] for r in rows]), dtype=float)
    feature_row(origin, history, metadata["timezone"])
    predicted = forecast(bundle, history, origin, "xgboost")
    target_actual = store.history(metadata["dataset_id"], origin, origin + pd.Timedelta(hours=24))
    kind = "historical_backtest" if target_actual else "historical_projection"
    run = dict(dataset_id=metadata["dataset_id"], origin=utc(origin),
               model_version=metadata["model_version"], model_name="xgboost",
               training_cutoff=utc(metadata["training_cutoff_exclusive"]),
               site_timezone=metadata["timezone"], units="sessions/hour", kind=kind,
               last_observation=utc(history.index.max()))
    identifier = store.save_forecast(run, predicted)
    return store.get_forecast(identifier)
