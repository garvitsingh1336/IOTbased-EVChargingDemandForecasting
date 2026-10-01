import pandas as pd
import pytest
from evforecast.boulder import local_timestamp, adapt_records, wall_times
from evforecast.data import aggregate_hourly

CONFIG={"timezone":"America/Denver","site_id":"park","site_name":"Park","boulder_address":"1505 30th St",
        "period_start":"2023-01-01","period_end_exclusive":"2024-01-01"}

def record(identifier=1):
    return {"ObjectId2":identifier,"ObjectID":str(identifier),"Station_Name":"PARK1","Address":"1505 30th St",
        "Start_Date___Time":"1/2/2023 08:00","Start_Time_Zone":"MST",
        "End_Date___Time":"1/2/2023 09:00","End_Time_Zone":"MST","Energy__kWh_":"5"}

def test_both_official_date_formats():
    times=wall_times(pd.Series(["6/2/2023 05:52","2023-06-02 05:52:49"]))
    assert times.notna().all() and times.iloc[1].second==49

def test_denver_dst_fold_and_nonexistent_hour():
    a,_=local_timestamp("11/5/2023 01:30","MDT")
    b,_=local_timestamp("11/5/2023 01:30","MST")
    assert b-a==pd.Timedelta(hours=1)
    assert local_timestamp("11/5/2023 01:30","")[1]=="ambiguous"
    assert local_timestamp("3/12/2023 02:30","MDT")[1]=="nonexistent"

def test_mislabelled_winter_time_is_reported_not_shifted():
    stamp,flag=local_timestamp("1/2/2023 08:00","MDT")
    assert flag=="label_conflict" and stamp==pd.Timestamp("2023-01-02T15:00Z")

def test_exact_export_duplicate_removed_other_sessions_retained():
    rows=[record(),record(),record(2),{**record(3),"Energy__kWh_":"6"}]
    sessions,report,_=adapt_records(rows,CONFIG)
    assert len(sessions)==2
    assert report["duplicate_session_ids"]==1 and report["duplicate_export_payloads"]==1

def test_optional_departure_anomaly_keeps_arrival_and_site_filter():
    rows=[{**record(),"End_Date___Time":"bad"},{**record(2),"Address":"different"}]
    sessions,report,_=adapt_records(rows,CONFIG)
    assert len(sessions)==1 and sessions.connectionTime.notna().all()
    assert report["invalid_or_missing_disconnectTime"]==1

def test_unresolvable_dst_arrival_masks_day():
    rows=[record(),{**record(2),"Start_Date___Time":"3/12/2023 02:30","Start_Time_Zone":"MDT"},
          {**record(3),"Start_Date___Time":"3/14/2023 08:00","Start_Time_Zone":"MDT"}]
    sessions,report,missing=adapt_records(rows,CONFIG)
    hourly=aggregate_hourly(sessions,CONFIG["timezone"],missing)
    assert report["unusable_arrival_records"]==1
    assert hourly.coverage_status.eq("known_missing").sum()==23

def test_missing_required_fields_fail_helpfully():
    with pytest.raises(ValueError,match="required field"):
        adapt_records([{"Address":"1505 30th St"}],CONFIG)
