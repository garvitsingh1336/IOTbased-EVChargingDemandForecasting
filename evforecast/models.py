"""Shared leakage-safe features, XGBoost, baselines and optional RF benchmark."""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

LOOKBACK = 168
MODEL_NAMES = ["same_hour_last_week", "hour_of_week_average", "xgboost", "random_forest"]
FEATURE_NAMES = ["local_hour", "local_weekday", "weekend", "hour_sin", "hour_cos",
                 "lag_1", "lag_24", "lag_168", "mean_24", "std_24", "mean_168", "std_168"]

def calendar(timestamp, timezone):
    local = timestamp.tz_convert(timezone)
    return [local.hour, local.dayofweek, int(local.dayofweek >= 5),
            np.sin(2*np.pi*local.hour/24), np.cos(2*np.pi*local.hour/24)]

def feature_row(timestamp, history, timezone):
    """history must end before timestamp. All rolling statistics are shifted."""
    past = history.loc[history.index < timestamp]
    window = past.reindex(pd.date_range(timestamp-pd.Timedelta(hours=LOOKBACK),
                                      periods=LOOKBACK, freq="h"))
    if window.isna().any():
        raise ValueError("Need 168 consecutive usable hours before forecast origin.")
    values = window.to_numpy(dtype=float)
    return calendar(timestamp, timezone) + [
        values[-1], values[-24], values[-168],
        values[-24:].mean(), values[-24:].std(), values.mean(), values.std()]

def training_matrix(history, timezone):
    rows, targets = [], []
    for timestamp, actual in history.iloc[LOOKBACK:].items():
        if pd.isna(actual):
            continue
        try:
            row = feature_row(timestamp, history, timezone)
        except ValueError:
            continue
        rows.append(row)
        targets.append(float(actual))
    if len(rows) < 168:
        raise ValueError("Insufficient usable training history after 168-hour lag warm-up.")
    return np.asarray(rows), np.asarray(targets)

def fit_bundle(history, config, leaf=10, xgb_params=None, include_rf=True):
    x, y = training_matrix(history, config["timezone"])
    forest = None
    if include_rf:
        forest = RandomForestRegressor(n_estimators=config["trees"], min_samples_leaf=leaf,
                                       max_features=1.0, random_state=config["random_seed"], n_jobs=1)
        forest.fit(x, y)
    booster = XGBRegressor(objective="reg:squarederror", tree_method="hist", n_jobs=1,
                           random_state=config["random_seed"], **(xgb_params or config["xgboost_grid"][0]))
    booster.fit(x, y)
    local = history.index.tz_convert(config["timezone"])
    keys = local.dayofweek * 24 + local.hour
    averages = history.groupby(keys).mean().dropna().to_dict()
    return {"forest": forest, "xgboost": booster, "hour_means": averages, "global_mean": float(history.mean()),
            "timezone": config["timezone"], "fit_end": history.index.max(),
            "min_samples_leaf": leaf, "training_rows": len(y)}

def forecast(bundle, history, origin, model, horizon=24):
    if model not in MODEL_NAMES:
        raise ValueError(f"Unknown model: {model}")
    origin = pd.Timestamp(origin)
    if origin.tzinfo is None:
        raise ValueError("Forecast origin must be timezone aware.")
    origin = origin.tz_convert("UTC")
    if pd.Timestamp(bundle["fit_end"]) >= origin:
        raise ValueError("Model was fitted on records at or after this forecast origin.")
    # Defensive cutoff: even if callers pass full data, future observations are inaccessible.
    past = history.loc[history.index < origin].copy()
    index = pd.date_range(origin, periods=horizon, freq="h")
    result = []
    for timestamp in index:
        local = timestamp.tz_convert(bundle["timezone"])
        key = local.dayofweek * 24 + local.hour
        average = bundle["hour_means"].get(key, bundle["global_mean"])
        if model == "hour_of_week_average":
            value = average
        elif model == "same_hour_last_week":
            # Same LOCAL wall-clock hour seven calendar days ago.
            naive = local.tz_localize(None) - pd.Timedelta(days=7)
            previous = naive.tz_localize(bundle["timezone"], ambiguous="NaT", nonexistent="NaT")
            value = past.get(previous.tz_convert("UTC"), np.nan) if not pd.isna(previous) else np.nan
            if pd.isna(value):
                value = average  # Explicit DST/missing-coverage fallback, learned on training only.
        else:
            estimator = bundle["xgboost"] if model == "xgboost" else bundle.get("forest")
            if estimator is None:
                raise ValueError("Random Forest benchmark was not fitted.")
            value = estimator.predict(np.asarray([feature_row(timestamp, past, bundle["timezone"])], dtype=float))[0]
        value = max(0.0, float(value))
        result.append(value)
        past.loc[timestamp] = value
    return pd.Series(result, index=index, name=model)
