"""Phase 7-10: suppliers, customers, purchasing, sales, payments, notifications, audit log.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14 20:45:37.568565
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_audit_logs_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_audit_logs_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_audit_logs_tenant_id_id")),
    )
    op.create_index(
        "ix_audit_logs_tenant_id_created_at",
        "audit_logs",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "customers",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("tax_number", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_customers_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_customers_tenant_id_id")),
    )
    op.create_index("ix_customers_tenant_id_name", "customers", ["tenant_id", "name"], unique=False)
    op.create_index(
        "ix_customers_tenant_id_phone", "customers", ["tenant_id", "phone"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("required_permission", sa.String(length=60), nullable=True),
        sa.Column("dedupe_key", sa.String(length=120), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_notifications_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "tenant_id", "dedupe_key", name=op.f("uq_notifications_tenant_id_dedupe_key")
        ),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_notifications_tenant_id_id")),
    )
    op.create_index(
        "ix_notifications_tenant_id_created_at",
        "notifications",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "suppliers",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("tax_number", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_suppliers_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_suppliers_tenant_id_id")),
    )
    op.create_index("ix_suppliers_tenant_id_name", "suppliers", ["tenant_id", "name"], unique=False)
    op.create_table(
        "purchase_orders",
        sa.Column("number", sa.String(length=30), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column(
            "subtotal", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "tax_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("total", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column(
            "paid_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft','ordered','partially_received','received','cancelled')",
            name=op.f("ck_purchase_orders_status_valid"),
        ),
        sa.CheckConstraint(
            "paid_amount >= 0 AND paid_amount <= total",
            name=op.f("ck_purchase_orders_paid_within_total"),
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND tax_amount >= 0 AND total >= 0",
            name=op.f("ck_purchase_orders_amounts_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_purchase_orders_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            name=op.f("fk_purchase_orders_tenant_id_supplier_id_suppliers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name=op.f("fk_purchase_orders_tenant_id_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_purchase_orders_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_orders")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_purchase_orders_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "number", name=op.f("uq_purchase_orders_tenant_id_number")
        ),
    )
    op.create_index(
        "ix_purchase_orders_tenant_id_created_at",
        "purchase_orders",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_purchase_orders_tenant_id_supplier_id",
        "purchase_orders",
        ["tenant_id", "supplier_id"],
        unique=False,
    )
    op.create_table(
        "sales",
        sa.Column("number", sa.String(length=30), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="completed", nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "discount_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "tax_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "cost_total", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "paid_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "returned_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('completed','cancelled')", name=op.f("ck_sales_status_valid")
        ),
        sa.CheckConstraint(
            "paid_amount >= 0 AND paid_amount <= total", name=op.f("ck_sales_paid_within_total")
        ),
        sa.CheckConstraint(
            "returned_amount >= 0 AND returned_amount <= total",
            name=op.f("ck_sales_returned_valid"),
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND total >= 0",
            name=op.f("ck_sales_amounts_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_sales_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name=op.f("fk_sales_tenant_id_customer_id_customers"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name=op.f("fk_sales_tenant_id_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_sales_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sales")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_sales_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "number", name=op.f("uq_sales_tenant_id_number")),
    )
    op.create_index(
        "ix_sales_tenant_id_created_at", "sales", ["tenant_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_sales_tenant_id_customer_id", "sales", ["tenant_id", "customer_id"], unique=False
    )
    op.create_table(
        "payments",
        sa.Column("direction", sa.String(length=3), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("direction IN ('in','out')", name=op.f("ck_payments_direction_valid")),
        sa.CheckConstraint(
            "method IN ('cash','card','bank_transfer','wallet')",
            name=op.f("ck_payments_method_valid"),
        ),
        sa.CheckConstraint(
            "(sale_id IS NOT NULL) <> (purchase_order_id IS NOT NULL)",
            name=op.f("ck_payments_exactly_one_document"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount_positive")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_payments_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            name=op.f("fk_payments_tenant_id_purchase_order_id_purchase_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sale_id"],
            ["sales.tenant_id", "sales.id"],
            name=op.f("fk_payments_tenant_id_sale_id_sales"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_payments_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_payments_tenant_id_id")),
    )
    op.create_index(
        "ix_payments_tenant_id_created_at", "payments", ["tenant_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_payments_tenant_id_sale_id", "payments", ["tenant_id", "sale_id"], unique=False
    )
    op.create_table(
        "purchase_order_items",
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), server_default="0", nullable=False),
        sa.Column(
            "tax_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("line_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "received_quantity",
            sa.Numeric(precision=14, scale=3),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "returned_quantity",
            sa.Numeric(precision=14, scale=3),
            server_default="0",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_purchase_order_items_quantity_positive")),
        sa.CheckConstraint(
            "received_quantity >= 0 AND received_quantity <= quantity",
            name=op.f("ck_purchase_order_items_received_within_ordered"),
        ),
        sa.CheckConstraint(
            "returned_quantity >= 0 AND returned_quantity <= received_quantity",
            name=op.f("ck_purchase_order_items_returned_within_received"),
        ),
        sa.CheckConstraint(
            "unit_cost >= 0", name=op.f("ck_purchase_order_items_unit_cost_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_purchase_order_items_tenant_id_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            name=op.f("fk_purchase_order_items_tenant_id_purchase_order_id_purchase_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_purchase_order_items_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_order_items")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_purchase_order_items_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "purchase_order_id",
            "line_no",
            name=op.f("uq_purchase_order_items_tenant_id_purchase_order_id_line_no"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "purchase_order_id",
            "product_id",
            name=op.f("uq_purchase_order_items_tenant_id_purchase_order_id_product_id"),
        ),
    )
    op.create_table(
        "purchase_receipts",
        sa.Column("number", sa.String(length=30), nullable=False),
        sa.Column("kind", sa.String(length=10), server_default="receipt", nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('receipt','return')", name=op.f("ck_purchase_receipts_kind_valid")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_purchase_receipts_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_id"],
            ["purchase_orders.tenant_id", "purchase_orders.id"],
            name=op.f("fk_purchase_receipts_tenant_id_purchase_order_id_purchase_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name=op.f("fk_purchase_receipts_tenant_id_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_purchase_receipts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_receipts")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_purchase_receipts_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "number", name=op.f("uq_purchase_receipts_tenant_id_number")
        ),
    )
    op.create_table(
        "sale_items",
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "discount_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), server_default="0", nullable=False),
        sa.Column(
            "tax_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("line_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("unit_cost_at_sale", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column(
            "returned_quantity",
            sa.Numeric(precision=14, scale=3),
            server_default="0",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_sale_items_quantity_positive")),
        sa.CheckConstraint(
            "returned_quantity >= 0 AND returned_quantity <= quantity",
            name=op.f("ck_sale_items_returned_within_sold"),
        ),
        sa.CheckConstraint("unit_cost_at_sale >= 0", name=op.f("ck_sale_items_cost_non_negative")),
        sa.CheckConstraint(
            "unit_price >= 0 AND discount_amount >= 0", name=op.f("ck_sale_items_price_valid")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_sale_items_tenant_id_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sale_id"],
            ["sales.tenant_id", "sales.id"],
            name=op.f("fk_sale_items_tenant_id_sale_id_sales"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_sale_items_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_items")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_sale_items_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id", "sale_id", "line_no", name=op.f("uq_sale_items_tenant_id_sale_id_line_no")
        ),
    )
    op.create_index(
        "ix_sale_items_tenant_id_product_id",
        "sale_items",
        ["tenant_id", "product_id"],
        unique=False,
    )
    op.create_table(
        "sale_returns",
        sa.Column("number", sa.String(length=30), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "cost_total", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "refund_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "total >= 0 AND refund_amount >= 0", name=op.f("ck_sale_returns_amounts_valid")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_sale_returns_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sale_id"],
            ["sales.tenant_id", "sales.id"],
            name=op.f("fk_sale_returns_tenant_id_sale_id_sales"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_sale_returns_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_returns")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_sale_returns_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "number", name=op.f("uq_sale_returns_tenant_id_number")),
    )
    op.create_index(
        "ix_sale_returns_tenant_id_created_at",
        "sale_returns",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "purchase_receipt_items",
        sa.Column("purchase_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("purchase_order_item_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_purchase_receipt_items_quantity_positive")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_purchase_receipt_items_tenant_id_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_order_item_id"],
            ["purchase_order_items.tenant_id", "purchase_order_items.id"],
            name=op.f(
                "fk_purchase_receipt_items_tenant_id_purchase_order_item_id_purchase_order_items"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "purchase_receipt_id"],
            ["purchase_receipts.tenant_id", "purchase_receipts.id"],
            name=op.f("fk_purchase_receipt_items_tenant_id_purchase_receipt_id_purchase_receipts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_purchase_receipt_items_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_receipt_items")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_purchase_receipt_items_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "purchase_receipt_id",
            "line_no",
            name=op.f("uq_purchase_receipt_items_tenant_id_purchase_receipt_id_line_no"),
        ),
    )
    op.create_table(
        "sale_return_items",
        sa.Column("sale_return_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("sale_item_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_sale_return_items_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_sale_return_items_tenant_id_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sale_item_id"],
            ["sale_items.tenant_id", "sale_items.id"],
            name=op.f("fk_sale_return_items_tenant_id_sale_item_id_sale_items"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "sale_return_id"],
            ["sale_returns.tenant_id", "sale_returns.id"],
            name=op.f("fk_sale_return_items_tenant_id_sale_return_id_sale_returns"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_sale_return_items_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_return_items")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_sale_return_items_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "sale_return_id",
            "line_no",
            name=op.f("uq_sale_return_items_tenant_id_sale_return_id_line_no"),
        ),
    )

    for table in ("suppliers", "customers", "purchase_orders", "sales"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    for table in (
        "suppliers",
        "customers",
        "purchase_orders",
        "purchase_order_items",
        "purchase_receipts",
        "purchase_receipt_items",
        "sales",
        "sale_items",
        "sale_returns",
        "sale_return_items",
        "payments",
        "notifications",
        "audit_logs",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = app_current_tenant_id()) "
            f"WITH CHECK (tenant_id = app_current_tenant_id())"
        )

    # Posted documents and logs are append-only for the application role.
    role = get_settings().db_app_user
    for table in (
        "purchase_receipts",
        "purchase_receipt_items",
        "sale_returns",
        "sale_return_items",
        "payments",
        "audit_logs",
    ):
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM {role}")
    op.execute(f"REVOKE DELETE ON sales, sale_items, purchase_orders FROM {role}")


def downgrade() -> None:
    op.drop_table("sale_return_items")
    op.drop_table("purchase_receipt_items")
    op.drop_index("ix_sale_returns_tenant_id_created_at", table_name="sale_returns")
    op.drop_table("sale_returns")
    op.drop_index("ix_sale_items_tenant_id_product_id", table_name="sale_items")
    op.drop_table("sale_items")
    op.drop_table("purchase_receipts")
    op.drop_table("purchase_order_items")
    op.drop_index("ix_payments_tenant_id_sale_id", table_name="payments")
    op.drop_index("ix_payments_tenant_id_created_at", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_sales_tenant_id_customer_id", table_name="sales")
    op.drop_index("ix_sales_tenant_id_created_at", table_name="sales")
    op.drop_table("sales")
    op.drop_index("ix_purchase_orders_tenant_id_supplier_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_tenant_id_created_at", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_index("ix_suppliers_tenant_id_name", table_name="suppliers")
    op.drop_table("suppliers")
    op.drop_index("ix_notifications_tenant_id_created_at", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_customers_tenant_id_phone", table_name="customers")
    op.drop_index("ix_customers_tenant_id_name", table_name="customers")
    op.drop_table("customers")
    op.drop_index("ix_audit_logs_tenant_id_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
