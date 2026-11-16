# Architecture

## Overview

StockFlow is a **modular monolith**: one FastAPI application, one PostgreSQL database,
split into business modules with strict internal layering. It can be deployed as a single
unit today and modules can be extracted later because they only talk through services.

```
Browser (React SPA, Arabic RTL first)
   │  same-origin /api/v1/*           (no CORS needed, no backend host in client code)
   ▼
Nginx ── /        → frontend (Vite dev server | static build)
      └─ /api/    → FastAPI (uvicorn)
                      ├── PostgreSQL 17  (runtime role: NOSUPERUSER, NOBYPASSRLS)
                      ├── Redis          (cache, rate limits, Celery broker)
                      └── Celery worker + beat (non-atomic background work only)
```

## Backend layering

```
app/
  main.py              application factory, middleware, exception handlers
  core/                config, logging, response envelope, errors, redis
  db/                  declarative Base (naming convention), engine, request session
  middleware/          request id + security headers
  api/v1/router.py     the only place module routers are mounted
  modules/<name>/      router.py → service.py → repository.py, + models.py, schemas.py, permissions.py
  tasks/               Celery app and tasks
```

| Layer | Responsibility | Must not |
|---|---|---|
| `router.py` | HTTP mapping, validation, dependencies (auth, tenant, permission) | contain business rules or SQL |
| `service.py` | business rules, transactions, money/stock arithmetic (`Decimal`) | know about HTTP |
| `repository.py` | tenant-scoped queries, row locking | make authorization decisions |
| `models.py` / `schemas.py` | persistence shape / API contract (kept separate → no mass assignment) | — |

Phase 1 ships one module, `health`, built in exactly this shape so later modules copy it.

## Cross-cutting decisions

| Topic | Decision |
|---|---|
| API contract | `/api/v1`, envelope `{success, data, message}` / `{success:false, error:{code,message,details}}`; unhandled errors are logged with a request id and returned as a generic `INTERNAL_ERROR` |
| DB driver | psycopg 3 for both the async app engine and sync Alembic (one driver) |
| DB roles | `stockflow_owner` owns the schema and runs migrations; `stockflow_app` is the runtime role with DML only. `/health/ready` reports whether the runtime role could bypass RLS and **fails in production** if it can |
| Tenant context | transaction-local GUC `app.tenant_id` set with `set_config(..., true)`, read by `app_current_tenant_id()`. It is discarded at COMMIT/ROLLBACK, so pooled connections cannot leak it (covered by a test) |
| Sessions | one session + one transaction per request (`get_db`): commit on success, rollback on error |
| Background work | Celery only for work that may happen after commit. Stock/financial writes are never deferred |
| Frontend | feature folders, TanStack Query for server state, Axios instance with error normalisation, i18next with `<html lang dir>` kept in sync, design tokens as CSS variables (light/dark) |
| Docs | Swagger at `/api/v1/docs` in non-production; disabled and blocked at nginx in production |

## Deviations from the brief (and why)

* **SQLAlchemy 2.1.x** is pinned (the current stable line of the "2.0-style" API).
* Dockerfiles live in `infrastructure/docker/` as `Dockerfile.backend` / `Dockerfile.frontend`
  (the brief lists both this naming and `backend/Dockerfile`; one location was chosen).
* Dependencies are added in the phase that first uses them (e.g. PyJWT/argon2-cffi in Phase 3,
  Recharts/React Hook Form/Zod when the first form/chart lands) to avoid unused packages.
