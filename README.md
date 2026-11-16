# StockFlow

**Smart Inventory, Warehouse & Sales Management — multi-tenant SaaS.**
Arabic-first (RTL) with English (LTR). FastAPI · PostgreSQL 17 · Redis · Celery · React · TypeScript.

> **Project status: Phases 1–11 are implemented and tested; Phase 12 is partly done.**
> Working today (API + Arabic/English UI): company registration and login, roles and
> permissions, branches, warehouses, employees, products, stock ledger (adjustments,
> transfers, minimum levels), purchasing (order → receive → return → pay), POS and sales
> invoices (payments, credit, returns, void), dashboard and sales/profit reports,
> low-stock notifications, activity log, company settings.
> Also included: expenses and net profit, CSV export (invoices, stock, expenses, reports),
> e-mail confirmation, a daily low-stock e-mail digest and a platform-admin console.
> Server-side PDF (WeasyPrint, Arabic/RTL) for invoices and the sales/profit reports, and an
> append-only platform action log.
> **Limits:** the Docker stack has not been run end-to-end (developed natively against
> PostgreSQL 17 + Redis; SMTP and Celery worker/beat were exercised against a local SMTP
> server) and nothing is deployed — see [docs/deployment.md](docs/deployment.md).

## Roadmap

| # | Phase | Status |
|---|---|---|
| 1 | Foundation | ✅ done |
| 2 | Database & multi-tenancy (RLS, composite FKs, isolation tests) | ✅ done |
| 3 | Authentication & authorization | ✅ done |
| 4 | Organization management (branches, warehouses, employees, roles, settings) | ✅ done |
| 5 | Product management | ✅ done |
| 6 | Inventory management (immutable stock ledger) | ✅ done |
| 7 | Purchasing | ✅ done |
| 8 | Sales & POS | ✅ done |
| 9 | Analytics & reporting | ✅ dashboard, sales and profit reports, expenses / net profit, CSV export |
| 10 | Notifications & background tasks | ✅ in-app low-stock alerts, scheduled scan, daily e-mail digest |
| 11 | Frontend completion | ✅ all screens above, including the platform-admin console |
| 12 | Testing & production readiness | 🟡 149 backend tests, demo seed, deployment guide; Docker stack untested, no browser test suite in CI |

## Platform administrator

```bash
cd backend && python -m app.scripts.platform_admin grant someone@example.com   # also: revoke, list
```

The person must already have an account. The flag can only be set by this CLI (owner
database role); a database trigger blocks the application role from granting it.

## Demo data

```bash
cd backend && python -m app.scripts.seed_demo     # refuses to run with APP_ENV=production
```

Creates the company "النيل للتجارة" with 10 products, opening stock (through a real
purchase order), customers and 7 invoices. Sign in with
`owner@demo-nile.example.com` / `StockFlow-Demo-2026` (development only).

## Technology

| Area | Stack |
|---|---|
| Backend | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy (async, psycopg 3), Alembic, Celery, Redis |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn-style UI, TanStack Query, Axios, i18next, Lucide |
| Infra | Docker Compose, Nginx, Mailpit (dev), GitHub Actions |

Architecture: [docs/architecture.md](docs/architecture.md) · Database: [docs/database-schema.md](docs/database-schema.md) · Tenant isolation: [docs/tenant-isolation.md](docs/tenant-isolation.md) · Security: [docs/security.md](docs/security.md) · Business rules: [docs/business-rules.md](docs/business-rules.md) · Deployment: [docs/deployment.md](docs/deployment.md)

## Repository layout

```
backend/         FastAPI app (app/), Alembic (migrations/), tests/
frontend/        React SPA (src/app, components, features, layouts, pages, i18n, services …)
infrastructure/  docker/ (Dockerfiles, postgres init script), nginx/ (dev + prod gateways)
docs/            architecture and database design
scripts/         local helper scripts
```

## Run with Docker

```bash
cp .env.example .env          # then change every "change-me" value
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:8080 | Web app (through Nginx) |
| http://localhost:8080/api/v1/docs | Swagger / OpenAPI |
| http://localhost:8080/api/v1/health/live | Liveness |
| http://localhost:8080/api/v1/health/ready | Readiness (PostgreSQL + Redis) |
| http://localhost:8025 | Mailpit inbox |

Migrations run automatically (`migrate` service). Manually:

```bash
docker compose run --rm migrate alembic upgrade head
docker compose run --rm migrate alembic revision -m "message"
docker compose exec backend pytest
docker compose exec frontend npm test
```

Production: `docker compose -f docker-compose.prod.yml --env-file .env up -d --build`
(only Nginx publishes ports; PostgreSQL and Redis stay on an internal network). A full
deployment guide (HTTPS, backups, restore) is delivered in Phase 12.

## Run without Docker

Needs PostgreSQL 17, Redis, Python 3.12+, Node 20.19+.

```bash
# 1. roles + databases (stockflow, stockflow_test)
sudo -u postgres env DB_OWNER_PASSWORD=<owner-pw> DB_APP_PASSWORD=<app-pw> \
  bash infrastructure/docker/postgres/10-init-roles.sh

# 2. backend/.env  – same keys as .env.example, with host 127.0.0.1 instead of postgres/redis

# 3. install, migrate, test
scripts/dev-local.sh setup
scripts/dev-local.sh test

# 4. run
(cd backend && .venv/bin/uvicorn app.main:app --reload)      # :8000
(cd frontend && npm run dev)                                  # :5173, proxies /api → :8000
(cd backend && .venv/bin/celery -A app.tasks.celery_app worker -B --loglevel=INFO)   # optional
```

## Security baseline already in place

* Runtime DB role is `NOSUPERUSER NOBYPASSRLS`, owns nothing and cannot run DDL (tested).
* Tenant context is transaction-local and cannot leak through the connection pool (tested).
* CORS is an explicit allowlist; wildcard is rejected at startup in production.
* Errors never expose driver/SQL details (tested); every response carries `X-Request-ID`.
* No secrets in the repository; `.env` is git-ignored; frontend only receives `VITE_*` public values.

## Demo accounts & screenshots

Register a company from `/register` to get an owner account. A full seed script (two demo
companies with sample data) is delivered with the business modules; screenshots are added as
pages are built.
