"""Historical arrival replay over REST; retries are safe through server idempotency."""
import json
import time
import httpx
import pandas as pd
from .replay import LABEL, arrival_events

def request_with_retry(client, method, path, *, attempts=4, **kwargs):
    for attempt in range(attempts):
        try:
            response = client.request(method, path, **kwargs)
            if response.status_code >= 500:
                response.raise_for_status()
            response.raise_for_status()  # 4xx are never retried.
            return response.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            retryable = isinstance(error, httpx.TransportError) or error.response.status_code >= 500
            if not retryable or attempt == attempts - 1:
                raise
            time.sleep(0.25 * 2**attempt)

def simulate_http(config, api_url="http://127.0.0.1:8000", run_id="demo", speed=3600, limit=None, reset=False):
    if speed <= 0 or (limit is not None and limit < 1):
        raise ValueError("Speed must be positive; limit must be at least 1.")
    root = config["root"]
    report = json.loads((root / "reports/evaluation.json").read_text())
    start = pd.Timestamp(report["demo_origin"])
    sessions = pd.read_csv(root / "data/sessions.csv", dtype={"siteID": str, "stationID": str, "sessionID": str})
    events = arrival_events(sessions, start, start + pd.Timedelta(hours=24))
    if limit is not None:
        events = events[:limit]
    print(LABEL, flush=True)
    print(f"REST: {api_url}; run: {run_id}; origin: {start}; speed: {speed} historical seconds / real second.", flush=True)
    with httpx.Client(base_url=api_url.rstrip("/"), timeout=15) as client:
        run = request_with_retry(client, "POST", f"/replay-runs/{run_id}")
        if reset:
            # Reset is deliberately not retried automatically; only this selected run is affected.
            run = request_with_retry(client, "POST", f"/replay-runs/{run_id}/reset", attempts=1)
        received = request_with_retry(client, "GET", f"/replay-runs/{run_id}/events")
        seen = {event["event_id"] for event in received["events"]}
        previous = None
        for event in events:
            if event["event_id"] in seen:
                continue
            timestamp = pd.Timestamp(event["timestamp"])
            if previous is not None:
                time.sleep(max(0, (timestamp-previous).total_seconds()/speed))
            result = request_with_retry(client, "POST", f"/replay-runs/{run_id}/events",
                                        json={**event, "generation": run["generation"]})
            print(json.dumps(result), flush=True)
            previous = timestamp
    print("Replay complete. Ctrl+C pauses during replay; rerun resumes the same run.", flush=True)
