import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Code = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=1,
        max_length=30,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    ),
]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class _Strict(BaseModel):
    # No tenant_id / id fields exist here and unknown fields are rejected.
    model_config = ConfigDict(extra="forbid")


class BranchCreate(_Strict):
    name: Name
    code: Code
    address: Address | None = None
    phone: Phone | None = None


class BranchUpdate(_Strict):
    name: Name | None = None
    address: Address | None = None
    phone: Phone | None = None
    is_active: bool | None = None


class BranchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    address: str | None
    phone: str | None
    manager_membership_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WarehouseCreate(_Strict):
    name: Name
    code: Code
    branch_id: uuid.UUID | None = None
    address: Address | None = None


class WarehouseUpdate(_Strict):
    name: Name | None = None
    branch_id: uuid.UUID | None = None
    address: Address | None = None
    is_active: bool | None = None


class WarehouseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    branch_id: uuid.UUID | None
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
