"""Generate the provisioned Grafana dashboard from current dataset/model metadata."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DS = {"type": "postgres", "uid": "evforecast-postgres"}
BLUE, ORANGE, TEAL = "#5794F2", "#FF9830", "#73BF69"

def main():
    config = json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
    quality = json.loads((ROOT/"reports/data_quality.json").read_text())
    evaluation = json.loads((ROOT/"reports/evaluation.json").read_text())
    tz = config["timezone"]
    panels = []
    def panel(title, kind, x, y, w, h, sql=None, color=BLUE, description="", **options):
        item = {"id": len(panels)+1, "title": title, "type": kind,
            "description": description, "gridPos": {"x":x,"y":y,"w":w,"h":h},
            "fieldConfig": {"defaults": {"unit":"short", "decimals":2,
                "color":{"mode":"fixed","fixedColor":color}, "min":0}, "overrides":[]},
            "options": options}
        if sql:
            item.update(datasource=DS, targets=[{"refId":"A","datasource":DS,"editorMode":"code",
                "format":"time_series" if kind == "timeseries" else "table", "rawQuery":True,"rawSql":sql}])
        panels.append(item)
        return item
    def row(title,y):
        item=panel(title,"row",0,y,24,1)
        item.update(collapsed=False,panels=[])
    def stat(title,x,sql,color=BLUE):
        return panel(title,"stat",x,4,6,4,sql,color,
            reduceOptions={"calcs":["lastNotNull"],"fields":"","values":False},
            colorMode="value",graphMode="none",justifyMode="center",textMode="auto",wideLayout=True)
    def table(title,x,y,w,h,sql,description=""):
        return panel(title,"table",x,y,w,h,sql,description=description,
            showHeader=True,cellHeight="sm",footer={"show":False})
    def bar(title,x,y,w,h,sql,color=BLUE):
        return panel(title,"barchart",x,y,w,h,sql,color,
            orientation="vertical",showValue="never",groupWidth=0.75,barWidth=0.8,
            xTickLabelRotation=-45, xTickLabelSpacing=0,
            legend={"displayMode":"list","placement":"bottom","showLegend":True},
            tooltip={"mode":"multi","sort":"desc"})
    dataset="dataset_id = ${dataset:sqlstring}"
    forecast="forecast_id = ${forecast:sqlstring}"
    panel("", "text",0,0,24,4,mode="markdown",content=(
        "# ⚡ EV CHARGING · DEMAND INTELLIGENCE\n"
        f"**{config['site_name']}** &nbsp; / &nbsp; {tz} &nbsp; / &nbsp; XGBoost\n\n"
        f"Historical study · {config['period_start']} → {config['period_end_exclusive']} (end exclusive). "
        "Forecasts estimate **session arrivals per hour**, not electrical load. "
        "Use the selectors to inspect a saved forecast and a simulated replay."))
    stat("Historical arrivals · usable hours",0,f'SELECT sum(arrivals) AS "Sessions" FROM hourly_demand WHERE {dataset}')
    stat("Observed station names",6,f'SELECT (quality->>\'charging_points\')::int AS "Stations" FROM datasets WHERE {dataset}',TEAL)["description"] = "Distinct station names, not individual connectors or available capacity."
    stat("Expected arrivals · next 24 hours",12,f'SELECT sum(prediction) AS "Expected sessions" FROM forecast_points WHERE {forecast}',ORANGE)
    stat("Busiest forecast hour · local",18,f"SELECT to_char(timestamp AT TIME ZONE '{tz}','Dy HH24:MI') AS \"Peak hour\" FROM forecast_points WHERE {forecast} ORDER BY prediction DESC,timestamp LIMIT 1",ORANGE)
    row("01  /  FORECAST EXPLORER",8)
    table("Forecast context · historical cutoff",0,9,24,4,
        f"SELECT to_char(origin AT TIME ZONE site_timezone,'YYYY-MM-DD HH24:MI') AS \"Forecast origin\", to_char(last_observation AT TIME ZONE site_timezone,'YYYY-MM-DD HH24:MI') AS \"Last observed hour start\", to_char(training_cutoff AT TIME ZONE site_timezone,'YYYY-MM-DD HH24:MI') AS \"Training cutoff (exclusive)\", site_timezone AS \"Timezone\", model_name AS \"Model\", model_version AS \"Version\", units AS \"Units\" FROM forecast_runs WHERE {forecast}")
    predicted=bar("Next 24 hours · expected session arrivals",0,13,12,9,
        f"SELECT to_char(timestamp AT TIME ZONE '{tz}','DD Mon HH24:MI') AS \"Local hour\", prediction AS \"Forecast\" FROM forecast_points WHERE {forecast} ORDER BY timestamp",ORANGE)
    predicted["description"]="24 consecutive elapsed hours. Fractional predictions are expected counts; no calibrated uncertainty interval is claimed."
    comparison=bar("Actual vs predicted · matching forecast run",12,13,12,9,
        f"SELECT to_char(p.timestamp AT TIME ZONE f.site_timezone,'DD Mon HH24:MI') AS \"Local hour\", h.arrivals AS \"Actual\", p.prediction AS \"Forecast\" FROM forecast_points p JOIN forecast_runs f ON f.forecast_id = p.forecast_id LEFT JOIN hourly_demand h ON h.dataset_id = f.dataset_id AND h.timestamp = p.timestamp WHERE p.forecast_id = ${{forecast:sqlstring}} ORDER BY p.timestamp")
    comparison["fieldConfig"]["overrides"]=[{"matcher":{"id":"byName","options":name},"properties":[{"id":"color","value":{"mode":"fixed","fixedColor":color}}]} for name,color in (("Actual",BLUE),("Forecast",ORANGE))]
    row("02  /  HISTORICAL PATTERNS",22)
    history=panel("Historical hourly arrivals · selected time range","timeseries",0,23,24,8,
        f'SELECT timestamp AS time, arrivals AS "Actual arrivals" FROM hourly_demand WHERE {dataset} AND $__timeFilter(timestamp) ORDER BY timestamp',
        legend={"displayMode":"list","placement":"bottom","calcs":["mean","max"]},tooltip={"mode":"multi"})
    history["fieldConfig"]["defaults"]["custom"]={"drawStyle":"line","lineInterpolation":"linear","lineWidth":1,"fillOpacity":15,"showPoints":"never","spanNulls":False,"axisLabel":"sessions/hour"}
    bar("Typical day · mean arrivals by hour",0,31,12,8,
        f"SELECT to_char(timestamp AT TIME ZONE '{tz}','HH24:00') AS \"Hour\", avg(arrivals) AS \"Mean sessions/hour\" FROM hourly_demand WHERE {dataset} GROUP BY 1 ORDER BY 1")
    bar("Typical week · mean arrivals by weekday",12,31,12,8,
        f"SELECT to_char(timestamp AT TIME ZONE '{tz}','Dy') AS \"Weekday\", avg(arrivals) AS \"Mean sessions/hour\" FROM hourly_demand WHERE {dataset} GROUP BY 1,extract(isodow FROM timestamp AT TIME ZONE '{tz}') ORDER BY extract(isodow FROM timestamp AT TIME ZONE '{tz}')",TEAL)
    fields=", ".join(f"avg(arrivals) FILTER (WHERE extract(hour FROM timestamp AT TIME ZONE '{tz}')={hour}) AS \"{hour:02d}\"" for hour in range(24))
    heat=table("Weekday / hour heatmap · mean sessions/hour",0,39,24,9,
        f"SELECT to_char(timestamp AT TIME ZONE '{tz}','Dy') AS \"Day\", {fields} FROM hourly_demand WHERE {dataset} GROUP BY 1,extract(isodow FROM timestamp AT TIME ZONE '{tz}') ORDER BY extract(isodow FROM timestamp AT TIME ZONE '{tz}')",
        "All usable history. Repeated DST hours contribute separate elapsed-hour observations. Empty cells indicate missing coverage.")
    heat["fieldConfig"]["defaults"].update(decimals=1,color={"mode":"continuous-BlYlRd"},custom={"cellOptions":{"type":"color-background","mode":"basic"},"width":44})
    heat["fieldConfig"]["overrides"]=[{"matcher":{"id":"byName","options":"Day"},"properties":[{"id":"custom.width","value":80},{"id":"custom.cellOptions","value":{"type":"auto"}}]}]
    row("03  /  MODEL PERFORMANCE",48)
    bar("Held-out test · MAE and RMSE",0,49,12,8,
        "SELECT model AS \"Method\", mae AS \"MAE\", rmse AS \"RMSE\" FROM evaluation_results WHERE split='test' AND model_version=(SELECT model_version FROM forecast_runs WHERE "+forecast+") ORDER BY mae")
    table("Validation/test metrics · sessions/hour",12,49,12,8,
        f"SELECT split, model, round(mae::numeric,3) AS mae, round(rmse::numeric,3) AS rmse, origins, forecast_hours FROM evaluation_results WHERE model_version=(SELECT model_version FROM forecast_runs WHERE {forecast}) ORDER BY split,mae")
    table("Evaluation protocol · identical 24-hour forecast origins",0,57,24,4,
        f"SELECT DISTINCT details->>'selected_model' AS \"Validation winner\", to_char(period_start AT TIME ZONE '{tz}','YYYY-MM-DD HH24:MI') AS \"Test start\", to_char(period_end AT TIME ZONE '{tz}','YYYY-MM-DD HH24:MI') AS \"Test end exclusive\", origins AS \"Test origins\", forecast_hours AS \"Evaluated hours\" FROM evaluation_results WHERE split='test' AND model_version=(SELECT model_version FROM forecast_runs WHERE {forecast})")
    row("04  /  DATA QUALITY & PROVENANCE",61)
    table("Dataset coverage and quality",0,62,24,5,
        f"SELECT quality->>'site_name' AS \"Location\", quality->>'first_connection_local' AS \"First selected arrival\", quality->>'last_connection_local' AS \"Last selected arrival\", (quality->>'local_days')::int AS \"Days\", (quality->>'assumed_zero_hours')::int AS \"Assumed-zero hours\", (quality->>'known_missing_hours')::int+(quality->>'unknown_coverage_hours')::int AS \"Masked hours\", quality->>'coverage_status' AS \"Source status\" FROM datasets WHERE {dataset}")
    table("Quality warnings · interpretation matters",0,67,24,8,
        f"SELECT json_array_elements_text(quality->'warnings') AS \"Data-quality notes\" FROM datasets WHERE {dataset}")
    row("05  /  HISTORICAL DATA REPLAY — SIMULATED IOT FEED",75)
    table("Historical data replay — simulated IoT feed",0,76,24,4,
        "SELECT r.run_id AS \"Demo run\", r.generation AS \"Reset generation\", count(e.event_id) AS \"Unique arrivals ingested\", max(e.received_at) AS \"Last ingestion time\" FROM replay_runs r LEFT JOIN arrival_events e ON e.run_id=r.run_id WHERE r.run_id=${replay:sqlstring} GROUP BY r.run_id,r.generation")
    table("Incoming replay events · arrival fields only",0,80,24,8,
        f"SELECT event_id AS \"Event ID\", to_char(timestamp AT TIME ZONE '{tz}','YYYY-MM-DD HH24:MI:SS') AS \"Historical arrival ({tz})\", charger_id AS \"Source station\", received_at AS \"Ingested at\" FROM arrival_events WHERE run_id=${{replay:sqlstring}} ORDER BY received_at DESC LIMIT 20")
    panel("How to use this prototype","text",0,88,24,4,mode="markdown",content=(
        "**Replay controls:** use the Python CLI to start/resume; Ctrl+C pauses; `--reset` resets only the selected demo run. "
        "Replay events never increase the training counts.\n\n"
        "**Capacity planning:** arrival peaks can guide staffing studies and further measurement. "
        "They do not establish queue lengths, waiting times, charger shortages or electrical power requirements. "
        "This US dataset does not validate an Indian-campus deployment."))
    queries = {
        "dataset": ("Dataset", "SELECT quality->>'site_name' AS __text,dataset_id AS __value FROM datasets WHERE site_id='boulder-carpenter-park' ORDER BY created_at DESC"),
        "forecast": ("Historical forecast run", "SELECT to_char(origin AT TIME ZONE site_timezone,'DD Mon YYYY HH24:MI') || ' · ' || left(forecast_id,8) AS __text,forecast_id AS __value FROM forecast_runs WHERE dataset_id=${dataset:sqlstring} ORDER BY created_at DESC"),
        "replay": ("Replay run", "SELECT run_id AS __text,run_id AS __value FROM replay_runs ORDER BY created_at DESC")}
    variables=[{"name":name,"label":label,"type":"query","datasource":DS,"query":query,"definition":query,
        "refresh":1,"multi":False,"includeAll":False,"sort":0,"options":[]} for name,(label,query) in queries.items()]
    dashboard={"uid":"evforecast-demand","title":"EV Charging | Demand Intelligence","description":"Historical Boulder session-arrival forecasting and simulated IoT ingestion.",
        "tags":["EV charging","Boulder","historical replay"],"schemaVersion":41,"version":2,"editable":False,
        "timezone":tz,"refresh":"30s","time":{"from":evaluation["test_start"],"to":evaluation["test_end_exclusive"]},
        "timepicker":{},"templating":{"list":variables},"panels":panels,
        "links":[{"title":"API & replay documentation","url":"http://127.0.0.1:8000/docs","type":"link","targetBlank":True}]}
    (ROOT/"infra/grafana/dashboards/evforecast.json").write_text(json.dumps(dashboard,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Generated {len(panels)} panels with historical range and {tz} timezone.")

if __name__ == "__main__":
    main()
