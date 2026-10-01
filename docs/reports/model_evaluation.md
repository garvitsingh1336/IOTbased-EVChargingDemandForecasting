# Model evaluation

Target: site-wide session arrivals (sessions/hour).

Primary specification ML model: **XGBoost**. Validation winner across all methods: **xgboost**.
Test: 2023-10-31 06:00:00+00:00 through 2023-11-30 07:00:00+00:00 (exclusive). 30 origins, 720 unique forecast hours, 30 local dates.

| Model | MAE | RMSE | Origins |
|---|---:|---:|---:|
| xgboost | 0.5097 | 0.8764 | 30 |
| random_forest | 0.5112 | 0.8836 | 30 |
| same_hour_last_week | 0.5832 | 1.2360 | 30 |
| hour_of_week_average | 0.6874 | 0.9953 | 30 |

## Protocol

- XGBoost, RF benchmark and hour-of-week means remain frozen during each evaluation period.
- Observed arrivals before each later origin may be used as lag inputs, never observations at or after that origin.
- Origins are 24 elapsed hours apart, starting at local midnight of each split.
- Fractional nonnegative predictions are expected counts; metrics use unrounded values.
- No calibrated prediction intervals are claimed.

Scores are conditional on assumed source coverage. Source reporting gaps and timezone assumptions limit confidence; see the data-quality report.
Test scores are reported honestly; the test winner does not replace the validation-selected method.
Training/validation/test boundaries and all tuning trials are in training.json.
The held-out demo model is never refitted on replayed future records.