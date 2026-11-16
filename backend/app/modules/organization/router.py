import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, PageParams
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.authorization.service import TenantAccess
from app.modules.organization.schemas import (
    BranchCreate,
    BranchOut,
    BranchUpdate,
    WarehouseCreate,
    WarehouseOut,
    WarehouseUpdate,
)
from app.modules.organization.service import OrganizationService

branches_router = APIRouter(prefix="/branches", tags=["Branches"])
warehouses_router = APIRouter(prefix="/warehouses", tags=["Warehouses"])

Search = Annotated[str | None, Query(max_length=100, description="Search in name and code")]


def _service(permission: str):
    def factory(
        access: TenantAccess = Depends(require_permission(permission)),
        db: AsyncSession = Depends(get_db),
    ) -> OrganizationService:
        return OrganizationService(db, access)

    return factory


def _page(items, total: int, page: PageParams, schema):
    return Page(
        items=[schema.model_validate(i) for i in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@branches_router.get("", response_model=SuccessResponse[Page[BranchOut]])
async def list_branches(
    page: PageParams = Depends(),
    q: Search = None,
    is_active: bool | None = None,
    service: OrganizationService = Depends(_service("branches.view")),
):
    items, total = await service.list_branches(page, q, is_active)
    return ok(_page(items, total, page, BranchOut))


@branches_router.post(
    "", response_model=SuccessResponse[BranchOut], status_code=status.HTTP_201_CREATED
)
async def create_branch(
    data: BranchCreate, service: OrganizationService = Depends(_service("branches.manage"))
):
    return ok(BranchOut.model_validate(await service.create_branch(data)), "Branch created")


@branches_router.get("/{branch_id}", response_model=SuccessResponse[BranchOut])
async def get_branch(
    branch_id: uuid.UUID, service: OrganizationService = Depends(_service("branches.view"))
):
    return ok(BranchOut.model_validate(await service.get_branch(branch_id)))


@branches_router.patch("/{branch_id}", response_model=SuccessResponse[BranchOut])
async def update_branch(
    branch_id: uuid.UUID,
    data: BranchUpdate,
    service: OrganizationService = Depends(_service("branches.manage")),
):
    branch = await service.update_branch(branch_id, data)
    return ok(BranchOut.model_validate(branch), "Branch updated")


@warehouses_router.get("", response_model=SuccessResponse[Page[WarehouseOut]])
async def list_warehouses(
    page: PageParams = Depends(),
    q: Search = None,
    is_active: bool | None = None,
    branch_id: uuid.UUID | None = None,
    service: OrganizationService = Depends(_service("warehouses.view")),
):
    items, total = await service.list_warehouses(page, q, is_active, branch_id)
    return ok(_page(items, total, page, WarehouseOut))


@warehouses_router.post(
    "", response_model=SuccessResponse[WarehouseOut], status_code=status.HTTP_201_CREATED
)
async def create_warehouse(
    data: WarehouseCreate, service: OrganizationService = Depends(_service("warehouses.manage"))
):
    warehouse = await service.create_warehouse(data)
    return ok(WarehouseOut.model_validate(warehouse), "Warehouse created")


@warehouses_router.get("/{warehouse_id}", response_model=SuccessResponse[WarehouseOut])
async def get_warehouse(
    warehouse_id: uuid.UUID, service: OrganizationService = Depends(_service("warehouses.view"))
):
    return ok(WarehouseOut.model_validate(await service.get_warehouse(warehouse_id)))


@warehouses_router.patch("/{warehouse_id}", response_model=SuccessResponse[WarehouseOut])
async def update_warehouse(
    warehouse_id: uuid.UUID,
    data: WarehouseUpdate,
    service: OrganizationService = Depends(_service("warehouses.manage")),
):
    warehouse = await service.update_warehouse(warehouse_id, data)
    return ok(WarehouseOut.model_validate(warehouse), "Warehouse updated")
