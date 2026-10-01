"""Integration invariants checked against the actual trained historical project."""
import json
from pathlib import Path
import joblib
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "reports/evaluation.json").exists(),
                                reason="Run pipeline before artifact integration tests")

def test_fit_cutoffs_and_all_model_target_pairs_match():
    metadata = json.loads((ROOT / "reports/evaluation.json").read_text())
    bundle = joblib.load(ROOT / "artifacts/forecast_bundle.joblib")
    assert pd.Timestamp(bundle["fit_end"]) < pd.Timestamp(metadata["test_start"])
    targets = pd.read_csv(ROOT / "reports/test_predictions.csv")
    pairs = [set(zip(group.origin, group.timestamp)) for _, group in targets.groupby("model")]
    assert len(pairs) == len(metadata["evaluated_models"]) and all(item == pairs[0] for item in pairs)
    validation = pd.read_csv(ROOT / "reports/validation_predictions.csv")
    assert set(validation.timestamp).isdisjoint(set(targets.timestamp))
    assert targets.groupby(["model", "origin"]).size().eq(24).all()

def test_selection_is_validation_winner_and_means_are_pretest_only():
    metadata = json.loads((ROOT / "reports/evaluation.json").read_text())
    validation = pd.read_csv(ROOT / "reports/validation_metrics.csv").sort_values(["MAE","RMSE","model"])
    assert metadata["selected_model"] == validation.iloc[0]["model"]
    bundle = joblib.load(ROOT / "artifacts/forecast_bundle.joblib")
    hourly = pd.read_csv(ROOT / "data/hourly.csv")
    hourly["timestamp"] = pd.to_datetime(hourly.timestamp, utc=True)
    history = hourly[hourly.timestamp < pd.Timestamp(metadata["test_start"])].set_index("timestamp").arrivals
    local = history.index.tz_convert(metadata["timezone"])
    expected = history.groupby(local.dayofweek * 24 + local.hour).mean().dropna().to_dict()
    assert bundle["hour_means"] == expected
