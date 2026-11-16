"""Default roles copied into every new company. Permissions are attached in Phase 3."""

OWNER_ROLE_CODE = "owner"

# (code, English name, Arabic name)
DEFAULT_ROLES: tuple[tuple[str, str, str], ...] = (
    (OWNER_ROLE_CODE, "Company Owner", "مالك الشركة"),
    ("admin", "Company Admin", "مدير الشركة"),
    ("branch_manager", "Branch Manager", "مدير فرع"),
    ("inventory_manager", "Inventory Manager", "مدير المخزون"),
    ("sales_cashier", "Sales Cashier", "كاشير مبيعات"),
    ("purchase_manager", "Purchase Manager", "مدير المشتريات"),
    ("accountant", "Accountant", "محاسب"),
    ("warehouse_employee", "Warehouse Employee", "موظف مخزن"),
)
