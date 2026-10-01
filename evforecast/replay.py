"""Arrival-only historical replay, isolated from training data and model updates."""
import json
import time
from pathlib import Path
import pandas as pd

LABEL = "Historical data replay — simulated IoT feed."

def arrival_events(sessions, start=None, end=None):
    events = []
    frame = sessions.copy()
    frame["connectionTime"] = pd.to_datetime(frame.connectionTime, utc=True)
    if start is not None:
        frame = frame.loc[frame.connectionTime >= pd.Timestamp(start)]
    if end is not None:
        frame = frame.loc[frame.connectionTime < pd.Timestamp(end)]
    frame = frame.sort_values(["connectionTime", "sessionID"], kind="stable")
    for row in frame.itertuples():
        events.append({"event_id": str(row.sessionID), "timestamp": row.connectionTime.isoformat(),
                       "site_id": str(row.siteID), "charger_id": str(row.stationID)})
    return events

class ReplayFeed:
    """One writer per file. Restart reconstructs seen IDs from the separate feed."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.seen = set()
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.seen.add(json.loads(line)["event_id"])

    def ingest(self, event):
        if set(event) != {"event_id", "timestamp", "site_id", "charger_id"}:
            raise ValueError("Arrival payload must not contain future session details.")
        if event["event_id"] in self.seen:
            return False
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")
        self.seen.add(event["event_id"])
        return True

    def reset(self):
        self.path.write_text("", encoding="utf-8")
        self.seen.clear()

def simulate(config, speed=3600, limit=None, reset=False):
    if speed <= 0:
        raise ValueError("Replay speed must be positive.")
    root = config["root"]
    meta = json.loads((root / "reports/evaluation.json").read_text())
    start = pd.Timestamp(meta["demo_origin"])
    end = start + pd.Timedelta(hours=24)
    sessions = pd.read_csv(root / "data/sessions.csv", dtype={"siteID": str, "stationID": str, "sessionID": str})
    events = arrival_events(sessions, start, end)
    if limit is not None:
        events = events[:limit]
    feed = ReplayFeed(root / "runtime/cli_arrivals.jsonl")
    if reset:
        feed.reset()
    print(LABEL)
    print(f"Origin: {start}; 1 real second = {speed} historical seconds. Ctrl+C pauses/stops; rerun resumes deduplicated ingestion.", flush=True)
    previous = None
    for event in events:
        if event["event_id"] in feed.seen:
            continue
        timestamp = pd.Timestamp(event["timestamp"])
        if previous is not None:
            time.sleep(max(0, (timestamp-previous).total_seconds()/speed))
        if feed.ingest(event):
            print(json.dumps(event), flush=True)
        previous = timestamp
    return len(feed.seen)
