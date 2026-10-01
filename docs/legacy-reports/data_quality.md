# Data-quality report

Original file preserved; recovered file is not a complete download.

- **input_records**: 4199
- **missing_fields**: {'sessionID': 0, 'stationID': 0, 'siteID': 0, 'connectionTime': 0, 'disconnectTime': 0, 'doneChargingTime': 0, 'kWhDelivered': 0, 'timezone': 0, 'userID': 0, 'userInputs': 0}
- **missing_values**: {'sessionID': 0, 'stationID': 0, 'siteID': 0, 'connectionTime': 0, 'disconnectTime': 0, 'doneChargingTime': 1, 'kWhDelivered': 0, 'timezone': 0, 'userID': 4174, 'userInputs': 4174}
- **duplicate_rule**: Keep the first occurrence of sessionID in original file order.
- **invalid_identifier_records**: 0
- **duplicate_session_ids**: 0
- **invalid_or_missing_connectionTime**: 0
- **invalid_or_missing_disconnectTime**: 0
- **invalid_or_missing_doneChargingTime**: 1
- **timezone_values**: ['America/Los_Angeles']
- **site_values**: ['0002']
- **unusable_arrival_records**: 0
- **invalid_or_negative_energy**: 0
- **energy_above_150_kwh_review_only**: 0
- **done_charging_outside_session**: 161
- **negative_duration**: 0
- **duration_above_48_hours_review_only**: 15
- **usable_arrivals**: 4199
- **charging_points**: 52
- **first_connection_local**: 2018-04-25T04:08:04-07:00
- **last_connection_local**: 2018-07-06T11:27:05-07:00
- **hourly_start**: 2018-04-26 07:00:00+00:00
- **hourly_end**: 2018-07-06 06:00:00+00:00
- **hourly_rows**: 1704
- **assumed_zero_hours**: 517
- **known_missing_hours**: 0
- **included_arrivals**: 4099
- **excluded_boundary_arrivals**: 100
- **local_days**: 71

## Limitations

- Recovery is not proof of complete source coverage; no feed-uptime logs are available.
- Zero-event hours are assumed zero, not confirmed working-feed observations.
- Observed-event hours can also be undercounted if records are missing.
- Both first and last local calendar days are excluded as boundary periods.
- Optional energy/departure anomalies do not invalidate otherwise valid arrival times.
- ACN warns about timezone errors in web downloads made before 10 October 2019. Download provenance is unknown; no speculative time correction is applied.
- US campus observations do not establish performance at an Indian campus.