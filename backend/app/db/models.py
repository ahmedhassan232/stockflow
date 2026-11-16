"""Model registry: importing this module registers every table on Base.metadata.
Used by Alembic autogenerate and the schema drift test. Add new model modules here."""

from app.modules.activity.models import AuditLog, Notification
from app.modules.auth.models import AuthSession, PasswordResetToken, Permission, RefreshToken
from app.modules.authorization.models import Membership, MembershipBranch, Role, RolePermission
from app.modules.catalog.models import Category, Product, Unit
from app.modules.expenses.models import Expense  # noqa: F401
from app.modules.inventory.models import (
    InventoryMovement,
    StockAdjustment,
    StockBalance,
    StockTransfer,
    StockTransferItem,
)
from app.modules.organization.models import Branch, Warehouse
from app.modules.partners.models import Customer, Supplier
from app.modules.platform.models import PlatformAuditLog  # noqa: F401
from app.modules.purchasing.models import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseReceipt,
    PurchaseReceiptItem,
)
from app.modules.sales.models import Payment, Sale, SaleItem, SaleReturn, SaleReturnItem
from app.modules.settings.models import CompanySettings, DocumentSequence, IdempotencyKey
from app.modules.tenants.models import Tenant
from app.modules.users.models import User

__all__ = [
    "AuditLog",
    "Notification",
    "Customer",
    "Supplier",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseReceipt",
    "PurchaseReceiptItem",
    "Payment",
    "Sale",
    "SaleItem",
    "SaleReturn",
    "SaleReturnItem",
    "Category",
    "CompanySettings",
    "DocumentSequence",
    "IdempotencyKey",
    "InventoryMovement",
    "Product",
    "StockAdjustment",
    "StockBalance",
    "StockTransfer",
    "StockTransferItem",
    "Unit",
    "AuthSession",
    "Branch",
    "Membership",
    "MembershipBranch",
    "PasswordResetToken",
    "Permission",
    "RefreshToken",
    "Role",
    "RolePermission",
    "Tenant",
    "User",
    "Warehouse",
]
