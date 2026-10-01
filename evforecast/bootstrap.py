"""Offline import of immutable real historical data and evaluation outputs."""
import json
import pandas as pd
from .artifacts import load_native, file_hash
from .database import Store
from .service import create_forecast

def bootstrap(config, store=None):
    root = config["root"]
    bundle = load_native(root)
    metadata = bundle["metadata"]
    if file_hash(root / "data/hourly.csv") != metadata["dataset_id"]:
        raise ValueError("Processed data differs from model provenance; retrain first.")
    store = store or Store()
    store.initialize()
    quality = json.loads((root / "reports/data_quality.json").read_text())
    data = pd.read_csv(root / "data/hourly.csv")
    store.import_dataset(metadata["dataset_id"], config["site_id"], config["timezone"], quality, data)
    for split in ("validation", "test"):
        store.save_evaluations(metadata, split, pd.read_csv(root / f"reports/{split}_metrics.csv"))
    store.create_replay("demo")
    existing = store.list_forecasts(metadata["dataset_id"])
    # Idempotent bootstrap: don't create a duplicate initial demo run.
    matching = [r for r in existing if r["model_version"] == metadata["model_version"] and
                pd.Timestamp(r["origin"]) == pd.Timestamp(metadata["test_start"])]
    demo = store.get_forecast(matching[0]["forecast_id"]) if matching else create_forecast(
        store, bundle, pd.Timestamp(metadata["test_start"]))
    return {"dataset_id": metadata["dataset_id"], "hourly_rows": len(data),
            "forecast_id": demo["forecast_id"], "origin": str(demo["origin"])}
