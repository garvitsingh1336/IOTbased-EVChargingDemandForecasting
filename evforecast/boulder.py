"""Official Boulder transaction adapter; local wall times, audited DST handling."""
import hashlib
import json
from pathlib import Path

import pandas as pd

from .config import write_json
from .data import aggregate_hourly

REQUIRED = ["ObjectId2", "Station_Name", "Address", "Start_Date___Time", "Start_Time_Zone"]

def wall_times(values):
    # The official export mixes US minute timestamps and ISO second timestamps.
    first = pd.to_datetime(values, format="%m/%d/%Y %H:%M", errors="coerce")
    return first.fillna(pd.to_datetime(values, format="%Y-%m-%d %H:%M:%S", errors="coerce"))

def local_timestamp(value, label, timezone="America/Denver"):
    """Use IANA local civil time. Labels resolve folds only, never shift winter clocks.

    Boulder has MDT labels in winter. Count those conflicts rather than blindly
    interpreting every MDT value as UTC-6. Nonexistent/undecidable instants are NaT.
    """
    try:
        naive = wall_times(pd.Series([value])).iloc[0]
        if pd.isna(naive):
            return pd.NaT, "invalid"
        first = naive.tz_localize(timezone, ambiguous=True, nonexistent="NaT")
        second = naive.tz_localize(timezone, ambiguous=False, nonexistent="NaT")
        if pd.isna(first):
            return pd.NaT, "nonexistent"
        label = str(label).strip().upper()
        if first != second:
            if label not in ("MDT", "MST"):
                return pd.NaT, "ambiguous"
            chosen = first if first.tzname() == label else second
            return chosen.tz_convert("UTC"), "fold_resolved_by_label"
        mismatch = label != first.tzname()
        return first.tz_convert("UTC"), "label_conflict" if mismatch else "ok"
    except (ValueError, TypeError, OverflowError):
        return pd.NaT, "invalid"

def adapt_records(records, config):
    if not isinstance(records, list) or not records:
        raise ValueError("Boulder source must be a nonempty JSON array of records.")
    for field in REQUIRED:
        if any(field not in row for row in records):
            raise ValueError(f"Boulder source missing required field: {field}")
    frame = pd.DataFrame(records)
    all_dates = wall_times(frame.Start_Date___Time)
    selected = frame.Address.astype(str).str.strip().eq(config["boulder_address"])
    if (selected & all_dates.isna()).any():
        raise ValueError("Selected site contains unparseable arrival dates; resolve source coverage before training.")
    begin, end = pd.Timestamp(config["period_start"]), pd.Timestamp(config["period_end_exclusive"])
    selected &= (all_dates >= begin) & (all_dates < end)
    frame = frame.loc[selected].copy()
    if frame.empty:
        raise ValueError("No Boulder sessions match the configured address and period.")
    duplicates = frame.ObjectId2.duplicated(keep="first")
    quality = {"source": "City of Boulder Open Data", "site_name": config["site_name"],
        "source_records": len(records), "input_records": len(frame),
        "source_first_connection_local": str(all_dates.min()), "source_last_connection_local": str(all_dates.max()),
        "selected_address": config["boulder_address"], "period_start": config["period_start"],
        "period_end_exclusive": config["period_end_exclusive"],
        "duplicate_session_ids": int(duplicates.sum()),
        "duplicate_rule": "Keep first ObjectId2; then keep first exact charging payload across all source fields except ObjectID/ObjectId2. Same-time records differing in any payload field are retained.",
        "missing_values": {field: int(frame[field].isna().sum()) for field in frame.columns},
        "coverage_status": "All advertised source IDs downloaded; feed uptime unverified"}
    frame = frame.loc[~duplicates].copy()
    payload_fields = [column for column in frame.columns if column not in ("ObjectID", "ObjectId2")]
    payload_duplicates = frame.duplicated(payload_fields, keep="first")
    quality["duplicate_export_payloads"] = int(payload_duplicates.sum())
    quality["duplicate_export_ids_removed"] = frame.loc[payload_duplicates, "ObjectId2"].tolist()
    frame = frame.loc[~payload_duplicates].copy()
    if frame.Station_Name.isna().any() or frame.Station_Name.astype(str).str.strip().eq("").any():
        raise ValueError("Selected site has missing station identifiers.")
    parsed = [local_timestamp(v, z, config["timezone"]) for v, z in zip(frame.Start_Date___Time, frame.Start_Time_Zone)]
    frame["connectionTime"] = pd.to_datetime([item[0] for item in parsed], utc=True)
    quality["arrival_timezone_checks"] = pd.Series([item[1] for item in parsed]).value_counts().to_dict()
    invalid = frame.connectionTime.isna()
    missing = list(config.get("known_missing_intervals", []))
    for value in frame.loc[invalid, "Start_Date___Time"]:
        day = wall_times(pd.Series([value])).iloc[0].normalize().tz_localize(config["timezone"])
        missing.append({"start": day.isoformat(), "end": (day + pd.DateOffset(days=1)).isoformat(),
                        "reason": "Unusable DST arrival; entire local day conservatively excluded"})
    quality["unusable_arrival_records"] = int(invalid.sum())
    frame = frame.loc[~invalid].copy()
    energy = pd.to_numeric(frame.get("Energy__kWh_"), errors="coerce")
    departure = [local_timestamp(v, z, config["timezone"])[0] for v, z in zip(frame.End_Date___Time, frame.End_Time_Zone)]
    duration = (pd.Series(pd.to_datetime(departure, utc=True), index=frame.index) - frame.connectionTime).dt.total_seconds()/3600
    quality["invalid_or_negative_energy"] = int((energy.isna() | (energy < 0)).sum())
    quality["invalid_or_missing_disconnectTime"] = int(pd.isna(departure).sum())
    quality["negative_duration"] = int((duration < 0).sum())
    quality["identical_station_start_end_energy_rows_review_only"] = int(frame.duplicated(
        ["Station_Name", "Start_Date___Time", "End_Date___Time", "Energy__kWh_"]).sum())
    quality["station_names"] = sorted(frame.Station_Name.unique().tolist())
    quality["charging_points"] = int(frame.Station_Name.nunique())
    quality["station_identifier_note"] = "Distinct source station names; individual connectors/ports are not identified. Not a physical port count."
    quality["invalid_or_missing_doneChargingTime"] = len(frame)
    quality["done_charging_outside_session"] = 0
    sessions = pd.DataFrame({"sessionID": "boulder-" + frame.ObjectId2.astype(str),
        "stationID": frame.Station_Name, "siteID": config["site_id"], "connectionTime": frame.connectionTime,
        "session_energy_kwh": energy.where(energy >= 0), "connection_duration_hours": duration.where(duration >= 0)})
    sessions = sessions.sort_values(["connectionTime", "sessionID"], kind="stable").reset_index(drop=True)
    quality["usable_arrivals"] = len(sessions)
    quality["first_connection_local"] = sessions.connectionTime.min().tz_convert(config["timezone"]).isoformat()
    quality["last_connection_local"] = sessions.connectionTime.max().tz_convert(config["timezone"]).isoformat()
    return sessions, quality, missing

