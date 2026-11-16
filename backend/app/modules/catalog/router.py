import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import CrudConfig, build_crud_router, ensure_exists, repo_for
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import Page, PageParams
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.authorization.service import TenantAccess
from app.modules.catalog.models import Category, Product, Unit
from app.modules.catalog.schemas import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ProductCreate,
    ProductDetail,
    ProductOut,
    ProductUpdate,
    UnitCreate,
    UnitOut,
    UnitUpdate,
    WarehouseStock,
)
from app.modules.inventory.models import InventoryMovement, StockBalance
from app.modules.organization.models import Warehouse

categories_router = build_crud_router(
    CrudConfig(
        model=Category,
        prefix="/categories",
        tag="Categories",
        label="Category",
        create_schema=CategoryCreate,
        update_schema=CategoryUpdate,
        out_schema=CategoryOut,
        view_permission="products.view",
        manage_permission="categories.manage",
        references={"parent_id": (Category, "Parent category")},
        nullable=frozenset({"description", "parent_id"}),
    )
)
units_router = build_crud_router(
    CrudConfig(
        model=Unit,
        prefix="/units",
        tag="Units",
        label="Unit",
        create_schema=UnitCreate,
        update_schema=UnitUpdate,
        out_schema=UnitOut,
        view_permission="products.view",
        manage_permission="categories.manage",
        search_fields=("name", "abbreviation"),
    )
)

products_router = APIRouter(prefix="/products", tags=["Products"])
_NULLABLE = {"barcode", "category_id", "unit_id", "description"}
_SORTS = {
    "name": (Product.name, Product.id),
    "-name": (Product.name.desc(), Product.id),
    "sku": (Product.sku,),
    "-created_at": (Product.created_at.desc(), Product.id),
    "selling_price": (Product.selling_price, Product.id),
    "-selling_price": (Product.selling_price.desc(), Product.id),
}


async def _check_refs(db: AsyncSession, tenant_id: uuid.UUID, values: dict) -> None:
    if "category_id" in values:
        await ensure_exists(db, tenant_id, Category, values["category_id"], "Category")
    if "unit_id" in values:
        await ensure_exists(db, tenant_id, Unit, values["unit_id"], "Unit")


async def _get(db: AsyncSession, access: TenantAccess, product_id: uuid.UUID) -> Product:
    product = await repo_for(Product, db, access.tenant_id).get(product_id)
    if product is None:
        raise NotFoundError("Product not found")
    return product


def _conflict(exc: IntegrityError) -> ConflictError:
    if "barcode" in str(exc.orig):
        return ConflictError("A product with this barcode already exists", code="BARCODE_TAKEN")
    return ConflictError("A product with this SKU already exists", code="SKU_TAKEN")


@products_router.get("", response_model=SuccessResponse[Page[ProductOut]])
async def list_products(
    page: PageParams = Depends(),
    q: Annotated[str | None, Query(max_length=100, description="Name, SKU or barcode")] = None,
    barcode: Annotated[
        str | None, Query(max_length=64, description="Exact match (scanner)")
    ] = None,
    category_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    sort: Literal[
        "name", "-name", "sku", "-created_at", "selling_price", "-selling_price"
    ] = "name",
    access: TenantAccess = Depends(require_permission("products.view")),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if barcode:
        where.append(Product.barcode == barcode)
    if category_id:
        where.append(Product.category_id == category_id)
    if is_active is not None:
        where.append(Product.is_active.is_(is_active))
    items, total = await repo_for(Product, db, access.tenant_id).search(
        q=q,
        fields=(Product.name, Product.sku, Product.barcode),
        where=where,
        order_by=_SORTS[sort],
        limit=page.page_size,
        offset=page.offset,
    )
    return ok(
        Page(
            items=[ProductOut.model_validate(i) for i in items],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )
    )


@products_router.post(
    "", response_model=SuccessResponse[ProductOut], status_code=status.HTTP_201_CREATED
)
async def create_product(
    data: ProductCreate,
    access: TenantAccess = Depends(require_permission("products.create")),
    db: AsyncSession = Depends(get_db),
):
    values = data.model_dump()
    await _check_refs(db, access.tenant_id, values)
    try:
        async with db.begin_nested():
            product = await repo_for(Product, db, access.tenant_id).add(Product(**values))
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    await db.refresh(product)
    return ok(ProductOut.model_validate(product), "Product created")


@products_router.get("/{product_id}", response_model=SuccessResponse[ProductDetail])
async def get_product(
    product_id: uuid.UUID,
    access: TenantAccess = Depends(require_permission("products.view")),
    db: AsyncSession = Depends(get_db),
):
    product = await _get(db, access, product_id)
    stmt = (
        select(StockBalance, Warehouse.name, Warehouse.branch_id)
        .join(
            Warehouse,
            (Warehouse.tenant_id == StockBalance.tenant_id)
            & (Warehouse.id == StockBalance.warehouse_id),
        )
        .where(StockBalance.tenant_id == access.tenant_id, StockBalance.product_id == product.id)
        .order_by(Warehouse.name)
    )
    stock = [
        WarehouseStock(
            warehouse_id=b.warehouse_id,
            warehouse_name=name,
            quantity=b.quantity,
            minimum_stock_level=b.minimum_stock_level,
        )
        for b, name, branch_id in (await db.execute(stmt)).all()
        if access.can_access_branch(branch_id)
    ]
    base = ProductOut.model_validate(product).model_dump()
    total = sum((s.quantity for s in stock), Decimal("0"))
    return ok(ProductDetail(**base, total_stock=total, stock=stock))


@products_router.patch("/{product_id}", response_model=SuccessResponse[ProductOut])
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    access: TenantAccess = Depends(require_permission("products.update")),
    db: AsyncSession = Depends(get_db),
):
    product = await _get(db, access, product_id)
    values = {
        k: v
        for k, v in data.model_dump(exclude_unset=True).items()
        if v is not None or k in _NULLABLE
    }
    await _check_refs(db, access.tenant_id, values)
    try:
        async with db.begin_nested():
            for name, value in values.items():
                setattr(product, name, value)
            await db.flush()
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    await db.refresh(product)
    return ok(ProductOut.model_validate(product), "Product updated")


@products_router.delete("/{product_id}", response_model=SuccessResponse[None])
async def delete_product(
    product_id: uuid.UUID,
    access: TenantAccess = Depends(require_permission("products.delete")),
    db: AsyncSession = Depends(get_db),
):
    """Hard delete is only possible for a product that never moved. Anything with
    history must be deactivated (PATCH is_active=false) so past documents stay intact."""
    product = await _get(db, access, product_id)
    used = (
        await db.execute(
            select(
                exists().where(
                    InventoryMovement.tenant_id == access.tenant_id,
                    InventoryMovement.product_id == product.id,
                )
            )
        )
    ).scalar()
    try:
        if used:
            raise IntegrityError("history", None, Exception("history"))
        async with db.begin_nested():
            await db.delete(product)
            await db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            "This product has transaction history and cannot be deleted. Deactivate it instead",
            code="PRODUCT_IN_USE",
        ) from exc
    return ok(None, "Product deleted")
