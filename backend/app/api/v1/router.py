"""Aggregates every module router under /api/v1. New modules are registered here."""

from fastapi import APIRouter

from app.modules.activity.router import audit_router, notifications_router
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import categories_router, products_router, units_router
from app.modules.expenses.router import router as expenses_router
from app.modules.health.router import router as health_router
from app.modules.inventory.router import router as inventory_router
from app.modules.organization.router import branches_router, warehouses_router
from app.modules.partners.router import customers_router, suppliers_router
from app.modules.platform.router import router as platform_router
from app.modules.purchasing.router import router as purchases_router
from app.modules.reports.router import router as reports_router
from app.modules.sales.router import router as sales_router
from app.modules.team.router import employees_router, roles_router, settings_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(branches_router)
api_router.include_router(warehouses_router)
for _router in (
    categories_router,
    units_router,
    products_router,
    inventory_router,
    suppliers_router,
    customers_router,
    purchases_router,
    sales_router,
    notifications_router,
    audit_router,
    reports_router,
    employees_router,
    roles_router,
    settings_router,
    expenses_router,
    platform_router,
):
    api_router.include_router(_router)
