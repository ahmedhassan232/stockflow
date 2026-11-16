import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import PageParams
from app.modules.authorization.service import TenantAccess
from app.modules.organization.models import Branch, Warehouse
from app.modules.organization.repository import BranchRepository, WarehouseRepository
from app.modules.organization.schemas import (
    BranchCreate,
    BranchUpdate,
    WarehouseCreate,
    WarehouseUpdate,
)


class OrganizationService:
    """Branches and warehouses of the caller's active company.

    Branch restriction: a member with `restricted_to_branches` only sees and changes their
    assigned branches and the warehouses attached to them. Anything else answers 404 (not
    403) so the existence of other branches is not disclosed.
    """

    def __init__(self, db: AsyncSession, access: TenantAccess) -> None:
        self.db = db
        self.access = access
        self.branches = BranchRepository(db, access.tenant_id)
        self.warehouses = WarehouseRepository(db, access.tenant_id)

    def _only_branches(self) -> frozenset[uuid.UUID] | None:
        return self.access.branch_ids if self.access.restricted_to_branches else None

    def _require_company_wide(self) -> None:
        if self.access.restricted_to_branches:
            raise ForbiddenError(
                "This action requires access to all branches", code="BRANCH_SCOPE_REQUIRED"
            )

    # ── branches ──

    async def list_branches(
        self, page: PageParams, q: str | None, is_active: bool | None
    ) -> tuple[Sequence[Branch], int]:
        return await self.branches.search(
            q=q,
            is_active=is_active,
            only_ids=self._only_branches(),
            limit=page.page_size,
            offset=page.offset,
        )

    async def get_branch(self, branch_id: uuid.UUID) -> Branch:
        branch = await self.branches.get(branch_id)
        if branch is None or not self.access.can_access_branch(branch.id):
            raise NotFoundError("Branch not found")
        return branch

    async def create_branch(self, data: BranchCreate) -> Branch:
        self._require_company_wide()
        try:
            async with self.db.begin_nested():
                return await self.branches.add(Branch(**data.model_dump()))
        except IntegrityError as exc:
            raise ConflictError(
                "A branch with this code already exists", code="CODE_TAKEN"
            ) from exc

    async def update_branch(self, branch_id: uuid.UUID, data: BranchUpdate) -> Branch:
        branch = await self.get_branch(branch_id)
        values = data.model_dump(exclude_unset=True)
        if values.get("name", "") is None or values.get("is_active", True) is None:
            raise AppError("name and is_active cannot be null")
        for field, value in values.items():
            setattr(branch, field, value)
        await self.db.flush()
        await self.db.refresh(branch)
        return branch

    # ── warehouses ──

    async def _check_target_branch(self, branch_id: uuid.UUID | None) -> None:
        if branch_id is None:
            self._require_company_wide()  # an unattached warehouse is company-wide
            return
        await self.get_branch(branch_id)  # 404 when missing, foreign or out of scope

    async def list_warehouses(
        self, page: PageParams, q: str | None, is_active: bool | None, branch_id: uuid.UUID | None
    ) -> tuple[Sequence[Warehouse], int]:
        return await self.warehouses.search(
            q=q,
            is_active=is_active,
            branch_id=branch_id,
            only_branch_ids=self._only_branches(),
            limit=page.page_size,
            offset=page.offset,
        )

    async def get_warehouse(self, warehouse_id: uuid.UUID) -> Warehouse:
        warehouse = await self.warehouses.get(warehouse_id)
        if warehouse is None or not self.access.can_access_branch(warehouse.branch_id):
            raise NotFoundError("Warehouse not found")
        return warehouse

    async def create_warehouse(self, data: WarehouseCreate) -> Warehouse:
        await self._check_target_branch(data.branch_id)
        try:
            async with self.db.begin_nested():
                return await self.warehouses.add(Warehouse(**data.model_dump()))
        except IntegrityError as exc:
            raise ConflictError(
                "A warehouse with this code already exists", code="CODE_TAKEN"
            ) from exc

    async def update_warehouse(self, warehouse_id: uuid.UUID, data: WarehouseUpdate) -> Warehouse:
        warehouse = await self.get_warehouse(warehouse_id)
        values = data.model_dump(exclude_unset=True)
        if values.get("name", "") is None or values.get("is_active", True) is None:
            raise AppError("name and is_active cannot be null")
        if "branch_id" in values:
            await self._check_target_branch(values["branch_id"])
        for field, value in values.items():
            setattr(warehouse, field, value)
        await self.db.flush()
        await self.db.refresh(warehouse)
        return warehouse
