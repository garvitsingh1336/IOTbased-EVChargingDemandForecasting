"""Legacy Streamlit/file-replay verification; use smoke_evforecast.py for the primary stack."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def main():
    os.chdir(ROOT)
    config = json.loads((ROOT / "config.json").read_text())
    recovery = json.loads((ROOT / "reports/recovery.json").read_text())
    digest = hashlib.sha256(Path(config["source"]).read_bytes()).hexdigest()
    assert digest == recovery["source_sha256"], "Original dataset changed."
    checks = {"original_sha256_unchanged": True}
    # All compared models must be scored on identical origin/timestamp pairs.
    predictions = pd.read_csv(ROOT / "reports/test_predictions.csv")
    keys = [set(zip(g.origin, g.timestamp)) for _, g in predictions.groupby("model")]
    assert all(k == keys[0] for k in keys)
    assert (predictions.prediction >= 0).all()
    checks["identical_model_test_timestamps"] = True
    checks["test_hours_per_model"] = len(keys[0])
    checks["nonnegative_predictions"] = True
    tested = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    (ROOT / "reports/pytest_output.txt").write_text(tested.stdout + tested.stderr, encoding="utf-8")
    checks["pytest_exit_code"] = tested.returncode
    if tested.returncode:
        print(tested.stdout, tested.stderr)
        raise RuntimeError("Tests failed.")
    print(tested.stdout.strip())
    # Exercise the real CLI simulator and confirm repeat ingestion adds no duplicates.
    command = [sys.executable, "-m", "evforecast", "simulate-legacy", "--speed", "100000000", "--limit", "10"]
    first = subprocess.run(command + ["--reset"], cwd=ROOT, capture_output=True, text=True, check=True)
    before = (ROOT / "runtime/cli_arrivals.jsonl").read_bytes()
    subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    after = (ROOT / "runtime/cli_arrivals.jsonl").read_bytes()
    assert before == after
    records = [json.loads(line) for line in after.splitlines()]
    assert len(records) == 10 and len({r["event_id"] for r in records}) == 10
    assert all(set(r) == {"event_id","timestamp","site_id","charger_id"} for r in records)
    checks["cli_replay_unique_events"] = 10
    checks["cli_replay_restart_deduplicates"] = True
    (ROOT / "reports/simulator_smoke.txt").write_text(first.stdout, encoding="utf-8")
    # Start a new owned process on an available port; never stop somebody else's process.
    import socket
    port = None
    for candidate in (8501, 8502, 8503):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", candidate))
                port = candidate
                break
            except OSError:
                continue
    if port is None:
        raise RuntimeError("Ports 8501â€“8503 occupied; dashboard startup not checked.")
    stdout = (ROOT / "runtime/streamlit.stdout.log").open("w", encoding="utf-8")
    stderr = (ROOT / "runtime/streamlit.stderr.log").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
         "--server.address", "127.0.0.1", "--server.port", str(port), "--browser.gatherUsageStats", "false"],
        cwd=ROOT, stdout=stdout, stderr=stderr,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    url = f"http://127.0.0.1:{port}"
    healthy = False
    for _ in range(30):
        if server.poll() is not None:
            break
        try:
            with urllib.request.urlopen(url + "/_stcore/health", timeout=1) as response:
                healthy = response.status == 200 and response.read() == b"ok"
            if healthy:
                break
        except Exception:
            time.sleep(0.5)
    if not healthy:
        server.terminate()
        raise RuntimeError("Streamlit failed health check; inspect runtime logs.")
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.status == 200
    checks.update(streamlit_health="HTTP 200: ok", streamlit_home="HTTP 200", dashboard_url=url,
                  dashboard_pid=server.pid,
                  note="Streamlit AppTest verifies rendering and controls; live HTTP verifies server startup. No visual browser inspection performed.")
    (ROOT / "runtime/server.json").write_text(json.dumps({"pid": server.pid, "url": url}), encoding="utf-8")
    (ROOT / "reports/verification.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    lines = ["# Executed verification", "", f"Python: {sys.version.split()[0]}", ""]
    lines += [f"- {k}: {v}" for k, v in checks.items()]
    lines += ["", "## Test runner", "", "```text", tested.stdout.strip(), "```",
              "", "Full pipeline preprocessing/training/evaluation completed on the real local source.",
              "Official six-month download was attempted but returned truncated JSON; see official_access.json.",
              "Dependency installation into a fresh virtual environment and a visual browser check were not performed.",
              "Tests use small constructed fixtures solely for correctness; no synthetic data trains the project models."]
    (ROOT / "docs/reports/legacy-verification.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(checks, indent=2))

if __name__ == "__main__":
    main()
