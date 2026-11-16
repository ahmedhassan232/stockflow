# Database design

Status: revisions `0001` (foundation), `0002` (multi-tenant core) and `0003` (auth + RBAC) are implemented. The rest of
the design below is the agreed target for later phases.

## Implemented in `0001`

| Object | Purpose |
|---|---|
| extensions `citext`, `pg_trgm` | case-insensitive e-mail; trigram search on product name / SKU / barcode |
| `app_current_tenant_id() → uuid` | reads transaction-local `app.tenant_id`; `NULL` when unset ⇒ RLS denies by default |
| `set_updated_at()` | trigger function for `updated_at` |
| default privileges | future tables/sequences get `SELECT/INSERT/UPDATE/DELETE` for `stockflow_app` — never DDL, never ownership |

## Implemented in `0002`

| Table | Tenant-owned | Notable constraints |
|---|---|---|
| `tenants` | is the tenant | `slug citext UNIQUE` + format check, `status IN (active, suspended)`, ISO-4217 currency check, defaults `EGP` / `Africa/Cairo`; RLS select/insert/update policies, no delete |
| `users` | no (global) | `email citext UNIQUE`; `password_hash` nullable until set |
| `roles` | yes | `UNIQUE(tenant_id, code)`; 8 default roles copied into each company (`is_system`) |
| `memberships` | yes | `UNIQUE(tenant_id, user_id)`; FK `(tenant_id, role_id) → roles`; status check; extra policy: a user reads their own rows |
| `branches` | yes | `UNIQUE(tenant_id, code)`; FK `(tenant_id, manager_membership_id) → memberships` |
| `warehouses` | yes | `UNIQUE(tenant_id, code)`; FK `(tenant_id, branch_id) → branches` |

Also: `app_current_user_id()`, `set_updated_at` triggers on all six tables. Differences from the
brief: roles are always tenant-owned (system roles are copied per company, so composite FKs apply);
a branch manager is a **membership** (`manager_membership_id`), not a bare user id.
Details: [tenant-isolation.md](tenant-isolation.md).

## Implemented in `0003`

| Table | Tenant-owned | Notes |
|---|---|---|
| `auth_sessions` | no (global) | one per signed-in device; `active_tenant_id`, `expires_at`, `revoked_at`, `revoked_reason` |
| `refresh_tokens` | no | `token_hash` (SHA-256) unique, single use, belongs to a session |
| `password_reset_tokens` | no | `token_hash`, `expires_at`, `used_at` |
| `permissions` | no | read-only catalogue (`code` PK); runtime role has SELECT only |
| `role_permissions` | yes | `UNIQUE(tenant_id, role_id, permission_code)`; composite FK to `roles` |
| `membership_branches` | yes | composite FKs to `memberships` and `branches` |

`memberships.restricted_to_branches` (bool): false = all branches; true = only rows in
`membership_branches` (none listed ⇒ no branch).

## Implemented in `0004`

Company settings and document counters, idempotency keys, categories, units, products,
stock balances (one row per warehouse + product, `quantity`, `minimum_stock_level`),
stock movements (append-only ledger), stock adjustments and stock transfers with lines.

## Implemented in `0005`

Suppliers, customers, purchase orders + items, purchase receipts + items, sales + items,
sale returns + items, payments, notifications, audit logs. Receipts, returns, payments,
stock movements and audit logs are append-only: the runtime role has no UPDATE/DELETE
privilege on them, so history cannot be rewritten even by a bug.

## Implemented in `0006`

`app_active_tenant_ids()` — a SECURITY DEFINER function returning only the ids of active
companies, for scheduled jobs that have no user. Jobs then enter each company's tenant
context and work under the normal RLS policies.

## Implemented in `0007`

`expenses` (tenant-owned, RLS; amount/date fixed once recorded, corrected by voiding),
`password_reset_tokens.purpose` (`password_reset` | `verify_email`),
`users.is_platform_admin` guarded by a trigger (only the owner role may grant it), and
the platform functions `platform_list_tenants()` / `platform_set_tenant_status()`, which
re-check inside PostgreSQL that the current user is a platform administrator.

## Implemented in `0008`

- `platform_audit_logs` (global, no tenant): `actor_user_id`, `action`
  (`company.suspended` / `company.activated`), `target_company_id`, `target_company_name`
  (copied, so the entry stays readable), `created_at`. The runtime role has **no**
  privileges on it. `platform_set_tenant_status()` inserts the row in the same transaction
  as the status change; `platform_audit_entries(limit)` returns rows to platform admins only.

