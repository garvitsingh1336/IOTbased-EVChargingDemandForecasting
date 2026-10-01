import numpy as np
import pandas as pd
import pytest
from evforecast.models import feature_row, forecast, MODEL_NAMES
from evforecast.evaluate import origins_for, metrics_for

class EchoLag:
    def predict(self, rows):
        return np.array([row[5] for row in rows])

def example():
    index = pd.date_range("2018-04-01", periods=240, freq="h", tz="UTC")
    series = pd.Series(np.arange(240, dtype=float), index=index)
    origin = index[200]
    bundle = {"xgboost": EchoLag(), "forest": EchoLag(), "hour_means": {}, "global_mean": 2,
              "timezone": "America/Los_Angeles", "fit_end": index[190]}
    return series, origin, bundle

def test_features_ignore_future_and_current_target():
    series, origin, _ = example()
    changed = series.copy()
    changed.loc[changed.index >= origin] = 999999
    assert feature_row(origin, series, "America/Los_Angeles") == feature_row(origin, changed, "America/Los_Angeles")
    assert feature_row(origin, series, "America/Los_Angeles")[5] == 199

@pytest.mark.parametrize("model", MODEL_NAMES)
def test_forecasts_invariant_to_future_targets(model):
    series, origin, bundle = example()
    changed = series.copy()
    changed.loc[changed.index >= origin] = 999999
    pd.testing.assert_series_equal(forecast(bundle, series, origin, model),
                                   forecast(bundle, changed, origin, model))

def test_recursion_uses_predictions_instead_of_actuals():
    series, origin, bundle = example()
    predictions = forecast(bundle, series, origin, "random_forest")
    assert predictions.eq(199).all()
    assert len(predictions) == 24

def test_model_fit_cutoff_guard_and_missing_history():
    series, origin, bundle = example()
    bundle["fit_end"] = origin
    with pytest.raises(ValueError, match="fitted"):
        forecast(bundle, series, origin, "random_forest")
    with pytest.raises(ValueError, match="168"):
        feature_row(origin, series.iloc[100:], "America/Los_Angeles")

def test_missing_targets_exclude_whole_origin():
    series, origin, _ = example()
    series.loc[origin + pd.Timedelta(hours=2)] = np.nan
    with pytest.raises(ValueError, match="No evaluable"):
        origins_for(series, origin, origin+pd.Timedelta(hours=24), "America/Los_Angeles")

def test_nonnegative_predictions():
    series, origin, bundle = example()
    bundle["global_mean"] = -2
    assert forecast(bundle, series, origin, "hour_of_week_average").eq(0).all()

def test_mae_and_rmse_are_unrounded():
    rows = pd.DataFrame({"model": ["a","a"], "origin": [1,1],
                         "actual": [0,2], "prediction": [0.5,1.5]})
    metrics = metrics_for(rows).iloc[0]
    assert metrics.MAE == 0.5 and metrics.RMSE == 0.5
