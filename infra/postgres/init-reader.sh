#!/bin/sh
set -eu
# psql quotes the password as a SQL literal; it is not interpolated into shell SQL.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 --set=reader_password="$GRAFANA_READER_PASSWORD" <<'SQL'
CREATE ROLE grafana_reader LOGIN PASSWORD :'reader_password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE evforecast TO grafana_reader;
GRANT USAGE ON SCHEMA public TO grafana_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE ev_app IN SCHEMA public GRANT SELECT ON TABLES TO grafana_reader;
ALTER ROLE grafana_reader SET default_transaction_read_only = on;
SQL