## Conventions for every table

* `id uuid PRIMARY KEY DEFAULT gen_random_uuid()`; `created_at/updated_at timestamptz`.
* Money `numeric(14,2)`, unit cost `numeric(14,4)`, quantity `numeric(14,3)`, rates `numeric(5,2)`. No floats.
* Statuses are `text` + `CHECK` (easier to evolve than enums).
* Constraint names come from the naming convention in `app/db/base.py`.

## Tenant isolation pattern (applied to every tenant-owned table)

```sql
tenant_id uuid NOT NULL REFERENCES tenants(id),
UNIQUE (tenant_id, id),                              -- target for composite FKs
FOREIGN KEY (tenant_id, warehouse_id)
    REFERENCES warehouses (tenant_id, id),           -- a row can only reference its own tenant

ALTER TABLE t ENABLE ROW LEVEL SECURITY;
ALTER TABLE t FORCE  ROW LEVEL SECURITY;             -- applies to the table owner too
CREATE POLICY tenant_isolation ON t
    USING      (tenant_id = app_current_tenant_id())
    WITH CHECK (tenant_id = app_current_tenant_id());
```

Unique keys are tenant-aware: `UNIQUE (tenant_id, sku)`, `UNIQUE (tenant_id, invoice_number)`, …

## Tables by group

| Group | Tables | Key rules |
|---|---|---|
| Platform (no RLS, platform routes only) | `tenants`, `subscription_plans`, `tenant_subscriptions`, `platform_admins` | `tenants.slug` unique; status `active/suspended` |
| Identity (global) | `users`, `refresh_tokens`, `password_reset_tokens` | `users.email citext UNIQUE`; only token **hashes** stored; rotation via `revoked_at` |
| Authorization | `permissions` (global catalogue), `roles` (system when `tenant_id IS NULL`, else tenant-defined), `role_permissions`, `memberships` `UNIQUE(tenant_id,user_id)`, `membership_branches` | permission codes like `sales.create` |
| Organization | `branches`, `warehouses`, `company_settings`, `invoice_sequences` | `UNIQUE(tenant_id, code)`; sequences locked `FOR UPDATE` when numbering |
| Catalog | `categories` (self-FK), `units`, `products` | `UNIQUE(tenant_id, sku)`, partial unique on barcode; `CHECK price >= 0`; GIN trigram index on name |
| Inventory | `stock_balances` `UNIQUE(tenant_id, warehouse_id, product_id)`, `inventory_movements` (append-only), `stock_transfers` | `CHECK quantity >= 0` unless tenant allows negative stock; movements: exactly one of `quantity_in/out` > 0; `UNIQUE(tenant_id, reference_type, reference_id, product_id, warehouse_id, movement_type)` blocks duplicates; UPDATE/DELETE revoked on the ledger |
| Parties | `suppliers`, `customers` | soft-deactivation only |
| Purchasing | `purchases`, `purchase_items`, `purchase_receipts`, `purchase_receipt_items` | `CHECK received_quantity <= ordered_quantity` |
| Sales | `sales`, `sale_items` (`unit_cost_at_sale`, `line_profit`), `sales_returns`, `sales_return_items` | posted documents are immutable; returns bounded by remaining returnable quantity |
| Finance | `payments`, `expense_categories`, `expenses` | `CHECK amount > 0`; `paid_amount <= total_amount` |
| Support | `notifications`, `notification_preferences`, `audit_logs`, `file_uploads`, `idempotency_keys` `UNIQUE(tenant_id, key, operation)` | audit log append-only |

## Costing and reporting definitions

* **Weighted average cost** on each accepted receipt:
  `new_avg = (on_hand_qty × old_avg + received_qty × receipt_unit_cost) / (on_hand_qty + received_qty)`
  where `on_hand_qty` is the tenant-wide quantity of the product (floored at 0).
* A sale copies the current average into `sale_items.unit_cost_at_sale`; returns reverse at that
  historical cost, so past profit never changes when purchase prices change.
* Revenue = net sales after discounts and returns, excluding tax. COGS = cost of items sold less
  returns. Gross profit = Revenue − COGS. Operating profit = Gross profit − expenses.
  Cash received is reported separately from revenue. Gross profit is never labelled net profit.
