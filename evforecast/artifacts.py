"""Native XGBoost inference artifacts, versioned by content rather than pickle."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from xgboost import XGBRegressor
from .models import FEATURE_NAMES
from .config import write_json

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save_native(bundle, root):
    directory = root / "artifacts/models"
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / "candidate.ubj"
    bundle["xgboost"].save_model(temporary)
    provenance = bundle["provenance"]
    model_hash = file_hash(temporary)
    identity = json.dumps({"model_sha256": model_hash, "provenance": provenance}, sort_keys=True).encode()
    version = "xgb-" + hashlib.sha256(identity).hexdigest()[:20]
    destination = directory / version
    destination.mkdir(exist_ok=True)
    temporary.replace(destination / "xgboost.ubj")
    metadata = {**provenance, "model_version": version, "model_sha256": model_hash,
                "feature_schema": FEATURE_NAMES, "fit_end": str(bundle["fit_end"]),
                "training_cutoff_exclusive": provenance["test_start"],
                "dataset_id": provenance["processed_hourly_sha256"],
                "units": "sessions/hour"}
    write_json(destination / "metadata.json", metadata)
    write_json(root / "artifacts/current_model.json", {"model_version": version})
    return metadata

def load_native(root):
    pointer = root / "artifacts/current_model.json"
    if not pointer.exists():
        raise FileNotFoundError("XGBoost model missing. Run python -m evforecast train.")
    version = json.loads(pointer.read_text())["model_version"]
    if not isinstance(version, str) or not version.startswith("xgb-") or not version[4:].isalnum():
        raise ValueError("Invalid local model version.")
    directory = root / "artifacts/models" / version
    metadata = json.loads((directory / "metadata.json").read_text())
    if metadata["feature_schema"] != FEATURE_NAMES:
        raise ValueError("Model feature schema does not match inference code.")
    if metadata["model_sha256"] != file_hash(directory / "xgboost.ubj"):
        raise ValueError("Model artifact checksum mismatch.")
    model = XGBRegressor(n_jobs=1)
    model.load_model(directory / "xgboost.ubj")
    model.set_params(n_jobs=1)
    return {"xgboost": model, "hour_means": {}, "global_mean": 0,
            "fit_end": pd.Timestamp(metadata["fit_end"]), "timezone": metadata["timezone"],
            "metadata": metadata}
