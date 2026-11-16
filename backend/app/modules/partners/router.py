import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

from app.core.crud import CrudConfig, build_crud_router
from app.modules.partners.models import Customer, Supplier

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Phone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=32, pattern=r"^[0-9+ ()-]+$"),
]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
Long = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class PartyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    phone: Phone | None = None
    email: EmailStr | None = None
    address: Long | None = None
    tax_number: Short | None = None
    notes: Long | None = None


class PartyUpdate(PartyCreate):
    name: Name | None = None
    is_active: bool | None = None


class PartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    phone: str | None
    email: str | None
    address: str | None
    tax_number: str | None
    notes: str | None
    is_active: bool
    created_at: datetime


_NULLABLE = frozenset({"phone", "email", "address", "tax_number", "notes"})

suppliers_router = build_crud_router(
    CrudConfig(
        model=Supplier,
        prefix="/suppliers",
        tag="Suppliers",
        label="Supplier",
        create_schema=PartyCreate,
        update_schema=PartyUpdate,
        out_schema=PartyOut,
        view_permission="suppliers.view",
        manage_permission="suppliers.manage",
        search_fields=("name", "phone"),
        nullable=_NULLABLE,
    )
)
customers_router = build_crud_router(
    CrudConfig(
        model=Customer,
        prefix="/customers",
        tag="Customers",
        label="Customer",
        create_schema=PartyCreate,
        update_schema=PartyUpdate,
        out_schema=PartyOut,
        view_permission="customers.view",
        manage_permission="customers.manage",
        search_fields=("name", "phone"),
        nullable=_NULLABLE,
    )
)