def preprocess_boulder(config):
    root = config["root"]
    source = Path(config["source"])
    if not source.is_absolute():
        source = root / source
    if not source.exists():
        raise FileNotFoundError("Boulder snapshot missing. Run python scripts/download_boulder.py.")
    raw = source.read_bytes()
    records = json.loads(raw)
    download = json.loads((source.parent / "boulder_download.json").read_text())
    digest = hashlib.sha256(raw).hexdigest()
    if digest != download["sha256"] or len(records) != download["records"]:
        raise ValueError("Boulder snapshot differs from its download manifest.")
    sessions, quality, missing = adapt_records(records, config)
    hourly = aggregate_hourly(sessions, config["timezone"], missing)
    # Long silent periods are unknown coverage, not asserted zero demand.
    zero = hourly.arrivals.eq(0)
    groups = zero.ne(zero.shift()).cumsum()
    lengths = zero.groupby(groups).transform("sum")
    suspicious = zero & (lengths >= config.get("silence_unknown_hours", 168))
    hourly.loc[suspicious, "arrivals"] = float("nan")
    hourly.loc[suspicious, "coverage_status"] = "unknown_coverage"
    quality.update(hourly_start=hourly.timestamp.min().isoformat(), hourly_end=hourly.timestamp.max().isoformat(),
        hourly_rows=len(hourly), included_arrivals=int(hourly.arrivals.sum()),
        assumed_zero_hours=int(hourly.coverage_status.eq("assumed_zero").sum()),
        known_missing_hours=int(hourly.coverage_status.eq("known_missing").sum()),
        unknown_coverage_hours=int(suspicious.sum()),
        excluded_boundary_arrivals=int((~sessions.connectionTime.between(hourly.timestamp.min(),
            hourly.timestamp.max()+pd.Timedelta(hours=1), inclusive="left")).sum()),
        local_days=int(hourly.timestamp.dt.tz_convert(config["timezone"]).dt.date.nunique()),
        masked_intervals=missing)
    quality["warnings"] = [
        "Historical Boulder observations; not live sensors or a validated forecast for today.",
        "All advertised table IDs were downloaded; this does not establish uninterrupted source reporting.",
        "Zero-event hours are assumed zero; populated hours may also undercount missing transactions.",
        "Both boundary local days are excluded. Silent runs of at least 168 hours are masked as unknown coverage.",
        "Wall-clock strings are interpreted in America/Denver. Conflicting MST/MDT labels are reported; labels only disambiguate repeated fall-back hours. This is an explicit source-timezone assumption.",
        "Station names do not identify individual connectors. Optional duration/energy anomalies do not discard valid arrivals.",
        "US municipal charging behaviour does not establish accuracy at an Indian college."]
    write_json(root / "reports/recovery.json", {"valid_json": True, "recovery_needed": False,
        "recovered_records": len(records), "source": str(source), "source_sha256": digest,
        "status": "Complete advertised Boulder table snapshot; underlying coverage unverified", "download": download})
    write_json(root / "reports/data_quality.json", quality)
    sessions.to_csv(root / "data/sessions.csv", index=False)
    hourly.to_csv(root / "data/hourly.csv", index=False)
    lines = ["# Boulder data-quality report", "", "Original source snapshot preserved; no JSON recovery was needed.", ""]
    lines += [f"- **{key}**: {value}" for key, value in quality.items() if key not in ("warnings", "duplicate_export_ids_removed")]
    lines += ["", "Removed export IDs are recorded in reports/data_quality.json for auditing."]
    lines += ["", "## Limitations", ""] + [f"- {v}" for v in quality["warnings"]]
    (root / "docs/reports/data_quality.md").write_text("\n".join(lines), encoding="utf-8")
    return quality
