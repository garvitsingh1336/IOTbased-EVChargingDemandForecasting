import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_config(path=None):
    path = Path(path) if path else ROOT / "config.json"
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    config["root"] = ROOT
    if not Path(config["source"]).is_absolute():
        config["source"] = str(ROOT / config["source"])
    for folder in ("data", "artifacts", "reports", "runtime", "docs/reports"):
        (ROOT / folder).mkdir(exist_ok=True, parents=True)
    return config

def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=str, allow_nan=False), encoding="utf-8")
