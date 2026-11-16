"""Company settings, catalog (categories, units, products) and inventory ledger.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14 20:37:56.144679
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_categories_not_own_parent")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["categories.tenant_id", "categories.id"],
            name=op.f("fk_categories_tenant_id_parent_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_categories_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_categories_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_categories_tenant_id_name")),
    )
    op.create_table(
        "company_settings",
        sa.Column("tax_number", sa.String(length=50), nullable=True),
        sa.Column(
            "default_tax_rate", sa.Numeric(precision=5, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "allow_negative_stock", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("invoice_footer", sa.Text(), nullable=True),
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
            "default_tax_rate >= 0 AND default_tax_rate <= 100",
            name=op.f("ck_company_settings_tax_rate_range"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_company_settings_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_settings")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_company_settings_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_company_settings_tenant_id")),
    )
    op.create_table(
        "document_sequences",
        sa.Column("doc_type", sa.String(length=30), nullable=False),
        sa.Column("prefix", sa.String(length=10), nullable=False),
        sa.Column("next_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "next_number > 0", name=op.f("ck_document_sequences_next_number_positive")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_document_sequences_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_sequences")),
        sa.UniqueConstraint(
            "tenant_id", "doc_type", name=op.f("uq_document_sequences_tenant_id_doc_type")
        ),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_document_sequences_tenant_id_id")),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("operation", sa.String(length=60), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
            name=op.f("fk_idempotency_keys_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_idempotency_keys_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "operation",
            "key",
            name=op.f("uq_idempotency_keys_tenant_id_operation_key"),
        ),
    )
    op.create_table(
        "units",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("abbreviation", sa.String(length=20), nullable=False),
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
            name=op.f("fk_units_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_units")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_units_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_units_tenant_id_name")),
    )
    op.create_table(
        "products",
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("unit_id", sa.Uuid(), nullable=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "purchase_price", sa.Numeric(precision=14, scale=4), server_default="0", nullable=False
        ),
        sa.Column(
            "selling_price", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False
        ),
        sa.Column(
            "average_cost", sa.Numeric(precision=14, scale=4), server_default="0", nullable=False
        ),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), server_default="0", nullable=False),
        sa.Column("track_inventory", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
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
        sa.CheckConstraint("average_cost >= 0", name=op.f("ck_products_average_cost_non_negative")),
        sa.CheckConstraint(
            "purchase_price >= 0", name=op.f("ck_products_purchase_price_non_negative")
        ),
        sa.CheckConstraint(
            "selling_price >= 0", name=op.f("ck_products_selling_price_non_negative")
        ),
        sa.CheckConstraint(
            "tax_rate >= 0 AND tax_rate <= 100", name=op.f("ck_products_tax_rate_range")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name=op.f("fk_products_tenant_id_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "unit_id"],
            ["units.tenant_id", "units.id"],
            name=op.f("fk_products_tenant_id_unit_id_units"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_products_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_products_tenant_id_id")),
        sa.UniqueConstraint("tenant_id", "sku", name=op.f("uq_products_tenant_id_sku")),
    )
    op.create_index(
        "ix_products_name_trgm",
        "products",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_products_tenant_id_category_id", "products", ["tenant_id", "category_id"], unique=False
    )
    op.create_index(
        "uq_products_tenant_id_barcode",
        "products",
        ["tenant_id", "barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )
    op.create_table(
        "inventory_movements",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("movement_type", sa.String(length=20), nullable=False),
        sa.Column(
            "quantity_in", sa.Numeric(precision=14, scale=3), server_default="0", nullable=False
        ),
        sa.Column(
            "quantity_out", sa.Numeric(precision=14, scale=3), server_default="0", nullable=False
        ),
        sa.Column(
            "unit_cost", sa.Numeric(precision=14, scale=4), server_default="0", nullable=False
        ),
        sa.Column("balance_after", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("reference_type", sa.String(length=30), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
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
            "movement_type IN ('purchase_receipt', 'sale', 'sale_return', 'purchase_return', 'adjustment_in', 'adjustment_out', 'transfer_in', 'transfer_out')",
            name=op.f("ck_inventory_movements_type_valid"),
        ),
        sa.CheckConstraint(
            "(quantity_in > 0 AND quantity_out = 0) OR (quantity_out > 0 AND quantity_in = 0)",
            name=op.f("ck_inventory_movements_exactly_one_direction"),
        ),
        sa.CheckConstraint(
            "unit_cost >= 0", name=op.f("ck_inventory_movements_unit_cost_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_inventory_movements_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_inventory_movements_tenant_id_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name=op.f("fk_inventory_movements_tenant_id_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_inventory_movements_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_movements")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_inventory_movements_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "reference_type",
            "reference_id",
            "line_no",
            "movement_type",
            name="uq_inventory_movements_reference",
        ),
    )
    op.create_index(
        "ix_inventory_movements_product",
        "inventory_movements",
        ["tenant_id", "product_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_inventory_movements_warehouse",
        "inventory_movements",
        ["tenant_id", "warehouse_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "stock_adjustments",
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=3), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
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
        sa.CheckConstraint(
            "direction IN ('in', 'out')", name=op.f("ck_stock_adjustments_direction_valid")
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_stock_adjustments_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_stock_adjustments_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_stock_adjustments_tenant_id_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name=op.f("fk_stock_adjustments_tenant_id_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_stock_adjustments_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_adjustments")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_stock_adjustments_tenant_id_id")),
    )
    op.create_table(
        "stock_balances",
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "quantity", sa.Numeric(precision=14, scale=3), server_default="0", nullable=False
        ),
        sa.Column(
            "reserved_quantity",
            sa.Numeric(precision=14, scale=3),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "minimum_stock_level",
            sa.Numeric(precision=14, scale=3),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "minimum_stock_level >= 0", name=op.f("ck_stock_balances_minimum_non_negative")
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0", name=op.f("ck_stock_balances_reserved_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_stock_balances_tenant_id_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name=op.f("fk_stock_balances_tenant_id_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_stock_balances_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_balances")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_stock_balances_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "warehouse_id",
            "product_id",
            name=op.f("uq_stock_balances_tenant_id_warehouse_id_product_id"),
        ),
    )
    op.create_index(
        "ix_stock_balances_tenant_id_product_id",
        "stock_balances",
        ["tenant_id", "product_id"],
        unique=False,
    )
    op.create_table(
        "stock_transfers",
        sa.Column("from_warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("to_warehouse_id", sa.Uuid(), nullable=False),
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
            "from_warehouse_id <> to_warehouse_id",
            name=op.f("ck_stock_transfers_different_warehouses"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_stock_transfers_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "from_warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name=op.f("fk_stock_transfers_tenant_id_from_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "to_warehouse_id"],
            ["warehouses.tenant_id", "warehouses.id"],
            name=op.f("fk_stock_transfers_tenant_id_to_warehouse_id_warehouses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_stock_transfers_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_transfers")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_stock_transfers_tenant_id_id")),
    )
    op.create_table(
        "stock_transfer_items",
        sa.Column("transfer_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_stock_transfer_items_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_stock_transfer_items_tenant_id_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "transfer_id"],
            ["stock_transfers.tenant_id", "stock_transfers.id"],
            name=op.f("fk_stock_transfer_items_tenant_id_transfer_id_stock_transfers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_stock_transfer_items_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_transfer_items")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_stock_transfer_items_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "transfer_id",
            "product_id",
            name=op.f("uq_stock_transfer_items_tenant_id_transfer_id_product_id"),
        ),
    )

    for table in ("company_settings", "categories", "units", "products"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    for table in (
        "company_settings",
        "document_sequences",
        "idempotency_keys",
        "categories",
        "units",
        "products",
        "stock_balances",
        "inventory_movements",
        "stock_adjustments",
        "stock_transfers",
        "stock_transfer_items",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = app_current_tenant_id()) "
            f"WITH CHECK (tenant_id = app_current_tenant_id())"
        )

    # The ledger is append-only for the application role.
    role = get_settings().db_app_user
    for table in (
        "inventory_movements",
        "stock_adjustments",
        "stock_transfers",
        "stock_transfer_items",
    ):
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM {role}")


def downgrade() -> None:
    op.drop_table("stock_transfer_items")
    op.drop_table("stock_transfers")
    op.drop_index("ix_stock_balances_tenant_id_product_id", table_name="stock_balances")
    op.drop_table("stock_balances")
    op.drop_table("stock_adjustments")
    op.drop_index("ix_inventory_movements_warehouse", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_product", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_index(
        "uq_products_tenant_id_barcode",
        table_name="products",
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )
    op.drop_index("ix_products_tenant_id_category_id", table_name="products")
    op.drop_index(
        "ix_products_name_trgm",
        table_name="products",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_table("products")
    op.drop_table("units")
    op.drop_table("idempotency_keys")
    op.drop_table("document_sequences")
    op.drop_table("company_settings")
    op.drop_table("categories")
