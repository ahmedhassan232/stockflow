"""Permission catalogue (code side). Must equal the `permissions` table – see
tests/test_rbac.py::test_permission_catalogue_matches_database. Add new codes here AND in
a new migration."""

PERMISSIONS: dict[str, str] = {
    "settings.view": "View company settings",
    "settings.update": "Update company settings",
    "branches.view": "View branches",
    "branches.manage": "Create and update branches",
    "warehouses.view": "View warehouses",
    "warehouses.manage": "Create and update warehouses",
    "employees.view": "View employees",
    "employees.manage": "Invite, update and remove employees",
    "roles.manage": "Manage roles and their permissions",
    "products.view": "View products",
    "products.create": "Create products",
    "products.update": "Update products",
    "products.delete": "Deactivate products",
    "categories.manage": "Manage categories and units",
    "inventory.view": "View stock and movements",
    "inventory.adjust": "Adjust stock",
    "inventory.transfer": "Transfer stock between warehouses",
    "suppliers.view": "View suppliers",
    "suppliers.manage": "Manage suppliers",
    "purchases.view": "View purchases",
    "purchases.create": "Create purchases",
    "purchases.receive": "Receive goods",
    "purchases.cancel": "Cancel purchases",
    "customers.view": "View customers",
    "customers.manage": "Manage customers",
    "sales.view": "View sales",
    "sales.create": "Create and post sales",
    "sales.cancel": "Cancel sales",
    "sales.return": "Process sales returns",
    "payments.view": "View payments",
    "payments.manage": "Record payments",
    "expenses.view": "View expenses",
    "expenses.manage": "Manage expenses",
    "reports.sales.view": "View sales reports",
    "reports.inventory.view": "View inventory reports",
    "reports.financial.view": "View financial reports",
}

ALL_PERMISSIONS: frozenset[str] = frozenset(PERMISSIONS)


def _all_except(*excluded: str) -> frozenset[str]:
    return ALL_PERMISSIONS - set(excluded)


# The system `owner` role is not listed: it implicitly holds every permission.
DEFAULT_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": _all_except("roles.manage", "settings.update"),
    "branch_manager": frozenset(
        {
            "branches.view",
            "warehouses.view",
            "employees.view",
            "products.view",
            "inventory.view",
            "inventory.adjust",
            "inventory.transfer",
            "suppliers.view",
            "purchases.view",
            "purchases.create",
            "purchases.receive",
            "customers.view",
            "customers.manage",
            "sales.view",
            "sales.create",
            "sales.cancel",
            "sales.return",
            "payments.view",
            "payments.manage",
            "expenses.view",
            "expenses.manage",
            "reports.sales.view",
            "reports.inventory.view",
        }
    ),
    "inventory_manager": frozenset(
        {
            "branches.view",
            "warehouses.view",
            "products.view",
            "products.create",
            "products.update",
            "products.delete",
            "categories.manage",
            "inventory.view",
            "inventory.adjust",
            "inventory.transfer",
            "reports.inventory.view",
        }
    ),
    "sales_cashier": frozenset(
        {
            "branches.view",
            "warehouses.view",
            "products.view",
            "inventory.view",
            "customers.view",
            "customers.manage",
            "sales.view",
            "sales.create",
            "sales.return",
            "payments.view",
            "payments.manage",
        }
    ),
    "purchase_manager": frozenset(
        {
            "branches.view",
            "warehouses.view",
            "products.view",
            "inventory.view",
            "suppliers.view",
            "suppliers.manage",
            "purchases.view",
            "purchases.create",
            "purchases.receive",
            "purchases.cancel",
        }
    ),
    "accountant": frozenset(
        {
            "branches.view",
            "sales.view",
            "purchases.view",
            "customers.view",
            "suppliers.view",
            "payments.view",
            "payments.manage",
            "expenses.view",
            "expenses.manage",
            "reports.sales.view",
            "reports.financial.view",
        }
    ),
    "warehouse_employee": frozenset(
        {
            "branches.view",
            "warehouses.view",
            "products.view",
            "inventory.view",
            "inventory.transfer",
            "purchases.view",
            "purchases.receive",
        }
    ),
}
