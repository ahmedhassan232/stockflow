#!/usr/bin/env bash
# Creates the two least-privilege roles and the application + test databases.
#   * DB_OWNER_USER – owns the schema, runs Alembic migrations.
#   * DB_APP_USER   – runtime role: NOSUPERUSER, NOBYPASSRLS, owns nothing,
#                     so Row Level Security can never be skipped by the API.
# Idempotent. Runs automatically inside the postgres container on first boot;
# locally:  sudo -u postgres env DB_OWNER_PASSWORD=.. DB_APP_PASSWORD=.. bash this-file
set -euo pipefail

: "${POSTGRES_DB:=stockflow}"
: "${DB_OWNER_USER:=stockflow_owner}"
: "${DB_APP_USER:=stockflow_app}"
: "${DB_OWNER_PASSWORD:?DB_OWNER_PASSWORD is required}"
: "${DB_APP_PASSWORD:?DB_APP_PASSWORD is required}"

PSQL=(psql -v ON_ERROR_STOP=1 --no-psqlrc)
[ -n "${POSTGRES_USER:-}" ] && PSQL+=(--username "$POSTGRES_USER")

"${PSQL[@]}" --dbname postgres \
  -v owner="$DB_OWNER_USER" -v owner_pw="$DB_OWNER_PASSWORD" \
  -v app="$DB_APP_USER" -v app_pw="$DB_APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I', :'owner') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'owner') \gexec
SELECT format('CREATE ROLE %I', :'app')   WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app') \gexec
ALTER ROLE :"owner" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'owner_pw';
ALTER ROLE :"app"   LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_pw';
SQL

for db in "$POSTGRES_DB" "${POSTGRES_DB}_test"; do
  "${PSQL[@]}" --dbname postgres -v db="$db" -v owner="$DB_OWNER_USER" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'owner')
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db') \gexec
ALTER DATABASE :"db" OWNER TO :"owner";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
SQL
  "${PSQL[@]}" --dbname "$db" -v db="$db" -v owner="$DB_OWNER_USER" -v app="$DB_APP_USER" <<'SQL'
GRANT CONNECT ON DATABASE :"db" TO :"app";
ALTER SCHEMA public OWNER TO :"owner";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app";
SQL
done
echo "StockFlow roles and databases are ready."
