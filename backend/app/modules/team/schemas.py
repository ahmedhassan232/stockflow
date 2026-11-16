import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.core.money import RateIn

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmployeeInvite(_Strict):
    full_name: Name
    email: EmailStr
    role_id: uuid.UUID
    # null = every branch; a list = ONLY those branches
    branch_ids: Annotated[list[uuid.UUID], Field(max_length=100)] | None = None


class EmployeeUpdate(_Strict):
    role_id: uuid.UUID | None = None
    status: Literal["active", "suspended"] | None = None
    restricted_to_branches: bool | None = None
    branch_ids: Annotated[list[uuid.UUID], Field(max_length=100)] | None = None


class EmployeeOut(BaseModel):
    id: uuid.UUID  # membership id
    user_id: uuid.UUID
    full_name: str
    email: str
    role_id: uuid.UUID
    role_code: str
    role_name: str
    status: str
    has_password: bool
    restricted_to_branches: bool
    branch_ids: list[uuid.UUID]
    joined_at: datetime
    is_self: bool


class RoleIn(_Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = (
        None
    )
    permissions: Annotated[list[str], Field(max_length=200)]


class RoleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_system: bool
    is_owner: bool
    permissions: list[str]
    member_count: int


class PermissionOut(BaseModel):
    code: str
    description: str
    group: str


class SettingsUpdate(_Strict):
    name: Name | None = None
    legal_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = (
        None
    )
    email: EmailStr | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    timezone: Annotated[str, StringConstraints(max_length=64)] | None = None
    tax_number: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = (
        None
    )
    default_tax_rate: RateIn | None = None
    allow_negative_stock: bool | None = None
    invoice_footer: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None
    ) = None


class SettingsOut(BaseModel):
    name: str
    slug: str
    legal_name: str | None
    email: str | None
    phone: str | None
    address: str | None
    currency: str
    timezone: str
    tax_number: str | None
    default_tax_rate: Decimal
    allow_negative_stock: bool
    invoice_footer: str | None
