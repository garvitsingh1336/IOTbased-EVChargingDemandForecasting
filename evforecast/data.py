"""Recover complete JSON records; preserve UTC instants and local calendar dates."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import write_json

FIELDS = ["sessionID", "stationID", "siteID", "connectionTime", "disconnectTime",
          "doneChargingTime", "kWhDelivered", "timezone", "userID", "userInputs"]

def recover_json(text):
    """Decode only consecutive, fully formed top-level session objects.
    Never search arbitrary braces or skip malformed interior material.
    """
    decoder = json.JSONDecoder()
    try:
        obj = json.loads(text)
        records = obj if isinstance(obj, list) else obj.get("_items") if isinstance(obj, dict) else None
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            raise ValueError("Expected a JSON array or an object containing an _items array of objects.")
        return records, {"valid_json": True, "recovered_records": len(records),
                         "stopped_at_character": len(text), "unparsed_characters": 0}
    except json.JSONDecodeError as error:
        json_error = str(error)
    pos = 0
    def whitespace(i):
        while i < len(text) and text[i].isspace():
            i += 1
        return i
    pos = whitespace(pos)
    if text[pos:pos+1] == "{":
        pos = whitespace(pos + 1)
        while True:
            key, end = decoder.raw_decode(text, pos)
            pos = whitespace(end)
            if text[pos:pos+1] != ":":
                raise ValueError("Unrecoverable envelope: expected a colon.")
            pos = whitespace(pos + 1)
            if key == "_items":
                break
            _, pos = decoder.raw_decode(text, pos)
            pos = whitespace(pos)
            if text[pos:pos+1] != ",":
                raise ValueError("Unrecoverable envelope: no _items array.")
            pos = whitespace(pos + 1)
    if text[pos:pos+1] != "[":
        raise ValueError("Recovery supports a top-level array or an _items array only.")
    pos = whitespace(pos + 1)
    records = []
    while pos < len(text) and text[pos] != "]":
        try:
            record, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            break
        if not isinstance(record, dict):
            raise ValueError("Session array contains a non-object.")
        records.append(record)
        pos = whitespace(end)
        if text[pos:pos+1] != ",":
            break
        pos = whitespace(pos + 1)
    if not records:
        raise ValueError("No complete records could be recovered.")
    return records, {"valid_json": False, "json_error": json_error,
                     "recovered_records": len(records), "stopped_at_character": pos,
                     "unparsed_characters": len(text) - pos,
                     "status": "Recovered prefix only; NOT a complete download."}

def parse_aware(value):
    if value is None or value == "":
        return pd.NaT
    try:
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None:
            return pd.NaT
        return stamp.tz_convert("UTC")
    except (ValueError, TypeError, OverflowError):
        return pd.NaT

def clean_records(records, config):
    frame = pd.DataFrame(records)
    report = {
        "input_records": len(frame),
        "missing_fields": {f: sum(f not in r for r in records) for f in FIELDS},
        "missing_values": {f: int(frame[f].isna().sum()) if f in frame else len(frame) for f in FIELDS},
        "duplicate_rule": "Keep the first occurrence of sessionID in original file order.",
    }
    for field in FIELDS:
        if field not in frame:
            frame[field] = None
    identifiers = ["sessionID", "stationID", "siteID", "timezone"]
    bad_id = pd.Series(False, index=frame.index)
    for field in identifiers:
        bad_id |= frame[field].map(lambda v: not isinstance(v, str) or not v.strip())
    report["invalid_identifier_records"] = int(bad_id.sum())
    duplicate = frame["sessionID"].notna() & frame["sessionID"].duplicated(keep="first")
    report["duplicate_session_ids"] = int(duplicate.sum())
    frame = frame.loc[~duplicate].copy()
    bad_id = bad_id.loc[frame.index]
    for name in ["connectionTime", "disconnectTime", "doneChargingTime"]:
        frame[name] = pd.to_datetime(frame[name].map(parse_aware), utc=True)
        report["invalid_or_missing_" + name] = int(frame[name].isna().sum())
    report["timezone_values"] = sorted(str(v) for v in frame["timezone"].dropna().unique())
    report["site_values"] = sorted(str(v) for v in frame["siteID"].dropna().unique())
    wrong_site = frame["siteID"] != config["site_id"]
    wrong_tz = frame["timezone"] != config["timezone"]
    invalid = bad_id | frame["connectionTime"].isna() | wrong_site | wrong_tz
    report["unusable_arrival_records"] = int(invalid.sum())
    energy = pd.to_numeric(frame["kWhDelivered"], errors="coerce")
    report["invalid_or_negative_energy"] = int((~np.isfinite(energy) | (energy < 0)).sum())
    report["energy_above_150_kwh_review_only"] = int((energy > 150).sum())
    outside = frame["doneChargingTime"].notna() & (
        (frame["doneChargingTime"] < frame["connectionTime"]) |
        (frame["doneChargingTime"] > frame["disconnectTime"]))
    report["done_charging_outside_session"] = int(outside.sum())
    duration = (frame["disconnectTime"] - frame["connectionTime"]).dt.total_seconds() / 3600
    report["negative_duration"] = int((duration < 0).sum())
    report["duration_above_48_hours_review_only"] = int((duration > 48).sum())
    frame["session_energy_kwh"] = energy.where(np.isfinite(energy) & (energy >= 0))
    frame["connection_duration_hours"] = duration.where(duration >= 0)
    frame = frame.loc[~invalid].sort_values(["connectionTime", "sessionID"], kind="stable")
    if frame.empty:
        raise ValueError("No usable arrivals found.")
    report["usable_arrivals"] = len(frame)
    report["charging_points"] = int(frame["stationID"].nunique())
    report["first_connection_local"] = frame["connectionTime"].min().tz_convert(config["timezone"]).isoformat()
    report["last_connection_local"] = frame["connectionTime"].max().tz_convert(config["timezone"]).isoformat()
    # Drop identities and any user inputs from downstream datasets.
    return frame[["sessionID", "stationID", "siteID", "connectionTime",
                  "session_energy_kwh", "connection_duration_hours"]], report

def aggregate_hourly(sessions, timezone, missing_intervals=()):
    """UTC hourly index avoids DST duplicates. Exclude both boundary local days."""
    local = sessions["connectionTime"].dt.tz_convert(timezone)
    start = (local.min().normalize() + pd.DateOffset(days=1)).tz_convert("UTC")
    stop = local.max().normalize().tz_convert("UTC")
    if stop <= start:
        raise ValueError("Insufficient coverage: need at least one interior local day.")
    index = pd.date_range(start, stop, freq="h", inclusive="left")
    counts = sessions.set_index("connectionTime").resample("h").size().reindex(index, fill_value=0)
    result = pd.DataFrame({"timestamp": index, "arrivals": counts.to_numpy(dtype=float)})
    result["coverage_status"] = np.where(result["arrivals"] == 0, "assumed_zero", "observed_events")
    for interval in missing_intervals:
        begin, end = (parse_aware(interval[k]) for k in ("start", "end"))
        if pd.isna(begin) or pd.isna(end) or begin >= end:
            raise ValueError("Known missing intervals need aware start < end.")
        mask = (result.timestamp < end) & (result.timestamp + pd.Timedelta(hours=1) > begin)
        result.loc[mask, "arrivals"] = np.nan
        result.loc[mask, "coverage_status"] = "known_missing"
    result["timestamp_local"] = result.timestamp.dt.tz_convert(timezone).map(lambda t: t.isoformat())
    return result

def preprocess(config):
    if config.get("dataset_type") == "boulder":
        from .boulder import preprocess_boulder
        return preprocess_boulder(config)
    source = Path(config["source"])
    if not source.is_file():
        raise FileNotFoundError(f"Dataset missing: {source}. Set source in config.json.")
    raw = source.read_bytes()
    records, recovery = recover_json(raw.decode("utf-8-sig"))
    recovery.update(source=str(source), source_bytes=len(raw),
                    source_sha256=hashlib.sha256(raw).hexdigest())
    root = config["root"]
    write_json(root / "data/recovered_sessions.json",
               {"_meta": {"recovery": recovery, "complete_download": False}, "_items": records})
    write_json(root / "reports/recovery.json", recovery)
    sessions, quality = clean_records(records, config)
    quality["warnings"] = [
        "Recovery is not proof of complete source coverage; no feed-uptime logs are available.",
        "Zero-event hours are assumed zero, not confirmed working-feed observations.",
        "Observed-event hours can also be undercounted if records are missing.",
        "Both first and last local calendar days are excluded as boundary periods.",
        "Optional energy/departure anomalies do not invalidate otherwise valid arrival times.",
        "ACN warns about timezone errors in web downloads made before 10 October 2019. Download provenance is unknown; no speculative time correction is applied.",
        "US campus observations do not establish performance at an Indian campus.",
    ]
    write_json(root / "reports/data_quality.json", quality)
    if quality["unusable_arrival_records"]:
        raise ValueError("Unusable arrival records found. Quality report saved. Resolve their coverage before aggregation; do not silently zero-fill.")
    hourly = aggregate_hourly(sessions, config["timezone"], config["known_missing_intervals"])
    quality.update(hourly_start=str(hourly.timestamp.min()), hourly_end=str(hourly.timestamp.max()),
                   hourly_rows=len(hourly), assumed_zero_hours=int((hourly.coverage_status == "assumed_zero").sum()),
                   known_missing_hours=int((hourly.coverage_status == "known_missing").sum()),
                   included_arrivals=int(hourly.arrivals.sum()),
                   excluded_boundary_arrivals=int(len(sessions) - sessions.connectionTime.between(
                       hourly.timestamp.min(), hourly.timestamp.max() + pd.Timedelta(hours=1), inclusive="left").sum()),
                   local_days=int(hourly.timestamp.dt.tz_convert(config["timezone"]).dt.date.nunique()))
    sessions.to_csv(root / "data/sessions.csv", index=False)
    hourly.to_csv(root / "data/hourly.csv", index=False)
    write_json(root / "reports/data_quality.json", quality)
    lines = ["# Data-quality report", "", "Original file preserved; recovered file is not a complete download.", ""]
    lines += [f"- **{key}**: {value}" for key, value in quality.items() if key != "warnings"]
    lines += ["", "## Limitations", ""] + [f"- {v}" for v in quality["warnings"]]
    (root / "docs/reports/data_quality.md").write_text("\n".join(lines), encoding="utf-8")
    return quality

def load_hourly(root):
    path = root / "data/hourly.csv"
    if not path.exists():
        raise FileNotFoundError("Run python -m evforecast preprocess first.")
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.set_index("timestamp")["arrivals"].asfreq("h")
