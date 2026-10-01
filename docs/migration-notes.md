# Boulder migration and dashboard redesign

## Retained
Existing Python modules, XGBoost inference, recursive forecast-origin safeguards, chronological validation/test logic, baselines, REST API, idempotent storage, replay simulator, tests and optional Streamlit interface. The original ACN file, old native artifacts and pre-migration project copy remain preserved.

## Changed
Added an official Boulder downloader with stable edit-version, advertised-ID and SHA-256 checks. Added a source adapter for mixed timestamps, local timezone/DST handling, export duplicate removal, location selection and coverage reporting. The active dataset is Scott Carpenter Park, December 2022–November 2023. The official snapshot contains 148,136 records dated 2018-01-01 17:49:00 to 2023-11-30 23:27:00. The configured location is Scott Carpenter Park, 1505 30th St, Boulder, Colorado. The selected December 2022–November 2023 window contains 7,787 source rows. After removing 1,163 exact export duplicates, 6,624 sessions remain. Excluding both boundary days leaves 6,604 arrivals across 8,712 hours and 363 local days. The two station names are not a count of individual connectors.

Removed the former project-number branding from active code/configuration, documentation, API title, Grafana titles/UIDs, filenames and Compose project name. Immutable archived artifacts and backups retain historical provenance. Renamed smoke script to scripts/smoke_evforecast.py. Existing old Docker volumes were preserved; the new evforecast stack uses its own volumes.

Grafana now has a dark default theme, branded introduction, four summary cards, numbered sections, consistent blue actual/orange forecast colours, paired forecast comparisons, a weekday/hour colour matrix, performance panels, quality notes and separate replay activity. Its default range is historical and site timezone is America/Denver. Version-controlled generation is scripts/build_dashboard.py.

## Results
| Model | MAE | RMSE |
|---|---:|---:|
| xgboost | 0.5097 | 0.8764 |
| random_forest | 0.5112 | 0.8836 |
| same_hour_last_week | 0.5832 | 1.2360 |
| hour_of_week_average | 0.6874 | 0.9953 |

XGBoost won validation. Both validation and test use 30 origins of 24 elapsed hours each. Results are not directly comparable with earlier ACN scores. No current-day or Indian-campus accuracy is claimed.

## Verification and remaining limitations
50 tests passed with one non-failing pytest cache-permission warning. The full Boulder pipeline completed. Live PostgreSQL/REST smoke and 18 Grafana data-panel queries passed; Grafana reader write access was rejected. Browser automation had no available browser, so rendered visual inspection could not be completed. Concurrent-ingestion stress tests and a fresh dependency installation were not performed. Full logs and machine-readable results are in reports/ and runtime/.
