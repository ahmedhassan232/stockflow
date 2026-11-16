"""Operating expenses: record, list, void. Feeds the net-profit figure in reports."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csv_export import csv_response
from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.core.money import money
from app.core.pagination import Page, PageParams
from app.core.responses import SuccessResponse, ok
from app.db.repository import like_pattern
from app.db.session import get_db
from app.modules.activity.service import audit
from app.modules.auth.dependencies import require_permission
from app.modules.authorization.service import TenantAccess
from app.modules.expenses.models import Expense
from app.modules.organization.models import Branch
from app.modules.purchasing.schemas import PositiveMoney
from app.modules.settings.service import idempotency_key, next_document_number, run_idempotent
from app.modules.users.models import User

router = APIRouter(prefix="/expenses", tags=["Expenses"])

Method = Literal["cash", "card", "bank_transfer", "wallet"]
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
Text500 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_date: date
    category: Category
    amount: PositiveMoney
    method: Method = "cash"
    description: Text500 | None = None
    branch_id: uuid.UUID | None = None


class VoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    expense_date: date
    category: str
    description: str | None
    amount: Decimal
    method: str
    branch_id: uuid.UUID | None
    branch_name: str | None = None
    status: str
    void_reason: str | None
    created_by_name: str | None = None
    created_at: datetime


class ExpenseList(Page[ExpenseOut]):
    total_amount: Decimal  # active expenses matching the filters (all pages)


def _filters(
    access: TenantAccess,
    q: str | None,
    category: str | None,
    date_from: date | None,
    date_to: date | None,
    status_: str | None,
) -> list:
    where = [Expense.tenant_id == access.tenant_id]
    if access.restricted_to_branches:
        # branch-restricted staff see only their branches' expenses (not company-wide ones)
        where.append(Expense.branch_id.in_(access.branch_ids))
    if q:
        pattern = like_pattern(q)
        where.append(
            Expense.description.ilike(pattern, escape="\\")
            | Expense.category.ilike(pattern, escape="\\")
            | Expense.number.ilike(pattern, escape="\\")
        )
    if category:
        where.append(Expense.category == category)
    if date_from:
        where.append(Expense.expense_date >= date_from)
    if date_to:
        where.append(Expense.expense_date <= date_to)
    if status_:
        where.append(Expense.status == status_)
    return where


def _query(where: list):
    return (
        select(Expense, Branch.name, User.full_name)
        .outerjoin(
            Branch, (Branch.tenant_id == Expense.tenant_id) & (Branch.id == Expense.branch_id)
        )
        .join(User, User.id == Expense.created_by)
        .where(*where)
        .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
    )


def _out(expense: Expense, branch: str | None, creator: str | None) -> ExpenseOut:
    out = ExpenseOut.model_validate(expense)
    out.branch_name, out.created_by_name = branch, creator
    return out


StatusFilter = Annotated[Literal["active", "voided"] | None, Query(alias="status")]


@router.get("", response_model=SuccessResponse[ExpenseList])
async def list_expenses(
    page: PageParams = Depends(),
    q: Annotated[str | None, Query(max_length=100)] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_: StatusFilter = None,
    access: TenantAccess = Depends(require_permission("expenses.view")),
    db: AsyncSession = Depends(get_db),
):
    where = _filters(access, q, category, date_from, date_to, status_)
    total, amount = (
        await db.execute(
            select(
                func.count(Expense.id),
                func.coalesce(func.sum(Expense.amount).filter(Expense.status == "active"), 0),
            ).where(*where)
        )
    ).one()
    rows = await db.execute(_query(where).limit(page.page_size).offset(page.offset))
    return ok(
        ExpenseList(
            items=[_out(*r) for r in rows.all()],
            total=total,
            page=page.page,
            page_size=page.page_size,
            total_amount=money(Decimal(amount)),
        )
    )


@router.get("/categories", response_model=SuccessResponse[list[str]])
async def expense_categories(
    access: TenantAccess = Depends(require_permission("expenses.view")),
    db: AsyncSession = Depends(get_db),
):
    """Categories already used by this company (for suggestions in the form)."""
    rows = await db.execute(
        select(Expense.category)
        .where(Expense.tenant_id == access.tenant_id)
        .group_by(Expense.category)
        .order_by(func.count().desc())
        .limit(50)
    )
    return ok(list(rows.scalars()))


@router.get("/export", summary="Download the filtered expenses as CSV")
async def export_expenses(
    q: Annotated[str | None, Query(max_length=100)] = None,
    category: Annotated[str | None, Query(max_length=60)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_: StatusFilter = None,
    access: TenantAccess = Depends(require_permission("expenses.view")),
    db: AsyncSession = Depends(get_db),
):
    where = _filters(access, q, category, date_from, date_to, status_)
    rows = (await db.execute(_query(where).limit(10_000))).all()
    return csv_response(
        "expenses.csv",
        [
            "Number",
            "Date",
            "Category",
            "Description",
            "Amount",
            "Method",
            "Branch",
            "Status",
            "Recorded by",
        ],
        [
            (
                e.number,
                e.expense_date,
                e.category,
                e.description,
                e.amount,
                e.method,
                branch,
                e.status,
                creator,
            )
            for e, branch, creator in rows
        ],
    )


@router.post("", response_model=SuccessResponse[ExpenseOut], status_code=status.HTTP_201_CREATED)
async def create_expense(
    data: ExpenseCreate,
    key: str | None = Depends(idempotency_key),
    access: TenantAccess = Depends(require_permission("expenses.manage")),
    db: AsyncSession = Depends(get_db),
):
    async def action() -> ExpenseOut:
        if data.expense_date > datetime.now(ZoneInfo(access.tenant.timezone)).date():
            raise AppError("An expense cannot be dated in the future", code="FUTURE_DATE")
        branch_name = None
        if data.branch_id is not None:
            branch = (
                await db.execute(
                    select(Branch).where(
                        Branch.tenant_id == access.tenant_id, Branch.id == data.branch_id
                    )
                )
            ).scalar_one_or_none()
            if branch is None:
                raise AppError("Branch not found", code="INVALID_REFERENCE")
            branch_name = branch.name
        if not access.can_access_branch(data.branch_id):
            raise ForbiddenError("You can only record expenses for your own branches")
        expense = Expense(
            tenant_id=access.tenant_id,
            number=await next_document_number(db, access.tenant_id, "expense", "EXP"),
            created_by=access.user_id,
            **data.model_dump(),
        )
        db.add(expense)
        await db.flush()
        await db.refresh(expense)
        audit(db, access, "expense.created", "expense", expense.id, expense.number)
        return _out(expense, branch_name, None)

    return ok(await run_idempotent(db, access, "expenses.create", key, data, action))


@router.post("/{expense_id}/void", response_model=SuccessResponse[ExpenseOut])
async def void_expense(
    expense_id: uuid.UUID,
    data: VoidRequest,
    access: TenantAccess = Depends(require_permission("expenses.manage")),
    db: AsyncSession = Depends(get_db),
):
    expense = (
        await db.execute(
            select(Expense)
            .where(Expense.tenant_id == access.tenant_id, Expense.id == expense_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if expense is None or (
        access.restricted_to_branches and not access.can_access_branch(expense.branch_id)
    ):
        raise NotFoundError("Expense not found")
    if expense.status != "active":
        raise AppError("This expense is already voided", code="INVALID_STATUS")
    expense.status, expense.void_reason, expense.voided_at = (
        "voided",
        data.reason,
        datetime.now(UTC),
    )
    await db.flush()
    await db.refresh(expense)
    audit(
        db, access, "expense.voided", "expense", expense.id, expense.number, {"reason": data.reason}
    )
    return ok(_out(expense, None, None))
