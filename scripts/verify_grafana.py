"""Execute provisioned dashboard queries through live Grafana + PostgreSQL.
This requires docker compose up, bootstrap-db and Grafana admin credentials in .env.
It does not claim browser visual inspection.
"""
import json
import os
from pathlib import Path
import re
import sys
import httpx
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evforecast.artifacts import load_native
from evforecast.database import Store

def main():
    load_dotenv(ROOT/".env")
    store=Store()
    if store.engine.dialect.name!="postgresql":
        raise SystemExit("Grafana verification requires PostgreSQL, not the SQLite smoke-test backend.")
    metadata=load_native(ROOT)["metadata"]
    runs=store.list_forecasts(metadata["dataset_id"])
    if not runs:
        raise SystemExit("Run bootstrap-db first.")
    selected=next(r for r in runs if r["model_version"]==metadata["model_version"])
    reader_url=URL.create("postgresql+psycopg",username="grafana_reader",
        password=os.environ["GRAFANA_READER_PASSWORD"],host=os.getenv("POSTGRES_HOST","127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT","5432")),database="evforecast")
    reader=create_engine(reader_url)
    with reader.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM hourly_demand"))>0
        connection.rollback()
        transaction=connection.begin()
        rejected=False
        try:
            connection.execute(text("INSERT INTO replay_runs (run_id,generation,label,created_at) VALUES (:id,1,:label,CURRENT_TIMESTAMP)"),
                               {"id":"reader-permission-probe","label":"Must be denied"})
        except DBAPIError as error:
            rejected=getattr(error.orig,"sqlstate",None) in ("42501","25006")
        finally:
            transaction.rollback()
        assert rejected,"Grafana reader unexpectedly has write access."
    reader.dispose()
    url="http://127.0.0.1:"+os.getenv("GRAFANA_PORT","3000")
    auth=(os.getenv("GRAFANA_ADMIN_USER","admin"),os.environ["GRAFANA_ADMIN_PASSWORD"])
    report={"grafana_url":url,"read_only_role_verified":True,"panels":[],"visual_browser_check":False}
    with httpx.Client(base_url=url,auth=auth,timeout=30) as client:
        response=client.get("/api/dashboards/uid/evforecast-demand")
        response.raise_for_status()
        dashboard=response.json()["dashboard"]
        health=client.get("/api/datasources/uid/evforecast-postgres/health")
        health.raise_for_status()
        assert health.json().get("status")=="OK",health.text
        report["datasource_health"]=health.json().get("status")
        replacements={"dataset":metadata["dataset_id"],"forecast":selected["forecast_id"],"replay":"demo"}
        begin,end=dashboard["time"]["from"],dashboard["time"]["to"]
        for panel in dashboard["panels"]:
            if not panel.get("targets"):
                continue
            sql=panel["targets"][0]["rawSql"]
            for key,value in replacements.items():
                sql=sql.replace("${"+key+":sqlstring}", "'"+value.replace("'","''")+"'")
            sql=re.sub(r"\$__timeFilter\(([^)]+)\)", lambda m: f"{m[1]} >= '{begin}' AND {m[1]} < '{end}'", sql)
            target={**panel["targets"][0],"rawSql":sql,"intervalMs":3600000,"maxDataPoints":10000}
            response=client.post("/api/ds/query",json={"from":str(pd.Timestamp(begin).value//10**6),"to":str(pd.Timestamp(end).value//10**6),"queries":[target]})
            response.raise_for_status()
            results=response.json()["results"]
            assert "A" in results and not results["A"].get("error"),response.text
            frames=results["A"].get("frames",[])
            rows=sum(len((frame.get("data",{}).get("values") or [[]])[0]) for frame in frames)
            if any(panel["title"].startswith(prefix) for prefix in (
                "Dataset coverage","Historical hourly","Next 24","Actual vs","Validation/test")):
                assert rows>0,f"No rows for {panel['title']}"
            report["panels"].append({"title":panel["title"],"query_ok":True,"rows":rows})
    (ROOT/"reports/grafana-verification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
