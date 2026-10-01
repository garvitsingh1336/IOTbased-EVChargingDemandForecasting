# Project report: IoT-Based EV Charging Demand Forecasting

## Problem
Estimate next-day hourly session arrivals at one site to help operators identify periods needing further capacity study. Arrival counts alone cannot determine power demand or queues.

## Dataset
The official snapshot contains 148,136 records dated 2018-01-01 17:49:00 to 2023-11-30 23:27:00. The configured location is Scott Carpenter Park, 1505 30th St, Boulder, Colorado. The selected December 2022–November 2023 window contains 7,787 source rows. After removing 1,163 exact export duplicates, 6,624 sessions remain. Excluding both boundary days leaves 6,604 arrivals across 8,712 hours and 363 local days. The two station names are not a count of individual connectors.
Downloaded from [the official City of Boulder source](https://open-data.bouldercolorado.gov/datasets/95992b3938be4622b07f0b05eba95d4c_0/explore); source bytes and ID completeness are recorded in data/raw/boulder_download.json. The 2018 ACN dataset is preserved as an archive and does not train the current model.

## Methodology
The site was selected by pre-validation activity. Normalize source fields, remove ID/exact-payload duplicates, convert local timestamps to UTC, exclude boundary days and aggregate arrivals hourly. Missing-feed coverage is not known; zeros are assumptions. Optional completion/energy anomalies do not invalidate arrival times. No identities or final-session attributes enter the model.

Chronological training begins 2022-12-02T07:00:00+00:00; validation begins 2023-10-01T06:00:00+00:00; test begins 2023-10-31T06:00:00+00:00 and ends 2023-11-30T07:00:00+00:00 exclusive. Three modest XGBoost settings were compared on validation only. Refit on training+validation, then freeze. Each of 30 test origins predicts a complete next 24 hours recursively; later lag updates use predictions. All methods share target timestamps.

## Results
| Model | MAE | RMSE |
|---|---:|---:|
| xgboost | 0.5097 | 0.8764 |
| random_forest | 0.5112 | 0.8836 |
| same_hour_last_week | 0.5832 | 1.2360 |
| hour_of_week_average | 0.6874 | 0.9953 |

XGBoost won validation and had the lowest measured test MAE. Fractional outputs are expected counts. No accuracy percentage or calibrated prediction interval is claimed. The test contains 720 hours; DST leaves the final available hour outside the last full 24-hour forecast rather than inventing an extra partial forecast.

## Implemented system
Historical preprocessing/training → saved XGBoost. Replay → FastAPI → PostgreSQL. Forecast service → immutable saved runs → Grafana. The dashboard has summary cards, forecast comparison, hourly history, weekday/hour patterns, baseline metrics, provenance and replay events. Grafana reads through a restricted database account.

## Limitations and future scope
The latest raw date is November 2023. Export duplicates, assumed feed availability, ambiguous source identifiers and local-time assumptions limit confidence. A municipal US site differs from an Indian college. Deployment requires new local data, availability monitoring, ingestion watermarks, security and independent evaluation. Weather is a possible extension only when its values are available at prediction time. No hardware or live sensing is claimed.
