"""Attempt the public web form, without accounts or embedded credentials.
Stores a separate download only if valid JSON arrives. Never overwrites the original.
"""
import hashlib
import http.cookiejar
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
class Fields(HTMLParser):
    token = None
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and values.get("name") == "csrf_token":
            self.token = values.get("value")

def main():
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "source": "https://ev.caltech.edu/dataset.html",
              "requested_site": "Caltech", "requested_start": "2018-05-01",
              "requested_end": "2018-11-01", "api": "Official API requires a registered token; none supplied."}
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        with opener.open(report["source"], timeout=25) as response:
            parser = Fields()
            parser.feed(response.read().decode())
        if not parser.token:
            raise ValueError("Public form did not provide a CSRF token.")
        fields = {"csrf_token": parser.token, "site": "Caltech", "start": "05/01/2018 12:00 AM",
                  "end": "11/01/2018 12:00 AM", "min_kWh": "", "submit": "Download"}
        request = urllib.request.Request(report["source"], data=urllib.parse.urlencode(fields).encode(),
                                         headers={"Referer": report["source"]})
        with opener.open(request, timeout=30) as response:
            raw = response.read(40_000_001)
            report["http_status"] = response.status
            report["content_type"] = response.headers.get("Content-Type")
        if len(raw) > 40_000_000:
            raise ValueError("Download exceeds the 40 MB non-timeseries safety limit.")
        obj = json.loads(raw)
        records = obj.get("_items") if isinstance(obj, dict) else obj
        if not isinstance(records, list) or not records:
            raise ValueError("Response did not contain nonempty session records.")
        path = ROOT / "data/official_six_month_download.json"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
        report.update(status="downloaded_separate_file", records=len(records), path=str(path),
                      sha256=hashlib.sha256(raw).hexdigest(),
                      note="Verify temporal coverage and completeness before selecting this source.")
    except Exception as error:
        report.update(status="public_web_download_unavailable", reason=f"{type(error).__name__}: {error}",
                      decision="Continue with recoverable local historical data; no synthetic substitution.")
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/official_access.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
