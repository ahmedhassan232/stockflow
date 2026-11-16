"""Factory for simple tenant-owned master-data resources (categories, units, suppliers,
customers …): list/search/paginate, create, read, update. Every route is permission-checked
and every query goes through TenantRepository (+ RLS)."""

import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.pagination import Page, PageParams
from app.core.responses import SuccessResponse, ok
from app.db.base import Base
from app.db.repository import TenantRepository
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.authorization.service import TenantAccess


def repo_for[M: Base](
    model: type[M], db: AsyncSession, tenant_id: uuid.UUID
) -> TenantRepository[M]:
    cls = type(f"{model.__name__}Repository", (TenantRepository,), {"model": model})
    return cls(db, tenant_id)


async def ensure_exists(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    model: type[Base],
    entity_id: uuid.UUID | None,
    label: str,
    *,
    must_be_active: bool = False,
) -> Any:
    """Validates a reference supplied by the client. Rows of other companies are simply
    'not found' here (repository filter + RLS), before the composite FK would even fire."""
    if entity_id is None:
        return None
    entity = await repo_for(model, db, tenant_id).get(entity_id)
    if entity is None:
        raise AppError(
            f"{label} not found", code="INVALID_REFERENCE", details={"id": str(entity_id)}
        )
    if must_be_active and not getattr(entity, "is_active", True):
        raise AppError(
            f"{label} is inactive", code="INACTIVE_REFERENCE", details={"id": str(entity_id)}
        )
    return entity


@dataclass(frozen=True)
class CrudConfig:
    model: type[Base]
    prefix: str
    tag: str
    label: str
    create_schema: type[BaseModel]
    update_schema: type[BaseModel]
    out_schema: type[BaseModel]
    view_permission: str
    manage_permission: str
    search_fields: tuple[str, ...] = ("name",)
    # request field -> (referenced model, label)
    references: dict[str, tuple[type[Base], str]] = field(default_factory=dict)
    # fields where an explicit null in PATCH means "clear the value"
    nullable: frozenset[str] = frozenset()


def build_crud_router(cfg: CrudConfig) -> APIRouter:
    router = APIRouter(prefix=cfg.prefix, tags=[cfg.tag])
    model, out = cfg.model, cfg.out_schema
    create_schema, update_schema = cfg.create_schema, cfg.update_schema

    async def _check_refs(db: AsyncSession, access: TenantAccess, values: dict[str, Any]) -> None:
        for name, (target, label) in cfg.references.items():
            if name in values:
                await ensure_exists(db, access.tenant_id, target, values[name], label)

    async def _get(db: AsyncSession, access: TenantAccess, entity_id: uuid.UUID) -> Any:
        entity = await repo_for(model, db, access.tenant_id).get(entity_id)
        if entity is None:
            raise NotFoundError(f"{cfg.label} not found")
        return entity

    @router.get("", response_model=SuccessResponse[Page[out]])
    async def list_items(
        page: PageParams = Depends(),
        q: Annotated[str | None, Query(max_length=100)] = None,
        is_active: bool | None = None,
        access: TenantAccess = Depends(require_permission(cfg.view_permission)),
        db: AsyncSession = Depends(get_db),
    ):
        where = [model.is_active.is_(is_active)] if is_active is not None else []
        items, total = await repo_for(model, db, access.tenant_id).search(
            q=q,
            fields=[getattr(model, f) for f in cfg.search_fields],
            where=where,
            order_by=(model.name, model.id),
            limit=page.page_size,
            offset=page.offset,
        )
        return ok(
            Page(
                items=[out.model_validate(i) for i in items],
                total=total,
                page=page.page,
                page_size=page.page_size,
            )
        )

    @router.post("", response_model=SuccessResponse[out], status_code=status.HTTP_201_CREATED)
    async def create_item(
        data: create_schema,  # type: ignore[valid-type]
        access: TenantAccess = Depends(require_permission(cfg.manage_permission)),
        db: AsyncSession = Depends(get_db),
    ):
        values = data.model_dump()
        await _check_refs(db, access, values)
        try:
            async with db.begin_nested():
                entity = await repo_for(model, db, access.tenant_id).add(model(**values))
        except IntegrityError as exc:
            raise ConflictError(f"{cfg.label} already exists", code="DUPLICATE") from exc
        await db.refresh(entity)
        return ok(out.model_validate(entity), f"{cfg.label} created")

    @router.get("/{item_id}", response_model=SuccessResponse[out])
    async def get_item(
        item_id: uuid.UUID,
        access: TenantAccess = Depends(require_permission(cfg.view_permission)),
        db: AsyncSession = Depends(get_db),
    ):
        return ok(out.model_validate(await _get(db, access, item_id)))

    @router.patch("/{item_id}", response_model=SuccessResponse[out])
    async def update_item(
        item_id: uuid.UUID,
        data: update_schema,  # type: ignore[valid-type]
        access: TenantAccess = Depends(require_permission(cfg.manage_permission)),
        db: AsyncSession = Depends(get_db),
    ):
        entity = await _get(db, access, item_id)
        values = {
            k: v
            for k, v in data.model_dump(exclude_unset=True).items()
            if v is not None or k in cfg.nullable
        }
        await _check_refs(db, access, values)
        try:
            async with db.begin_nested():
                for name, value in values.items():
                    setattr(entity, name, value)
                await db.flush()
        except IntegrityError as exc:
            raise ConflictError(f"{cfg.label} already exists", code="DUPLICATE") from exc
        await db.refresh(entity)
        return ok(out.model_validate(entity), f"{cfg.label} updated")

    return router
