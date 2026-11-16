# Deployment guide

> Status: the application was developed and tested natively (PostgreSQL 17, Redis 7).
> The Docker Compose files are syntactically valid but **have not been run end-to-end**.
> Do a full rehearsal on a staging server before going live.

## 1. Server
- Linux host with Docker Engine + Compose plugin, 2 vCPU / 4 GB RAM minimum.
- A domain name pointing at the server; ports 80 and 443 open.

## 2. Configuration
```bash
cp .env.example .env
```
Change every `change-me` value. Required for production:

| Variable | Notes |
|---|---|
| `APP_ENV=production` | disables API docs, forces Secure cookies, validates secrets at start-up |
| `JWT_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `POSTGRES_PASSWORD`, `DB_OWNER_PASSWORD`, `DB_APP_PASSWORD` | three different strong passwords |
| `DATABASE_URL` | must use the **runtime** role (`stockflow_app`) — it has no BYPASSRLS |
| `MIGRATION_DATABASE_URL` | the owner role; used only by Alembic |
| `FRONTEND_URL`, `CORS_ORIGINS` | `https://your-domain` |
| `SMTP_*` | a real mail provider (password reset and employee invitations) |

Never run the API with the owner role: tenant isolation depends on the runtime role
being subject to row-level security.

## 3. TLS
Put certificates in `./certs/`, uncomment the certs volume of the nginx service in `docker-compose.prod.yml`, and enable the commented 443 server
block in `infrastructure/nginx/prod.conf` (or terminate TLS at a load balancer that sets
`X-Forwarded-Proto`). The refresh cookie is `Secure`, so login does not work over plain HTTP.

## 4. Start
```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
curl -f https://your-domain/api/v1/health/ready
```
Services: nginx, backend (uvicorn), celery-worker, celery-beat (exactly ONE instance),
postgres, redis.

## 5. Upgrades
1. Back up the database. 2. Pull and build the new images. 3. `alembic upgrade head`.
4. Restart backend, worker and beat. Migrations are forward-compatible within a release.

## 6. Backups
- Nightly `pg_dump -Fc` plus WAL archiving if you need point-in-time recovery.
- Test a restore regularly. Redis holds only rate limits, task queue and caches.

## 7. Monitoring
- `/api/v1/health/live` (process) and `/api/v1/health/ready` (database, Redis, migrations).
- Logs are JSON on stdout with a request id; ship them to your log system.
- Alert on 5xx rate, readiness failures and a missing Celery heartbeat.

## 8. Before going live — checklist
- [ ] Staging rehearsal of this guide, including a restore from backup
- [ ] Real SMTP tested (reset password + invitation)
- [ ] `APP_ENV=production` and no default secrets (the app refuses to start otherwise)
- [ ] Database port not exposed publicly
- [ ] Demo seed NOT run in production

## Frontend on Vercel (optional)

Vercel can host **only the React frontend**. The API, PostgreSQL, Redis and the Celery
worker/beat need a host that runs long-lived containers (a VPS with
`docker-compose.prod.yml`, Fly.io, Render, Railway…).

1. Deploy the backend first and note its HTTPS host.
2. In `frontend/vercel.json` replace `REPLACE-WITH-YOUR-API-HOST` with that host. The
   rewrite makes the browser call `/api/...` on the Vercel domain, so the refresh cookie
   stays first-party and no CORS setup is needed.
3. On the backend set `FRONTEND_URL` (and the allowed origins) to the Vercel domain;
   otherwise refresh/logout are rejected with `CSRF_REJECTED`.
4. Create the Vercel project with **Root Directory = `frontend`**.

## Verified locally (2026-11-14)

- Celery worker + beat as real processes against Redis: `system.heartbeat` fired by beat,
  `inventory.low_stock_scan`, `inventory.low_stock_digest` and `email.send` executed.
- SMTP against a local test server (`python -m aiosmtpd -n -l 127.0.0.1:1025`,
  `SMTP_HOST=127.0.0.1`): verification mail delivered, its token confirmed the address,
  the digest mail was delivered once and skipped on the second run the same day.
- Not verified: the Docker images/compose stack (no Docker in the build environment),
  SMTP with STARTTLS + login (`SMTP_STARTTLS=true`, `SMTP_USERNAME`, `SMTP_PASSWORD`) —
  implemented, but not tried against a real provider.
