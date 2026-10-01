"""Live HTTP smoke test. Use --sqlite explicitly when PostgreSQL is unavailable."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evforecast.bootstrap import bootstrap
from evforecast.config import load_config
from evforecast.database import Store

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--sqlite",action="store_true",help="Explicit service-free test only; Grafana needs PostgreSQL")
    args=parser.parse_args()
    config=load_config()
    if args.sqlite:
        os.environ["DATABASE_URL"]="sqlite:///"+(ROOT/"runtime"/f"smoke-{uuid.uuid4().hex}.sqlite").as_posix()
    store=Store()
    imported=bootstrap(config,store)
    checks={"database_backend":store.engine.dialect.name,"bootstrap":imported}
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    url=f"http://127.0.0.1:{port}"
    out=(ROOT/"runtime/api-smoke.log").open("w",encoding="utf-8")
    server=subprocess.Popen([sys.executable,"-m","uvicorn","evforecast.api:app","--host","127.0.0.1","--port",str(port)],
                            cwd=ROOT,env=os.environ.copy(),stdout=out,stderr=out,
                            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    try:
        with httpx.Client(base_url=url,timeout=20) as client:
            for _ in range(40):
                try:
                    response=client.get("/health")
                    if response.status_code==200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("API did not become ready; inspect runtime/api-smoke.log")
            checks["live_health"]=response.json()
            replay_command=[sys.executable,"-m","evforecast","simulate","--api-url",url,"--run-id","smoke",
                            "--speed","100000000","--limit","3"]
            subprocess.run(replay_command+["--reset"],cwd=ROOT,check=True,capture_output=True,text=True)
            seen=client.get("/replay-runs/smoke/events").json()
            first=seen["events"][0]
            event={key:first[key] for key in ["event_id","timestamp","site_id","charger_id","generation"]}
            duplicate=client.post("/replay-runs/smoke/events",json=event)
            assert duplicate.json()["duplicate"]
            assert client.get("/replay-runs/smoke/events").json()["count"]==3
            subprocess.run(replay_command,cwd=ROOT,check=True,capture_output=True,text=True)
            assert client.get("/replay-runs/smoke/events").json()["count"]==3
            origin=json.loads((ROOT/"reports/evaluation.json").read_text())["demo_origin"]
            forecast=client.post("/forecasts",json={"origin":origin})
            assert forecast.status_code==201,forecast.text
            result=forecast.json()
            stored=client.get("/forecasts/"+result["forecast_id"]).json()
            assert len(stored["points"])==24
            assert stored["points"]==result["points"]
            assert stored["units"]=="sessions/hour" and stored["model_name"]=="xgboost"
            assert len(stored["actuals"])==24
            checks.update(ingested_unique_events=3,repeated_event_rejected=True,simulator_resume_deduplicates=True,
                          stored_forecast_hours=24,stored_forecast_id=stored["forecast_id"],
                          model_version=stored["model_version"],origin=stored["origin"],
                          training_cutoff=stored["training_cutoff"],actuals_per_run=24,
                          api_openapi_status=client.get("/openapi.json").status_code)
            digest=hashlib.sha256(Path(config["source"]).read_bytes()).hexdigest()
            assert digest==json.loads((ROOT/"reports/recovery.json").read_text())["source_sha256"]
            checks["original_source_unchanged"]=True
            checks["grafana"]="Not exercised by this script. Run scripts/verify_grafana.py against PostgreSQL + Grafana."
    finally:
        server.terminate()
        server.wait(timeout=15)
        out.close()
        store.engine.dispose()
    (ROOT/"reports/evforecast-smoke.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
    print(json.dumps(checks,indent=2))

if __name__=="__main__":
    main()
