import json
import pandas as pd
import pytest
from evforecast.data import recover_json, clean_records, aggregate_hourly, parse_aware

CONFIG = {"site_id": "0002", "timezone": "America/Los_Angeles"}

def record(identifier="a", timestamp="2018-04-25T12:00:00Z"):
    return {"sessionID": identifier, "stationID": "charger", "siteID": "0002",
            "timezone": CONFIG["timezone"], "connectionTime": timestamp,
            "disconnectTime": "2018-04-25T13:00:00Z",
            "doneChargingTime": "2018-04-25T14:00:00Z", "kWhDelivered": 3}

def test_recover_trailing_comma_and_partial_object():
    text = '{"_meta": {"site":"caltech"}, "_items": [' + json.dumps(record()) + ', {"sessionID":'
    rows, report = recover_json(text)
    assert len(rows) == 1 and rows[0]["sessionID"] == "a"
    assert not report["valid_json"]
    assert report["unparsed_characters"] > 0

def test_recovery_respects_braces_in_strings_and_nested_data():
    obj = record()
    obj["userInputs"] = [{"text": 'brace } and escaped quote "'}]
    rows, _ = recover_json('{"_items":[' + json.dumps(obj) + ",")
    assert rows == [obj]

def test_valid_json_and_invalid_shape():
    assert recover_json(json.dumps({"_items": [record()]}))[1]["valid_json"]
    with pytest.raises(ValueError):
        recover_json('{"wrong": []}')

def test_duplicate_keep_first_optional_anomaly_preserved():
    second = record()
    second["stationID"] = "different"
    frame, report = clean_records([record(), second], CONFIG)
    assert len(frame) == 1 and frame.iloc[0].stationID == "charger"
    assert report["duplicate_session_ids"] == 1
    assert report["done_charging_outside_session"] == 1
    assert report["unusable_arrival_records"] == 0
    assert "userID" not in frame

def test_naive_timestamp_rejected():
    assert pd.isna(parse_aware("2018-04-25 12:00:00"))
    assert parse_aware("Wed, 25 Apr 2018 11:08:04 GMT").hour == 11

def sessions_at(values):
    return pd.DataFrame({"connectionTime": pd.to_datetime(values, utc=True)})

def test_hourly_counts_boundaries_and_known_gap():
    frame = sessions_at(["2018-04-25T12:00Z", "2018-04-26T08:05Z",
                         "2018-04-26T08:15Z", "2018-04-27T12:00Z"])
    result = aggregate_hourly(frame, CONFIG["timezone"],
                              [{"start": "2018-04-26T09:30Z", "end": "2018-04-26T10:00Z"}])
    assert len(result) == 24
    assert result.arrivals.sum() == 2
    assert (result.coverage_status == "known_missing").sum() == 1
    assert result.loc[result.coverage_status == "known_missing", "arrivals"].isna().all()
    assert (result.coverage_status == "assumed_zero").sum() == 22

@pytest.mark.parametrize("times,hours", [
    (["2018-03-10T12:00Z", "2018-03-12T12:00Z"], 23),
    (["2018-11-03T12:00Z", "2018-11-05T12:00Z"], 25),
])
def test_dst_days_have_correct_elapsed_hours(times, hours):
    result = aggregate_hourly(sessions_at(times), CONFIG["timezone"])
    assert len(result) == hours
    assert result.timestamp.is_unique
    assert result.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all()

def test_fall_back_repeated_hour_is_two_distinct_instants():
    frame = sessions_at(["2018-11-03T12:00Z", "2018-11-04T08:15Z",
                         "2018-11-04T09:15Z", "2018-11-05T12:00Z"])
    result = aggregate_hourly(frame, CONFIG["timezone"])
    populated = result[result.arrivals > 0]
    assert len(populated) == 2
    assert populated.timestamp_local.str.contains("T01:").all()
    assert populated.timestamp_local.nunique() == 2
