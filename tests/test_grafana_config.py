"""Static provisioning checks only; not a claim of Grafana query execution."""
import json
from pathlib import Path
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from evforecast.database import schema
ROOT=Path(__file__).resolve().parents[1]

def test_dashboard_pins_historical_time_and_one_run_comparison():
    dashboard=json.loads((ROOT/"infra/grafana/dashboards/evforecast.json").read_text(encoding="utf-8"))
    assert dashboard["timezone"]=="America/Denver"
    assert dashboard["time"]["from"].startswith("2023-")
    comparison=next(p for p in dashboard["panels"] if p["title"].startswith("Actual vs"))
    sql=comparison["targets"][0]["rawSql"]
    assert "p.forecast_id = ${forecast:sqlstring}" in sql
    assert "h.dataset_id = f.dataset_id" in sql
    assert "h.timestamp = p.timestamp" in sql
    assert "sum(" not in sql.lower()
    for table in schema.sorted_tables:
        statement=str(CreateTable(table).compile(dialect=postgresql.dialect()))
        if "timestamp" in table.c or table.name=="forecast_runs":
            assert "TIMESTAMP WITH TIME ZONE" in statement

def test_reader_provisioning_uses_select_and_no_plugins():
    init=(ROOT/"infra/postgres/init-reader.sh").read_text()
    assert "GRANT SELECT" in init and "default_transaction_read_only = on" in init
    assert "GRANT ALL" not in init
    compose=(ROOT/"compose.yaml").read_text()
    assert "GF_INSTALL_PLUGINS" not in compose
