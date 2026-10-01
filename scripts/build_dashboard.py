"""Generate the provisioned Grafana dashboard from current dataset/model metadata."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DS = {"type": "postgres", "uid": "evforecast-postgres"}

# ── Professional color palette ──────────────────────────────────────
PRIMARY   = "#6C63FF"   # Electric violet – primary accent
SECONDARY = "#FF6B6B"   # Coral – secondary / alerts
SUCCESS   = "#2ECE71"   # Emerald green – positive / actual
FORECAST  = "#F5A623"   # Amber – predictions
INFO      = "#4FC3F7"   # Sky blue – informational
MUTED     = "#8E8E93"   # Neutral gray
BG_DARK   = "#1A1A2E"   # Deep navy background accent

# Semantic aliases
ACTUAL_COLOR   = PRIMARY
PREDICT_COLOR  = FORECAST
COMPARE_A      = "#6C63FF"  # Actual
COMPARE_B      = "#FF6B6B"  # Predicted
HEATMAP_SCHEME = "continuous-BlYlRd"

def main():
    config = json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
    quality = json.loads((ROOT/"reports/data_quality.json").read_text())
    evaluation = json.loads((ROOT/"reports/evaluation.json").read_text())
    tz = config["timezone"]
    panels = []

    # ── Panel builder helpers ───────────────────────────────────────
    def panel(title, kind, x, y, w, h, sql=None, color=PRIMARY, description="", transparent=False, **options):
        item = {
            "id": len(panels)+1, "title": title, "type": kind,
            "description": description,
            "gridPos": {"x":x, "y":y, "w":w, "h":h},
            "transparent": transparent,
            "fieldConfig": {
                "defaults": {
                    "unit": "short", "decimals": 2,
                    "color": {"mode": "fixed", "fixedColor": color},
                    "min": 0,
                    "noValue": "—",
                },
                "overrides": []
            },
            "options": options,
        }
        if sql:
            item.update(datasource=DS, targets=[{
                "refId": "A", "datasource": DS, "editorMode": "code",
                "format": "time_series" if kind == "timeseries" else "table",
                "rawQuery": True, "rawSql": sql}])
        panels.append(item)
        return item

    def row(title, y, collapsed=False):
        item = panel(title, "row", 0, y, 24, 1)
        item.update(collapsed=collapsed, panels=[])

    def stat(title, x, y, sql, color=PRIMARY, unit="short", description=""):
        p = panel(title, "stat", x, y, 6, 4, sql, color,
            description=description, transparent=True,
            reduceOptions={"calcs": ["lastNotNull"], "fields": "", "values": False},
            colorMode="value", graphMode="none", justifyMode="center",
            textMode="auto", wideLayout=True)
        p["fieldConfig"]["defaults"]["unit"] = unit
        return p

    def table(title, x, y, w, h, sql, description=""):
        return panel(title, "table", x, y, w, h, sql, description=description,
            showHeader=True, cellHeight="sm",
            footer={"show": False},
            sortBy=[])

    def bar(title, x, y, w, h, sql, color=PRIMARY, orientation="vertical"):
        return panel(title, "barchart", x, y, w, h, sql, color,
            orientation=orientation, showValue="never",
            groupWidth=0.7, barWidth=0.85, barRadius=0.15,
            xTickLabelRotation=-45, xTickLabelSpacing=0,
            legend={"displayMode": "list", "placement": "bottom", "showLegend": True},
            tooltip={"mode": "multi", "sort": "desc"})

    dataset  = "dataset_id = ${dataset:sqlstring}"
    forecast = "forecast_id = ${forecast:sqlstring}"

    # ═══════════════════════════════════════════════════════════════════
    # ROW 0 — HEADER BANNER
    # ═══════════════════════════════════════════════════════════════════
    panel("", "text", 0, 0, 24, 5, transparent=True, mode="markdown", content=(
        '<div style="text-align:center; padding: 12px 0;">\n\n'
        '# ⚡ EV CHARGING DEMAND INTELLIGENCE\n\n'
        f'**{config["site_name"]}** &nbsp; · &nbsp; `{tz}` &nbsp; · &nbsp; XGBoost Recursive Forecasting\n\n'
        '---\n\n'
        f'📅 Historical study period: **{config["period_start"]}** → **{config["period_end_exclusive"]}** (exclusive) &nbsp; | &nbsp; '
        '📊 Metric: **Sessions / hour** &nbsp; | &nbsp; '
        '🔋 Not electrical load\n\n'
        '</div>'))

    # ═══════════════════════════════════════════════════════════════════
    # ROW 1 — KPI STAT CARDS
    # ═══════════════════════════════════════════════════════════════════
    stat("📈 Historical Sessions", 0, 5,
        f'SELECT sum(arrivals) AS "Sessions" FROM hourly_demand WHERE {dataset}',
        PRIMARY, description="Total observed session arrivals across all usable hours in the selected dataset.")

    stat("🔌 Station Names", 6, 5,
        f"SELECT (quality->>'charging_points')::int AS \"Stations\" FROM datasets WHERE {dataset}",
        INFO, description="Distinct station names reported in source data. Does not equal individual connector/port count.")

    stat("🔮 Next 24h Expected", 12, 5,
        f'SELECT sum(prediction) AS "Expected" FROM forecast_points WHERE {forecast}',
        FORECAST, description="Sum of predicted session arrivals over the next 24 forecast hours.")

    stat("⏰ Peak Forecast Hour", 18, 5,
        f"SELECT to_char(timestamp AT TIME ZONE '{tz}','Dy HH24:MI') AS \"Peak\" FROM forecast_points WHERE {forecast} ORDER BY prediction DESC,timestamp LIMIT 1",
        SECONDARY, description="Local hour with the highest predicted session arrivals in the selected forecast run.")

    # ═══════════════════════════════════════════════════════════════════
    # ROW 2 — FORECAST EXPLORER
    # ═══════════════════════════════════════════════════════════════════
    row("⚡  FORECAST EXPLORER", 9)

    table("Forecast Context", 0, 10, 24, 4,
        f"SELECT to_char(origin AT TIME ZONE site_timezone,'YYYY-MM-DD HH24:MI') AS \"Forecast Origin\", "
        f"to_char(last_observation AT TIME ZONE site_timezone,'YYYY-MM-DD HH24:MI') AS \"Last Observed Hour\", "
        f"to_char(training_cutoff AT TIME ZONE site_timezone,'YYYY-MM-DD HH24:MI') AS \"Training Cutoff\", "
        f"site_timezone AS \"Timezone\", model_name AS \"Model\", model_version AS \"Version\", units AS \"Units\" "
        f"FROM forecast_runs WHERE {forecast}",
        "Metadata for the selected forecast run including origin timestamp, training cutoff, and model version.")

    predicted = bar("Next 24 Hours · Expected Arrivals", 0, 14, 12, 10,
        f"SELECT to_char(timestamp AT TIME ZONE '{tz}','DD Mon HH24:MI') AS \"Local hour\", "
        f"prediction AS \"Forecast\" FROM forecast_points WHERE {forecast} ORDER BY timestamp",
        FORECAST)
    predicted["description"] = "24 consecutive elapsed hours of predicted session arrivals. Fractional values are expected counts; no calibrated uncertainty interval is claimed."

    comparison = bar("Actual vs Predicted", 12, 14, 12, 10,
        f"SELECT to_char(p.timestamp AT TIME ZONE f.site_timezone,'DD Mon HH24:MI') AS \"Local hour\", "
        f"h.arrivals AS \"Actual\", p.prediction AS \"Forecast\" FROM forecast_points p "
        f"JOIN forecast_runs f ON f.forecast_id = p.forecast_id "
        f"LEFT JOIN hourly_demand h ON h.dataset_id = f.dataset_id AND h.timestamp = p.timestamp "
        f"WHERE p.forecast_id = ${{forecast:sqlstring}} ORDER BY p.timestamp")
    comparison["fieldConfig"]["overrides"] = [
        {"matcher": {"id": "byName", "options": "Actual"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": COMPARE_A}}]},
        {"matcher": {"id": "byName", "options": "Forecast"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": COMPARE_B}}]}]
    comparison["description"] = "Side-by-side comparison of actual observed arrivals vs model predictions for the same 24-hour window."

    # ═══════════════════════════════════════════════════════════════════
    # ROW 3 — HISTORICAL PATTERNS
    # ═══════════════════════════════════════════════════════════════════
    row("📊  HISTORICAL PATTERNS", 24)

    history = panel("Historical Hourly Arrivals", "timeseries", 0, 25, 24, 9,
        f'SELECT timestamp AS time, arrivals AS "Session arrivals" FROM hourly_demand WHERE {dataset} AND $__timeFilter(timestamp) ORDER BY timestamp',
        PRIMARY,
        legend={"displayMode": "list", "placement": "bottom", "calcs": ["mean", "max", "sum"]},
        tooltip={"mode": "multi", "sort": "desc"})
    history["fieldConfig"]["defaults"]["custom"] = {
        "drawStyle": "line", "lineInterpolation": "smooth",
        "lineWidth": 2, "fillOpacity": 20, "gradientMode": "opacity",
        "showPoints": "never", "spanNulls": False,
        "axisLabel": "sessions/hour",
        "thresholdsStyle": {"mode": "off"}}
    history["description"] = "Interactive time series of hourly session arrivals. Use the time range picker to zoom into specific periods."

    bar("Typical Day · Mean by Hour", 0, 34, 8, 9,
        f"SELECT to_char(timestamp AT TIME ZONE '{tz}','HH24:00') AS \"Hour\", "
        f"avg(arrivals) AS \"Mean sessions/hour\" FROM hourly_demand WHERE {dataset} GROUP BY 1 ORDER BY 1",
        PRIMARY)

    bar("Typical Week · Mean by Weekday", 8, 34, 8, 9,
        f"SELECT to_char(timestamp AT TIME ZONE '{tz}','Dy') AS \"Weekday\", "
        f"avg(arrivals) AS \"Mean sessions/hour\" FROM hourly_demand WHERE {dataset} "
        f"GROUP BY 1,extract(isodow FROM timestamp AT TIME ZONE '{tz}') "
        f"ORDER BY extract(isodow FROM timestamp AT TIME ZONE '{tz}')",
        SUCCESS)

    # Gauge: overall average arrivals per hour
    gauge = panel("Avg Sessions/Hour", "gauge", 16, 34, 8, 9,
        f'SELECT avg(arrivals) AS "Avg" FROM hourly_demand WHERE {dataset}',
        PRIMARY, description="Overall average sessions per hour across all usable history.",
        orientation="auto", showThresholdLabels=False, showThresholdMarkers=True)
    gauge["fieldConfig"]["defaults"]["unit"] = "short"
    gauge["fieldConfig"]["defaults"]["decimals"] = 2
    gauge["fieldConfig"]["defaults"]["thresholds"] = {
        "mode": "absolute",
        "steps": [
            {"color": SUCCESS, "value": None},
            {"color": FORECAST, "value": 1},
            {"color": SECONDARY, "value": 2}]}
    gauge["fieldConfig"]["defaults"]["max"] = 4

    # Heatmap table
    fields = ", ".join(
        f"avg(arrivals) FILTER (WHERE extract(hour FROM timestamp AT TIME ZONE '{tz}')={hour}) AS \"{hour:02d}\""
        for hour in range(24))
    heat = table("Weekday × Hour Heatmap · Mean Sessions/Hour", 0, 43, 24, 10,
        f"SELECT to_char(timestamp AT TIME ZONE '{tz}','Dy') AS \"Day\", {fields} "
        f"FROM hourly_demand WHERE {dataset} "
        f"GROUP BY 1,extract(isodow FROM timestamp AT TIME ZONE '{tz}') "
        f"ORDER BY extract(isodow FROM timestamp AT TIME ZONE '{tz}')",
        "Demand intensity by weekday and hour. Darker red = higher demand. Empty cells indicate missing coverage.")
    heat["fieldConfig"]["defaults"].update(
        decimals=1,
        color={"mode": HEATMAP_SCHEME},
        custom={"cellOptions": {"type": "color-background", "mode": "basic"}, "width": 44})
    heat["fieldConfig"]["overrides"] = [{
        "matcher": {"id": "byName", "options": "Day"},
        "properties": [
            {"id": "custom.width", "value": 80},
            {"id": "custom.cellOptions", "value": {"type": "auto"}}]}]

    # ═══════════════════════════════════════════════════════════════════
    # ROW 4 — MODEL PERFORMANCE
    # ═══════════════════════════════════════════════════════════════════
    row("🏆  MODEL PERFORMANCE", 53)

    metrics_bar = bar("Test Set · MAE & RMSE Comparison", 0, 54, 12, 9,
        "SELECT model AS \"Method\", mae AS \"MAE\", rmse AS \"RMSE\" FROM evaluation_results "
        "WHERE split='test' AND model_version=(SELECT model_version FROM forecast_runs WHERE "
        + forecast + ") ORDER BY mae")
    metrics_bar["fieldConfig"]["overrides"] = [
        {"matcher": {"id": "byName", "options": "MAE"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": PRIMARY}}]},
        {"matcher": {"id": "byName", "options": "RMSE"}, "properties": [
            {"id": "color", "value": {"mode": "fixed", "fixedColor": SECONDARY}}]}]
    metrics_bar["description"] = "Lower is better. MAE = Mean Absolute Error; RMSE = Root Mean Squared Error. Both measured in sessions/hour on held-out test data."

    table("Full Metrics Table", 12, 54, 12, 9,
        f"SELECT split AS \"Split\", model AS \"Model\", round(mae::numeric,3) AS \"MAE\", "
        f"round(rmse::numeric,3) AS \"RMSE\", origins AS \"Origins\", forecast_hours AS \"Hours\" "
        f"FROM evaluation_results WHERE model_version=(SELECT model_version FROM forecast_runs WHERE {forecast}) ORDER BY split,mae",
        "Validation and test performance for all models. XGBoost was selected by validation MAE; test metrics are reported for comparison only.")

    table("Evaluation Protocol", 0, 63, 24, 4,
        f"SELECT DISTINCT details->>'selected_model' AS \"Validation Winner\", "
        f"to_char(period_start AT TIME ZONE '{tz}','YYYY-MM-DD HH24:MI') AS \"Test Start\", "
        f"to_char(period_end AT TIME ZONE '{tz}','YYYY-MM-DD HH24:MI') AS \"Test End (exclusive)\", "
        f"origins AS \"Test Origins\", forecast_hours AS \"Evaluated Hours\" "
        f"FROM evaluation_results WHERE split='test' AND model_version=(SELECT model_version FROM forecast_runs WHERE {forecast})",
        "Chronological rolling-origin evaluation protocol. Each origin produces a complete 24-hour recursive forecast.")

    # ═══════════════════════════════════════════════════════════════════
    # ROW 5 — DATA QUALITY & PROVENANCE
    # ═══════════════════════════════════════════════════════════════════
    row("🔍  DATA QUALITY & PROVENANCE", 67)

    table("Dataset Coverage", 0, 68, 24, 5,
        f"SELECT quality->>'site_name' AS \"Location\", "
        f"quality->>'first_connection_local' AS \"First Arrival\", "
        f"quality->>'last_connection_local' AS \"Last Arrival\", "
        f"(quality->>'local_days')::int AS \"Days\", "
        f"(quality->>'assumed_zero_hours')::int AS \"Assumed-Zero Hours\", "
        f"(quality->>'known_missing_hours')::int+(quality->>'unknown_coverage_hours')::int AS \"Masked Hours\", "
        f"quality->>'coverage_status' AS \"Source Status\" FROM datasets WHERE {dataset}",
        "Source dataset coverage summary. Assumed-zero hours have no observed arrivals but no confirmed feed outage either.")

    table("Quality Warnings", 0, 73, 24, 8,
        f"SELECT json_array_elements_text(quality->'warnings') AS \"⚠️  Data Quality Notes\" FROM datasets WHERE {dataset}",
        "Operational caveats and data limitations that affect interpretation. Read these before drawing conclusions.")

    # ═══════════════════════════════════════════════════════════════════
    # ROW 6 — SIMULATED IOT REPLAY
    # ═══════════════════════════════════════════════════════════════════
    row("📡  SIMULATED IoT REPLAY", 81)

    table("Replay Run Summary", 0, 82, 12, 5,
        "SELECT r.run_id AS \"Run ID\", r.generation AS \"Generation\", "
        "count(e.event_id) AS \"Events Ingested\", "
        "max(e.received_at) AS \"Last Ingestion\" "
        "FROM replay_runs r LEFT JOIN arrival_events e ON e.run_id=r.run_id "
        "WHERE r.run_id=${replay:sqlstring} GROUP BY r.run_id,r.generation",
        "Summary of the selected replay run including reset generation and event count.")

    # Live event rate (arrivals per minute since replay started)
    table("Replay Statistics", 12, 82, 12, 5,
        "SELECT count(e.event_id) AS \"Total Events\", "
        "min(e.received_at) AS \"First Ingestion\", "
        "max(e.received_at) AS \"Latest Ingestion\", "
        "CASE WHEN count(e.event_id) > 1 THEN "
        "round(EXTRACT(EPOCH FROM max(e.received_at) - min(e.received_at))::numeric / "
        "GREATEST(count(e.event_id)-1, 1), 1) ELSE 0 END AS \"Avg Seconds Between Events\" "
        "FROM arrival_events e WHERE e.run_id=${replay:sqlstring}",
        "Timing statistics for the selected replay run.")

    table("Latest Replay Events", 0, 87, 24, 9,
        f"SELECT event_id AS \"Event ID\", "
        f"to_char(timestamp AT TIME ZONE '{tz}','YYYY-MM-DD HH24:MI:SS') AS \"Historical Arrival ({tz})\", "
        f"charger_id AS \"Station / Charger\", "
        f"to_char(received_at AT TIME ZONE '{tz}','YYYY-MM-DD HH24:MI:SS') AS \"Ingested At\" "
        f"FROM arrival_events WHERE run_id=${{replay:sqlstring}} ORDER BY received_at DESC LIMIT 20",
        "Most recent 20 replay events with their historical arrival timestamps and ingestion times.")

    panel("How to Use This Prototype", "text", 0, 96, 24, 5, transparent=True, mode="markdown", content=(
        '<div style="padding: 8px 0;">\n\n'
        '### 🎮 Replay Controls\n'
        '```\n'
        'python -m evforecast simulate --api-url http://127.0.0.1:8000 --run-id demo --speed 3600 --reset\n'
        '```\n'
        '- **Ctrl+C** pauses replay; rerun resumes without duplicates\n'
        '- `--reset` resets only the selected run (does not delete training history or Docker volumes)\n'
        '- `--speed 100000000 --limit 10` for quick demo\n\n'
        '### ⚠️ Important Limitations\n'
        '- Arrival peaks guide capacity **studies**, not definitive capacity decisions\n'
        '- Cannot establish queue lengths, waiting times, charger shortages, or electrical power requirements\n'
        '- This is a **US municipal dataset** — results do not validate an Indian-campus deployment\n'
        '- Data ends November 2023 — these are **not live predictions**\n\n'
        '</div>'))

    # ═══════════════════════════════════════════════════════════════════
    # TEMPLATE VARIABLES
    # ═══════════════════════════════════════════════════════════════════
    queries = {
        "dataset": ("Dataset",
            "SELECT quality->>'site_name' AS __text,dataset_id AS __value FROM datasets WHERE site_id='boulder-carpenter-park' ORDER BY created_at DESC"),
        "forecast": ("Forecast Run",
            "SELECT to_char(origin AT TIME ZONE site_timezone,'DD Mon YYYY HH24:MI') || ' · ' || left(forecast_id,8) AS __text,forecast_id AS __value FROM forecast_runs WHERE dataset_id=${dataset:sqlstring} ORDER BY created_at DESC"),
        "replay": ("Replay Run",
            "SELECT run_id AS __text,run_id AS __value FROM replay_runs ORDER BY created_at DESC"),
    }
    variables = [{
        "name": name, "label": label, "type": "query", "datasource": DS,
        "query": query, "definition": query,
        "refresh": 1, "multi": False, "includeAll": False, "sort": 0, "options": []
    } for name, (label, query) in queries.items()]

    # ═══════════════════════════════════════════════════════════════════
    # DASHBOARD ASSEMBLY
    # ═══════════════════════════════════════════════════════════════════
    dashboard = {
        "uid": "evforecast-demand",
        "title": "⚡ EV Charging | Demand Intelligence",
        "description": "IoT-Based EV Charging Demand Forecasting — Boulder historical session-arrival forecasting with XGBoost and simulated IoT ingestion.",
        "tags": ["EV charging", "IoT", "XGBoost", "Boulder", "forecasting"],
        "schemaVersion": 41,
        "version": 3,
        "editable": False,
        "timezone": tz,
        "refresh": "30s",
        "time": {
            "from": config["period_start"] + "T00:00:00Z",
            "to": config["period_end_exclusive"] + "T00:00:00Z",
        },
        "timepicker": {"refresh_intervals": ["10s", "30s", "1m", "5m"]},
        "templating": {"list": variables},
        "panels": panels,
        "links": [
            {"title": "📖 API Documentation", "url": "http://127.0.0.1:8000/docs", "type": "link", "targetBlank": True, "icon": "doc"},
            {"title": "💻 GitHub Repository", "url": "https://github.com/garvitsingh1336/IOTbased-EVChargingDemandForecasting", "type": "link", "targetBlank": True, "icon": "external link"},
        ],
        "annotations": {"list": []},
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,  # Shared crosshair
        "liveNow": False,
    }

    out = ROOT / "infra/grafana/dashboards/evforecast.json"
    out.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {len(panels)} panels with historical range and {tz} timezone.")
    print(f"   Dashboard: {out}")

if __name__ == "__main__":
    main()
