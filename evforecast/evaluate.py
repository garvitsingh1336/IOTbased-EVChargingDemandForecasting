"""Chronological tuning, frozen held-out evaluation, and historical demo artifact."""
import json
import hashlib
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn
import plotly.express as px
from sklearn.metrics import mean_absolute_error, mean_squared_error

from .artifacts import save_native
from .config import write_json
from .data import load_hourly
from .models import LOOKBACK, MODEL_NAMES, fit_bundle, forecast, feature_row

def split_periods(series, config):
    tz = config["timezone"]
    end = (series.index[-1] + pd.Timedelta(hours=1)).tz_convert(tz)
    test = end - pd.DateOffset(days=config["test_days"])
    validation = test - pd.DateOffset(days=config["validation_days"])
    if validation - series.index[0] < pd.Timedelta(days=config["minimum_training_days"]):
        raise ValueError("Insufficient history: need training days plus validation and test days. Obtain more real data or explicitly shorten evaluation in config.json.")
    return validation.tz_convert("UTC"), test.tz_convert("UTC"), end.tz_convert("UTC")

def origins_for(series, begin, end, timezone):
    candidates = pd.date_range(begin, end-pd.Timedelta(hours=24), freq="24h")
    accepted, skipped = [], []
    for origin in candidates:
        target = series.reindex(pd.date_range(origin, periods=24, freq="h"))
        try:
            feature_row(origin, series, timezone)
            usable = not target.isna().any()
        except ValueError:
            usable = False
        (accepted if usable else skipped).append(origin)
    if not accepted:
        raise ValueError("No evaluable 24-hour origins with complete lookback and targets.")
    return accepted, skipped

def predict_origins(bundle, series, origins, models=MODEL_NAMES):
    records = []
    for origin in origins:
        for name in models:
            predictions = forecast(bundle, series, origin, name)
            for horizon, (timestamp, prediction) in enumerate(predictions.items(), start=1):
                records.append({"origin": origin, "timestamp": timestamp, "horizon": horizon,
                                "model": name, "actual": float(series.loc[timestamp]), "prediction": prediction})
    return pd.DataFrame(records)

def metrics_for(predictions):
    records = []
    for name, group in predictions.groupby("model"):
        records.append({"model": name, "MAE": float(mean_absolute_error(group.actual, group.prediction)),
                        "RMSE": float(np.sqrt(mean_squared_error(group.actual, group.prediction))),
                        "origins": int(group.origin.nunique()), "forecast_hours": len(group)})
    return pd.DataFrame(records).sort_values(["MAE", "RMSE", "model"]).reset_index(drop=True)

def train(config):
    root = config["root"]
    series = load_hourly(root)
    validation, test, end = split_periods(series, config)
    val_origins, val_skipped = origins_for(series, validation, test, config["timezone"])
    train_series = series.loc[series.index < validation]
    tuning = []
    candidates = {}
    include_rf = config.get("include_random_forest", True)
    names = [name for name in MODEL_NAMES if include_rf or name != "random_forest"]
    leaf = config.get("rf_benchmark_leaf", 10)
    for index, params in enumerate(config["xgboost_grid"]):
        bundle = fit_bundle(train_series, config, leaf, params, include_rf=False)
        pred = predict_origins(bundle, series, val_origins, ["xgboost"])
        metric = metrics_for(pred).iloc[0].to_dict()
        tuning.append({"candidate": index, "parameters": params, **metric})
        candidates[index] = bundle
    tuning.sort(key=lambda row: (row["MAE"], row["RMSE"], row["candidate"]))
    best_params = tuning[0]["parameters"]
    validation_bundle = fit_bundle(train_series, config, leaf, best_params, include_rf)
    validation_predictions = predict_origins(validation_bundle, series, val_origins, names)
    validation_metrics = metrics_for(validation_predictions)
    selected = validation_metrics.iloc[0]["model"]
    final_bundle = fit_bundle(series.loc[series.index < test], config, leaf, best_params, include_rf)
    provenance = {
        "technology": "Embedded IOT",
        "subdomain": "Charging Infrastructure", "official_stack": ["REST API", "Python", "XGBoost", "Grafana"],
        "primary_model": "xgboost", "evaluated_models": names,
        "title": "IoT-Based EV Charging Demand Forecasting",
        "target": "Site-wide session arrivals, sessions/hour",
        "strategy": "Recursive next 24 elapsed hours; unavailable lags use predictions.",
        "selected_model": selected, "selection": "Lowest validation MAE; RMSE then model name break ties.",
        "validation_start": validation.isoformat(), "test_start": test.isoformat(),
        "test_end_exclusive": end.isoformat(), "training_start": series.index[0].isoformat(),
        "validation_origins": len(val_origins), "validation_skipped_origins": [str(v) for v in val_skipped],
        "tuning": tuning, "timezone": config["timezone"], "random_seed": config["random_seed"],
        "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__},
        "processed_hourly_sha256": hashlib.sha256((root / "data/hourly.csv").read_bytes()).hexdigest(),
        "configuration": {k: v for k, v in config.items() if k != "root"},
        "data_sha256": json.loads((root / "reports/recovery.json").read_text())["source_sha256"],
        "notes": [
            "XGBoost, RF benchmark and hour-of-week means remain frozen during each evaluation period.",
            "Observed arrivals before each later origin may be used as lag inputs, never observations at or after that origin.",
            "Origins are 24 elapsed hours apart, starting at local midnight of each split.",
            "Fractional nonnegative predictions are expected counts; metrics use unrounded values.",
            "No calibrated prediction intervals are claimed.",
        ],
    }
    final_bundle.update(selected_model=selected, provenance=provenance)
    metadata = save_native(final_bundle, root)
    provenance["model_version"] = metadata["model_version"]
    joblib.dump(final_bundle, root / "artifacts/forecast_bundle.joblib")
    validation_predictions.to_csv(root / "reports/validation_predictions.csv", index=False)
    validation_metrics.to_csv(root / "reports/validation_metrics.csv", index=False)
    write_json(root / "reports/training.json", provenance)
    return provenance

