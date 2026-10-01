"""Download an auditable snapshot of the official City of Boulder session table."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]
URL = "https://services.arcgis.com/ePKBjXrBZ2vEEgWd/arcgis/rest/services/Electric_Vehicle_Charging_Station_Data/FeatureServer/0"

def main():
    destination = ROOT / "data/raw/boulder_sessions.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise SystemExit("Snapshot already exists; preserve it. Choose a new snapshot filename for an update.")
    with httpx.Client(timeout=90, follow_redirects=True) as client:
        def get(path, **params):
            for attempt in range(4):
                try:
                    response = client.get(URL + path, params={"f": "json", **params})
                    response.raise_for_status()
                    body = response.json()
                    if "error" in body:
                        raise ValueError(body["error"])
                    return body
                except (httpx.HTTPError, ValueError):
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
        metadata = get("")
        ids = sorted(get("/query", where="1=1", returnIdsOnly="true")["objectIds"])
        rows = []
        size = min(1000, metadata.get("maxRecordCount", 1000))
        for offset in range(0, len(ids), size):
            batch = ids[offset:offset+size]
            page = get("/query", where=f"{metadata['objectIdField']} >= {batch[0]} AND {metadata['objectIdField']} <= {batch[-1]}",
                       outFields="*", returnGeometry="false", orderByFields=metadata["objectIdField"], resultRecordCount=size)
            if page.get("exceededTransferLimit"):
                raise ValueError("Incomplete page; reduce batch size before retrying.")
            rows.extend(item["attributes"] for item in page["features"])
            print(f"Downloaded {len(rows):,}/{len(ids):,} records", flush=True)
        key = metadata["objectIdField"]
        if len(rows) != len(ids) or sorted(row[key] for row in rows) != ids:
            raise ValueError("Downloaded record IDs differ from the advertised snapshot.")
        after = get("")
        if after.get("editingInfo") != metadata.get("editingInfo"):
            raise ValueError("Source changed during download; retry a consistent snapshot.")
    rows.sort(key=lambda row: row[key])
    payload = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    destination.write_bytes(payload)
    report = {"source_url": URL, "retrieved_at": datetime.now(timezone.utc).isoformat(),
              "records": len(rows), "object_id_field": key,
              "source_editing_info": metadata.get("editingInfo"),
              "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
              "all_advertised_ids_downloaded": True,
              "coverage_note": "Complete advertised table snapshot; not proof of uninterrupted charger reporting.",
              "license": "CC0 per official item metadata"}
    (destination.parent / "boulder_download.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
