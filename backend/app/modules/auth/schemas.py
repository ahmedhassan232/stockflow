import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.modules.tenants.schemas import TenantCreate

# Length-based policy (NIST 800-63B): long passphrases beat composition rules.
Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_Strict):
    full_name: Name
    email: EmailStr
    password: Password
    company: TenantCreate


class LoginRequest(_Strict):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class SelectCompanyRequest(_Strict):
    tenant_id: uuid.UUID


class ForgotPasswordRequest(_Strict):
    email: EmailStr


class ResetPasswordRequest(_Strict):
    email: EmailStr | None = None
    code: Annotated[str, StringConstraints(pattern=r"^\d{6}$")] | None = None
    token: Annotated[str, StringConstraints(min_length=20, max_length=200)] | None = None
    new_password: Password

    @model_validator(mode="after")
    def validate_reset_method(self):
        if self.token is not None:
            if self.email is not None or self.code is not None:
                raise ValueError("Use either an invitation token or an email and reset code")
        elif self.email is None or self.code is None:
            raise ValueError("Email and six-digit code are required")
        return self


class ChangePasswordRequest(_Strict):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Password


class ProfileUpdate(_Strict):
    full_name: Name | None = None
    phone: Phone | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    avatar_url: str | None
    email_verified: bool
    is_platform_admin: bool = False


class CompanyMembershipOut(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    tenant_status: str
    membership_status: str


class ActiveCompanyOut(BaseModel):
    tenant_id: uuid.UUID
    name: str
    slug: str
    currency: str
    timezone: str
    membership_id: uuid.UUID
    role_code: str
    role_name: str
    permissions: list[str]
    restricted_to_branches: bool
    branch_ids: list[uuid.UUID]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    active_tenant_id: uuid.UUID | None


class AuthOut(TokenOut):
    user: UserOut
    memberships: list[CompanyMembershipOut]


class MeOut(BaseModel):
    user: UserOut
    memberships: list[CompanyMembershipOut]
    active_company: ActiveCompanyOut | None


class SessionOut(BaseModel):
    id: uuid.UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    last_seen_at: datetime
    is_current: bool = Field(default=False)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
