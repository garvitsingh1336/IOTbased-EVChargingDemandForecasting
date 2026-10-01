import pandas as pd
import pytest
from evforecast.replay import ReplayFeed, arrival_events

def test_arrival_payload_order_and_dedup_across_restart(tmp_path):
    frame = pd.DataFrame([
        {"sessionID":"b","connectionTime":"2018-04-26T09:00Z","siteID":"0002","stationID":"c","kWhDelivered":9},
        {"sessionID":"a","connectionTime":"2018-04-26T08:00Z","siteID":"0002","stationID":"c","kWhDelivered":3}])
    events = arrival_events(frame)
    assert [e["event_id"] for e in events] == ["a", "b"]
    assert set(events[0]) == {"event_id","timestamp","site_id","charger_id"}
    feed = ReplayFeed(tmp_path / "events.jsonl")
    assert feed.ingest(events[0])
    assert not ReplayFeed(feed.path).ingest(events[0])
    with pytest.raises(ValueError):
        feed.ingest({**events[1], "energy": 4})
    feed.reset()
    assert not feed.path.read_text()
    assert feed.ingest(events[0])
