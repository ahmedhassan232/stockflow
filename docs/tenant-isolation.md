# Tenant isolation

Company A must never read, change, delete or reference Company B's data — even if application
code has a bug. Isolation is therefore enforced in independent layers; each one is tested.

| # | Layer | Where | What it guarantees |
|---|---|---|---|
| 1 | Tenant context | `app/db/tenant.py` | `app.tenant_id` / `app.user_id` are set per **transaction** (`set_config(..., true)`) from server-side identity only |
| 2 | Repository | `app/db/repository.py` | every query filtered by `tenant_id`; inserts stamped with the repository's tenant; `tenant_id`/`id` immutable |
| 3 | Row Level Security | migration `0002` | `ENABLE` + `FORCE` RLS, policy `tenant_id = app_current_tenant_id()` for `USING` and `WITH CHECK`; no context ⇒ no rows |
| 4 | Composite foreign keys | migration `0002` | `(tenant_id, x_id) → x(tenant_id, id)`: a row cannot point at another company's row |
| 5 | Database roles | `10-init-roles.sh` | runtime role is `NOSUPERUSER NOBYPASSRLS`, owns no tables, cannot `ALTER`/`DROP POLICY`/`TRUNCATE` |

## Rules for the two special tables

* **`tenants`** – readable by its own context and by users who hold a membership in it (company
  chooser). Insert only when `id` equals the context (the provisioning service generates the id
  server-side). No delete policy: the API role cannot delete a company.
* **`memberships`** – normal tenant policy, plus read-only access to **your own** rows via
  `app_current_user_id()`. This does not expose any business table.
* **`users`** – global identity table without `tenant_id` (one person, many companies). It has no
  RLS; only auth/user repositories may query it and tenant endpoints never list it directly.

## Why the pool cannot leak

The context is transaction-local. `COMMIT`/`ROLLBACK` resets it, so the next request that borrows
the same physical connection starts with no tenant and sees nothing.
`test_pooled_connection_does_not_leak_tenant_context` forces a single connection and proves this
after both commit and rollback.

## Duplicate company identifiers

Other companies are invisible under RLS, so a "does this slug exist?" query cannot work — and would
be racy anyway. The unique constraint is the source of truth: the insert runs in a savepoint and an
integrity error becomes `409 CONFLICT`.

## Adding a new tenant-owned table (checklist)

1. Model inherits `TenantOwnedMixin`, declares `UniqueConstraint("tenant_id", "id")` and composite
   `ForeignKeyConstraint`s to other tenant tables; register it in `app/db/models.py`.
2. Migration: add the table to the RLS loop (enable, force, `tenant_isolation` policy) and the
   `set_updated_at` trigger.
3. Repository subclasses `TenantRepository`.

`tests/test_schema_guards.py` fails the build if a table has no `tenant_id` (and is not on the
explicit global list), lacks forced RLS / policy / `UNIQUE (tenant_id, id)`, uses a non-composite FK
to a tenant table, or if models and migrations drift apart.

## Not yet covered (later phases)

* HTTP-level tests (403/404 across tenants) arrive with authentication in Phase 3 — there are
  deliberately **no tenant data endpoints yet**, because they would be unauthenticated.
* Platform super-admin access (explicit, audited) is Phase 19 of the brief; nothing bypasses RLS today.
