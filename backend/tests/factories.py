"""Test data helpers. They go through the real services and the real runtime DB role."""

import uuid
from dataclasses import dataclass

from app.db.tenant import TenantContext, context_transaction
from app.modules.tenants.schemas import ProvisionedTenant, TenantCreate
from app.modules.tenants.service import TenantProvisioningService
from app.modules.users.models import User


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


async def create_user(name: str = "Test User") -> uuid.UUID:
    async with context_transaction(TenantContext()) as session:
        user = User(full_name=name, email=f"{unique('user')}@example.com")
        session.add(user)
        await session.flush()
        return user.id


@dataclass(frozen=True)
class Company:
    owner_id: uuid.UUID
    p: ProvisionedTenant
    slug: str

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.p.tenant_id

    @property
    def ctx(self) -> TenantContext:
        return TenantContext(tenant_id=self.p.tenant_id, user_id=self.owner_id)


async def create_company(name: str, owner_id: uuid.UUID | None = None) -> Company:
    owner_id = owner_id or await create_user(f"{name} owner")
    slug = unique("co")
    async with context_transaction(TenantContext(user_id=owner_id)) as session:
        provisioned = await TenantProvisioningService(session).provision(
            owner_user_id=owner_id, data=TenantCreate(name=name, slug=slug)
        )
    return Company(owner_id=owner_id, p=provisioned, slug=slug)