def evaluate(config):
    root = config["root"]
    artifact = root / "artifacts/forecast_bundle.joblib"
    if not artifact.exists():
        raise FileNotFoundError("Run python -m evforecast train first.")
    # Only load artifacts generated locally by this project; never untrusted joblib files.
    bundle = joblib.load(artifact)
    provenance = bundle["provenance"]
    current_hash = json.loads((root / "reports/recovery.json").read_text())["source_sha256"]
    if (provenance["data_sha256"] != current_hash
        or provenance.get("processed_hourly_sha256") != hashlib.sha256((root / "data/hourly.csv").read_bytes()).hexdigest()
        or provenance.get("configuration") != {k: v for k, v in config.items() if k != "root"}):
        raise ValueError("Data/config differs from model provenance; rerun training.")
    series = load_hourly(root)
    test, end = pd.Timestamp(provenance["test_start"]), pd.Timestamp(provenance["test_end_exclusive"])
    origins, skipped = origins_for(series, test, end, config["timezone"])
    predictions = predict_origins(bundle, series, origins, provenance["evaluated_models"])
    metrics = metrics_for(predictions)
    predictions.to_csv(root / "reports/test_predictions.csv", index=False)
    metrics.to_csv(root / "reports/test_metrics.csv", index=False)
    predictions["local_hour"] = predictions.timestamp.dt.tz_convert(config["timezone"]).dt.hour
    predictions["absolute_error"] = abs(predictions.actual - predictions.prediction)
    errors = predictions.groupby(["model", "local_hour"], as_index=False).absolute_error.mean()
    errors.to_csv(root / "reports/errors_by_hour.csv", index=False)
    selected = bundle["selected_model"]
    demo_origin = origins[0]
    demo = predictions.loc[(predictions.origin == demo_origin) & (predictions.model == "xgboost")].copy()
    demo.to_csv(root / "artifacts/demo_forecast.csv", index=False)
    report = {
        **provenance, "test_origins": len(origins), "test_skipped_origins": [str(v) for v in skipped],
        "test_local_dates": int(predictions.timestamp.dt.tz_convert(config["timezone"]).dt.date.nunique()),
        "unique_test_hours": int(predictions.timestamp.nunique()),
        "test_metrics": metrics.to_dict("records"), "demo_origin": demo_origin.isoformat(),
        "demo_last_observation": (demo_origin-pd.Timedelta(hours=1)).isoformat(),
        "test_best_model_descriptive_only": metrics.iloc[0]["model"],
    }
    write_json(root / "reports/evaluation.json", report)
    write_json(root / "artifacts/models" / provenance["model_version"] / "evaluation.json", report)
    lines = ["# Model evaluation", "", "Target: site-wide session arrivals (sessions/hour).", "",
             f"Primary specification ML model: **XGBoost**. Validation winner across all methods: **{selected}**.",
             f"Test: {test} through {end} (exclusive). {len(origins)} origins, "
             f"{report['unique_test_hours']} unique forecast hours, {report['test_local_dates']} local dates.",
             "", "| Model | MAE | RMSE | Origins |", "|---|---:|---:|---:|"]
    lines += [f"| {r.model} | {r.MAE:.4f} | {r.RMSE:.4f} | {r.origins} |" for r in metrics.itertuples()]
    lines += ["", "## Protocol", ""] + [f"- {v}" for v in provenance["notes"]]
    lines += ["", "Scores are conditional on assumed source coverage. Source reporting gaps and timezone assumptions limit confidence; see the data-quality report.",
              "Test scores are reported honestly; the test winner does not replace the validation-selected method.",
              "Training/validation/test boundaries and all tuning trials are in training.json.",
              "The held-out demo model is never refitted on replayed future records."]
    (root / "docs/reports/model_evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    px.bar(metrics.melt(id_vars=["model"], value_vars=["MAE", "RMSE"]),
           x="model", y="value", color="variable", barmode="group",
           labels={"value": "Error (sessions/hour)"}).write_html(root / "reports/model_comparison.html", include_plotlyjs=True)
    first = predictions.loc[predictions.origin == demo_origin]
    actual = first[["timestamp", "actual"]].drop_duplicates().rename(columns={"actual": "value"})
    actual["series"] = "actual"
    curves = first[["timestamp", "model", "prediction"]].rename(columns={"model": "series", "prediction": "value"})
    px.line(pd.concat([actual, curves]), x="timestamp", y="value", color="series",
            labels={"value": "Arrivals (sessions/hour)", "timestamp": "Time (UTC)"}).write_html(
                root / "reports/actual_vs_predicted.html", include_plotlyjs=True)
    px.line(errors, x="local_hour", y="absolute_error", color="model",
            labels={"local_hour": f"Hour ({config['timezone']})", "absolute_error": "MAE (sessions/hour)"}).write_html(
                root / "reports/errors_by_hour.html", include_plotlyjs=True)
    return report
