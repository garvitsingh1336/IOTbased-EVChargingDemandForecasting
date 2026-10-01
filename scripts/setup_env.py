"""Generate local credentials once. Never overwrite an existing .env or print secrets."""
from pathlib import Path
import secrets
ROOT = Path(__file__).resolve().parents[1]
path = ROOT / ".env"
if path.exists():
    print(".env already exists; preserved.")
else:
    values = {
        "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": "5432",
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "GRAFANA_READER_PASSWORD": secrets.token_hex(24),
        "GRAFANA_ADMIN_USER": "admin", "GRAFANA_ADMIN_PASSWORD": secrets.token_hex(24),
        "GRAFANA_PORT": "3000",
    }
    with path.open("x", encoding="utf-8") as output:
        output.write("\n".join(f"{key}={value}" for key, value in values.items())+"\n")
    print("Created ignored .env with random local credentials. Use its Grafana admin password to log in.")
