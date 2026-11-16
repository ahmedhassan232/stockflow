import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Slug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=63,
        pattern=r"^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$",  # lower-cased after validation
    ),
]


class TenantCreate(BaseModel):
    """Fields a registrant may set. `extra=forbid` blocks mass assignment
    (e.g. sending `status` or `id`)."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
    slug: Slug
    email: EmailStr | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    currency: Annotated[str, StringConstraints(to_upper=True, pattern=r"^[A-Za-z]{3}$")] = "EGP"
    timezone: Annotated[str, StringConstraints(max_length=64)] = "Africa/Cairo"
    create_default_branch: bool = True
    default_branch_name: str = Field(default="الفرع الرئيسي", min_length=1, max_length=150)
    default_warehouse_name: str = Field(default="المخزن الرئيسي", min_length=1, max_length=150)


class ProvisionedTenant(BaseModel):
    tenant_id: uuid.UUID
    owner_membership_id: uuid.UUID
    owner_role_id: uuid.UUID
    branch_id: uuid.UUID | None
    warehouse_id: uuid.UUID | None
