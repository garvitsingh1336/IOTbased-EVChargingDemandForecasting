# Boulder data-quality report

Original source snapshot preserved; no JSON recovery was needed.

- **source**: City of Boulder Open Data
- **site_name**: Boulder — Scott Carpenter Park
- **source_records**: 148136
- **input_records**: 7787
- **source_first_connection_local**: 2018-01-01 17:49:00
- **source_last_connection_local**: 2023-11-30 23:27:00
- **selected_address**: 1505 30th St
- **period_start**: 2022-12-01
- **period_end_exclusive**: 2023-12-01
- **duplicate_session_ids**: 0
- **duplicate_rule**: Keep first ObjectId2; then keep first exact charging payload across all source fields except ObjectID/ObjectId2. Same-time records differing in any payload field are retained.
- **missing_values**: {'Station_Name': 0, 'Address': 0, 'City': 0, 'State_Province': 0, 'Zip_Postal_Code': 0, 'Start_Date___Time': 0, 'Start_Time_Zone': 0, 'End_Date___Time': 0, 'End_Time_Zone': 0, 'Total_Duration__hh_mm_ss_': 0, 'Charging_Time__hh_mm_ss_': 0, 'Energy__kWh_': 0, 'GHG_Savings__kg_': 0, 'Gasoline_Savings__gallons_': 0, 'Port_Type': 0, 'ObjectID': 0, 'ObjectId2': 0}
- **coverage_status**: All advertised source IDs downloaded; feed uptime unverified
- **duplicate_export_payloads**: 1163
- **arrival_timezone_checks**: {'ok': 6624}
- **unusable_arrival_records**: 0
- **invalid_or_negative_energy**: 0
- **invalid_or_missing_disconnectTime**: 0
- **negative_duration**: 0
- **identical_station_start_end_energy_rows_review_only**: 12
- **station_names**: ['BOULDER / CARPENTER PARK1', 'BOULDER / CARPENTER PARK2']
- **charging_points**: 2
- **station_identifier_note**: Distinct source station names; individual connectors/ports are not identified. Not a physical port count.
- **invalid_or_missing_doneChargingTime**: 6624
- **done_charging_outside_session**: 0
- **usable_arrivals**: 6624
- **first_connection_local**: 2022-12-01T08:25:00-07:00
- **last_connection_local**: 2023-11-30T20:01:00-07:00
- **hourly_start**: 2022-12-02T07:00:00+00:00
- **hourly_end**: 2023-11-30T06:00:00+00:00
- **hourly_rows**: 8712
- **included_arrivals**: 6604
- **assumed_zero_hours**: 6206
- **known_missing_hours**: 0
- **unknown_coverage_hours**: 0
- **excluded_boundary_arrivals**: 20
- **local_days**: 363
- **masked_intervals**: []

Removed export IDs are recorded in reports/data_quality.json for auditing.

## Limitations

- Historical Boulder observations; not live sensors or a validated forecast for today.
- All advertised table IDs were downloaded; this does not establish uninterrupted source reporting.
- Zero-event hours are assumed zero; populated hours may also undercount missing transactions.
- Both boundary local days are excluded. Silent runs of at least 168 hours are masked as unknown coverage.
- Wall-clock strings are interpreted in America/Denver. Conflicting MST/MDT labels are reported; labels only disambiguate repeated fall-back hours. This is an explicit source-timezone assumption.
- Station names do not identify individual connectors. Optional duration/energy anomalies do not discard valid arrivals.
- US municipal charging behaviour does not establish accuracy at an Indian college.