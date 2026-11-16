import hashlib
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError
from app.modules.authorization.service import TenantAccess
from app.modules.settings.models import CompanySettings, DocumentSequence, IdempotencyKey


async def get_company_settings(db: AsyncSession, tenant_id: uuid.UUID) -> CompanySettings:
    row = (
        await db.execute(select(CompanySettings).where(CompanySettings.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if row is None:  # companies created before this table existed
        row = CompanySettings(tenant_id=tenant_id)
        db.add(row)
        await db.flush()
        await db.refresh(row)
    return row


async def next_document_number(
    db: AsyncSession, tenant_id: uuid.UUID, doc_type: str, prefix: str
) -> str:
    """Concurrency-safe numbering: the sequence row stays locked until the caller's
    transaction ends, so numbers are unique and gap-free (a rollback returns the number)."""
    await db.execute(
        pg_insert(DocumentSequence)
        .values(tenant_id=tenant_id, doc_type=doc_type, prefix=prefix)
        .on_conflict_do_nothing(index_elements=["tenant_id", "doc_type"])
    )
    seq = (
        await db.execute(
            select(DocumentSequence)
            .where(DocumentSequence.tenant_id == tenant_id, DocumentSequence.doc_type == doc_type)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    number = f"{seq.prefix}-{seq.next_number:06d}"
    seq.next_number += 1
    await db.flush()
    return number


def idempotency_key(
    key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=100,
        description="Send the same value when retrying; the operation runs at most once.",
    ),
) -> str | None:
    return key


async def run_idempotent(
    db: AsyncSession,
    access: TenantAccess,
    operation: str,
    key: str | None,
    payload: BaseModel,
    action: Callable[[], Awaitable[BaseModel]],
) -> dict[str, Any]:
    """Runs `action` at most once per (company, operation, key).

    The key row is inserted in the SAME transaction as the business change. A concurrent
    duplicate blocks on the unique index until the first request commits, then receives
    the stored response instead of executing again. If the first request fails, its key
    row is rolled back with it and a retry executes normally.
    """
    if key is None:
        return (await action()).model_dump(mode="json")
    digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    record = IdempotencyKey(
        tenant_id=access.tenant_id,
        operation=operation,
        key=key,
        request_hash=digest,
        created_by=access.user_id,
    )
    try:
        async with db.begin_nested():
            db.add(record)
            await db.flush()
    except IntegrityError:
        existing = (
            await db.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.tenant_id == access.tenant_id,
                    IdempotencyKey.operation == operation,
                    IdempotencyKey.key == key,
                )
            )
        ).scalar_one()
        if existing.request_hash != digest:
            raise ConflictError(
                "Idempotency-Key was already used with a different request",
                code="IDEMPOTENCY_KEY_REUSED",
            ) from None
        if existing.response is None:
            raise AppError(
                "The original request is still being processed", code="IN_PROGRESS"
            ) from None
        return {**existing.response, "idempotent_replay": True}
    result = (await action()).model_dump(mode="json")
    record.response = result
    await db.flush()
    return result
