# Security

## Authentication

| Topic | Implementation |
|---|---|
| Passwords | Argon2id (`argon2-cffi`), hashed off the event loop; minimum 10 characters; transparent re-hash when parameters change |
| Access token | JWT HS256, 15 minutes, claims `sub` (user), `sid` (session), `tid` (selected company). Algorithm pinned, issuer and type checked. Kept **in memory only** by the frontend |
| Refresh token | Opaque random value in an `HttpOnly` cookie scoped to `/api/v1/auth`; only its SHA-256 hash is stored; **single use** (rotated on every refresh) |
| Token theft | Replaying a rotated-out refresh token revokes the whole session (`TOKEN_REUSED`). A 10-second grace window answers `REFRESH_RACE` instead, so two tabs refreshing together are not treated as theft |
| Session revocation | Every request loads the session row: logout, password change/reset, or "sign out other devices" take effect immediately, even for unexpired access tokens |
| CSRF | Business endpoints use the `Authorization` header (not ambient cookies). The two cookie endpoints (`/refresh`, `/logout`) require `Origin` to equal the request host or an allowlisted origin |
| Brute force | 5 failed logins per e-mail → locked for 15 minutes (`LOGIN_LOCKED`); plus a per-IP limit on all unauthenticated auth endpoints. Counters live in Redis and the limiter **fails closed** (503) if Redis is down |
| Enumeration | Unknown e-mail, wrong password and disabled account return the identical 401; a dummy hash is verified for unknown users; forgot-password always returns the same 200 |
| Password reset | Single-use, 30-minute, hashed token e-mailed as a link; success signs the user out everywhere |

Known trade-offs: the per-e-mail lockout lets an attacker temporarily lock a known account
(chosen over unlimited guessing); registration reveals that an e-mail is taken (`409`).

## Authorization

1. The access token only says *which company was selected*. On every tenant request the backend
   re-reads the membership, role, company status and permissions (`load_tenant_access`), so a
   revoked membership, suspended company or edited role applies to existing tokens at once.
2. `POST /auth/select-company` accepts a company id only as a request; it is honoured solely if an
   active membership in an active company exists. No endpoint accepts `tenant_id` in a body, query
   or header (`extra="forbid"` schemas reject it).
3. Permissions are granular codes (`branches.manage`, `sales.create`, …) checked by
   `require_permission(...)` on every protected route. The system `owner` role holds all of them;
   other default roles are seeded per company in `authorization/permissions.py`.
4. Branch restriction: a restricted member only sees/changes assigned branches and their
   warehouses; other branches answer **404** (existence is not disclosed) and company-wide actions
   answer 403 `BRANCH_SCOPE_REQUIRED`.
5. Hiding buttons in the UI is convenience only — the same checks are enforced by the API and, for
   tenant boundaries, again by PostgreSQL RLS (see [tenant-isolation.md](tenant-isolation.md)).

## Other controls

* Explicit CORS allowlist (wildcard rejected in production); production refuses to start with a
  placeholder JWT secret or a non-`Secure` refresh cookie.
* Request schemas forbid unknown fields (mass-assignment protection); response models never
  include password hashes or token hashes.
* Errors use a fixed envelope; unhandled exceptions are logged with a request id and returned as a
  generic `INTERNAL_ERROR`.
* `LIKE` wildcards in search terms are escaped; all SQL is parameterised.

## PDF generation

PDFs are rendered on the server with WeasyPrint from HTML built in `app/modules/reports/pdf.py`.
Every dynamic value is HTML-escaped (`e()`), and the renderer's URL fetcher refuses every
URL, so user text can neither inject markup nor make the server fetch a file or a network
address. PDF routes use the same permissions as the screens they mirror.

## Platform action log

Suspending or reactivating a company writes a row to `platform_audit_logs` inside the same
database function and transaction. The application role cannot read, insert, change or
delete rows directly; reading goes through a function that re-checks the caller.

## Not implemented yet

File-upload validation (there are no uploads), 2FA. E-mail verification exists but is not
mandatory: unverified users see a banner and do not receive the digest.
