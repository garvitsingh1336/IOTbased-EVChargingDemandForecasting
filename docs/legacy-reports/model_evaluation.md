# Model evaluation

Target: site-wide session arrivals (sessions/hour).

Selected using validation only: **hour_of_week_average**.
Test: 2018-06-22 07:00:00+00:00 through 2018-07-06 07:00:00+00:00 (exclusive). 14 origins, 336 unique forecast hours, 14 local dates.

| Model | MAE | RMSE | Origins |
|---|---:|---:|---:|
| random_forest | 1.3076 | 1.9563 | 14 |
| hour_of_week_average | 1.3162 | 2.0347 | 14 |
| same_hour_last_week | 1.5238 | 2.3705 | 14 |

## Protocol

- RF and hour-of-week means remain frozen during each evaluation period.
- Observed arrivals before each later origin may be used as lag inputs, never observations at or after that origin.
- Origins are 24 elapsed hours apart, starting at local midnight of each split.
- Fractional nonnegative predictions are expected counts; metrics use unrounded values.
- No calibrated prediction intervals are claimed.

Scores are conditional on assumed source coverage. The short, incomplete export limits confidence.
Test scores are reported honestly; the test winner does not replace the validation-selected method.
Training/validation/test boundaries and all tuning trials are in training.json.
The held-out demo model is never refitted on replayed future records.