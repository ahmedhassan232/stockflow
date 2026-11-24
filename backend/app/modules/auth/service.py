import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import Settings
from app.core.email import Email, deliver, deliver_direct
from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    UnauthenticatedError,
)
from app.db.tenant import TenantContext, apply_context
from app.modules.auth import security
from app.modules.auth.dependencies import Principal
from app.modules.auth.models import AuthSession, PasswordResetToken, RefreshToken
from app.modules.auth.schemas import (
    ActiveCompanyOut,
    CompanyMembershipOut,
    MeOut,
    ProfileUpdate,
    RegisterRequest,
    SessionOut,
    UserOut,
)
from app.modules.authorization.models import Membership
from app.modules.authorization.service import TenantAccess, load_tenant_access
from app.modules.tenants.models import Tenant
from app.modules.tenants.service import TenantProvisioningService
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# Two tabs refreshing at the same moment is normal; an OLD token showing up later is theft.
REFRESH_RACE_GRACE = timedelta(seconds=10)
INVALID_CREDENTIALS = "Invalid email or password"


@dataclass(frozen=True, slots=True)
class ClientMeta:
    ip: str | None
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    active_tenant_id: uuid.UUID | None
    user: User
    memberships: list[CompanyMembershipOut]


class AuthService:
    def __init__(self, db: AsyncSession, redis: Redis, settings: Settings) -> None:
        self.db = db
        self.redis = redis
        self.settings = settings

    # ───────────────────────── helpers ─────────────────────────

    async def _context(self, *, user_id: uuid.UUID, tenant_id: uuid.UUID | None = None) -> None:
        if not self.db.in_transaction():
            await self.db.begin()
        await apply_context(self.db, TenantContext(tenant_id=tenant_id, user_id=user_id))

    async def _memberships(self, user_id: uuid.UUID) -> list[CompanyMembershipOut]:
        """Needs `app.user_id` = user_id (RLS: own memberships + their companies only)."""
        rows = await self.db.execute(
            select(Membership.status, Tenant.id, Tenant.name, Tenant.slug, Tenant.status)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .where(Membership.user_id == user_id, Membership.status != "revoked")
            .order_by(Membership.joined_at)
        )
        return [
            CompanyMembershipOut(
                membership_status=m_status,
                tenant_id=tid,
                tenant_name=name,
                tenant_slug=slug,
                tenant_status=t_status,
            )
            for m_status, tid, name, slug, t_status in rows.all()
        ]

    async def _new_refresh_token(self, session: AuthSession) -> str:
        raw, digest = security.new_opaque_token()
        self.db.add(
            RefreshToken(
                session_id=session.id,
                user_id=session.user_id,
                token_hash=digest,
                expires_at=session.expires_at,
            )
        )
        await self.db.flush()
        return raw

    async def _open_session(
        self, user: User, meta: ClientMeta, tenant_id: uuid.UUID | None
    ) -> IssuedTokens:
        now = datetime.now(UTC)
        session = AuthSession(
            user_id=user.id,
            active_tenant_id=tenant_id,
            ip_address=meta.ip,
            user_agent=(meta.user_agent or "")[:300] or None,
            expires_at=now + timedelta(days=self.settings.refresh_token_ttl_days),
        )
        self.db.add(session)
        await self.db.flush()
        refresh = await self._new_refresh_token(session)
        access, ttl = security.create_access_token(
            user_id=user.id, session_id=session.id, tenant_id=tenant_id
        )
        return IssuedTokens(access, ttl, refresh, tenant_id, user, await self._memberships(user.id))

    async def _revoke_sessions(
        self,
        user_id: uuid.UUID,
        reason: str,
        *,
        only: uuid.UUID | None = None,
        keep: uuid.UUID | None = None,
    ) -> int:
        now = datetime.now(UTC)
        cond = [AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)]
        if only is not None:
            cond.append(AuthSession.id == only)
        if keep is not None:
            cond.append(AuthSession.id != keep)
        ids = (await self.db.execute(select(AuthSession.id).where(*cond))).scalars().all()
        if not ids:
            return 0
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.id.in_(ids))
            .values(revoked_at=now, revoked_reason=reason)
        )
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id.in_(ids), RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return len(ids)

    # ───────────────────────── register / login ─────────────────────────

    async def register(self, data: RegisterRequest, meta: ClientMeta) -> IssuedTokens:
        """User + company + owner membership + defaults + session: ONE transaction."""
        email = data.email.lower()
        user = User(
            full_name=data.full_name,
            email=email,
            password_hash=await security.hash_password(data.password),
        )
        try:
            async with self.db.begin_nested():
                self.db.add(user)
                await self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "An account with this email already exists", code="EMAIL_TAKEN"
            ) from exc

        provisioned = await TenantProvisioningService(self.db).provision(
            owner_user_id=user.id, data=data.company
        )
        await self._send_verification(user)
        return await self._open_session(user, meta, provisioned.tenant_id)

    # ───────────────────────── e-mail verification ─────────────────────────

    async def _send_verification(self, user: User) -> None:
        now = datetime.now(UTC)
        await self.db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.purpose == "verify_email",
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        raw, digest = security.new_opaque_token()
        self.db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=digest,
                purpose="verify_email",
                expires_at=now + timedelta(hours=48),
            )
        )
        await self.db.flush()
        link = f"{self.settings.frontend_url.rstrip('/')}/verify-email?token={raw}"
        deliver(
            Email(
                to=user.email,
                subject="StockFlow – تأكيد البريد الإلكتروني / Confirm your e-mail",
                body=(
                    f"مرحبًا {user.full_name}،\n\nلتأكيد بريدك الإلكتروني افتح الرابط التالي "
                    f"(صالح لمدة 48 ساعة):\n{link}\n\n"
                    "Open the link above to confirm your e-mail address. It expires in 48 hours."
                ),
            )
        )

    async def resend_verification(self, principal: Principal) -> None:
        if not principal.user.email_verified:
            await self._send_verification(principal.user)

    async def verify_email(self, raw_token: str) -> None:
        now = datetime.now(UTC)
        token = (
            await self.db.execute(
                select(PasswordResetToken)
                .where(
                    PasswordResetToken.token_hash == security.hash_token(raw_token),
                    PasswordResetToken.purpose == "verify_email",
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if token is None or token.used_at is not None or token.expires_at <= now:
            raise AppError(
                "This confirmation link is invalid or has expired", code="INVALID_VERIFY_TOKEN"
            )
        user = await self.db.get(User, token.user_id)
        if user is None or not user.is_active:
            raise AppError(
                "This confirmation link is invalid or has expired", code="INVALID_VERIFY_TOKEN"
            )
        user.email_verified = True
        token.used_at = now

    async def login(self, email: str, password: str, meta: ClientMeta) -> IssuedTokens:
        email = email.lower()
        s = self.settings
        if await rate_limit.current(self.redis, "login-fail", email) >= s.login_max_failures:
            raise RateLimitedError("Too many failed attempts. Try again later", code="LOGIN_LOCKED")

        user = (await self.db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        valid = await security.verify_password(user.password_hash if user else None, password)
        if user is None or not valid or not user.is_active:
            # Same answer for unknown e-mail, wrong password and disabled account.
            await rate_limit.hit(
                self.redis, "login-fail", email, limit=10**9, window=s.login_lockout_seconds
            )
            raise UnauthenticatedError(INVALID_CREDENTIALS, code="INVALID_CREDENTIALS")

        await rate_limit.reset(self.redis, "login-fail", email)
        if security.needs_rehash(user.password_hash or ""):
            user.password_hash = await security.hash_password(password)

        await self._context(user_id=user.id)
        usable = [
            m
            for m in await self._memberships(user.id)
            if m.membership_status == "active" and m.tenant_status == "active"
        ]
        # Exactly one company → select it; several → the client must call select-company.
        tenant_id = usable[0].tenant_id if len(usable) == 1 else None
        return await self._open_session(user, meta, tenant_id)

    # ───────────────────────── refresh / logout ─────────────────────────

    async def refresh(self, raw_token: str | None) -> IssuedTokens:
        if not raw_token:
            raise UnauthenticatedError("Missing refresh token", code="REFRESH_INVALID")
        now = datetime.now(UTC)
        token = (
            await self.db.execute(
                select(RefreshToken)
                .where(RefreshToken.token_hash == security.hash_token(raw_token))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if token is None:
            raise UnauthenticatedError("Invalid refresh token", code="REFRESH_INVALID")
        session = (
            await self.db.execute(
                select(AuthSession).where(AuthSession.id == token.session_id).with_for_update()
            )
        ).scalar_one()

        if token.revoked_at is not None:
            if session.revoked_at is None and now - token.revoked_at > REFRESH_RACE_GRACE:
                # A rotated-out token is being replayed: assume it was stolen and kill the
                # whole session. Commit so the revocation survives the 401 below.
                await self._revoke_sessions(session.user_id, "token_reuse", only=session.id)
                await self.db.commit()
                logger.warning("Refresh token reuse detected; session %s revoked", session.id)
                raise UnauthenticatedError("Session has been revoked", code="TOKEN_REUSED")
            raise UnauthenticatedError("Refresh token already used", code="REFRESH_RACE")
        if session.revoked_at is not None or token.expires_at <= now or session.expires_at <= now:
            raise UnauthenticatedError("Session expired", code="REFRESH_INVALID")

        user = await self.db.get(User, session.user_id)
        if user is None or not user.is_active:
            raise UnauthenticatedError("Account is disabled", code="ACCOUNT_DISABLED")

        token.revoked_at = now  # single use
        session.last_seen_at = now
        refresh = await self._new_refresh_token(session)

        tenant_id = session.active_tenant_id
        await self._context(user_id=user.id, tenant_id=tenant_id)
        if tenant_id is not None:
            try:
                await load_tenant_access(self.db, user_id=user.id, tenant_id=tenant_id)
            except ForbiddenError:
                tenant_id = session.active_tenant_id = None  # membership gone / company suspended
        access, ttl = security.create_access_token(
            user_id=user.id, session_id=session.id, tenant_id=tenant_id
        )
        return IssuedTokens(access, ttl, refresh, tenant_id, user, await self._memberships(user.id))

    async def logout(self, raw_token: str | None) -> None:
        """Idempotent; unknown or missing tokens are ignored."""
        if not raw_token:
            return
        token = (
            await self.db.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == security.hash_token(raw_token)
                )
            )
        ).scalar_one_or_none()
        if token is not None:
            await self._revoke_sessions(token.user_id, "logout", only=token.session_id)

    # ───────────────────────── company selection / profile ─────────────────────────

    async def select_company(
        self, principal: Principal, tenant_id: uuid.UUID
    ) -> tuple[str, int, TenantAccess]:
        """The requested id is only a *wish*: it is honoured solely when an ACTIVE membership
        in an ACTIVE company exists for the authenticated user."""
        await self._context(user_id=principal.user_id, tenant_id=tenant_id)
        access = await load_tenant_access(self.db, user_id=principal.user_id, tenant_id=tenant_id)
        session = await self.db.get(AuthSession, principal.session_id)
        session.active_tenant_id = tenant_id
        token, ttl = security.create_access_token(
            user_id=principal.user_id, session_id=principal.session_id, tenant_id=tenant_id
        )
        return token, ttl, access

    async def me(self, principal: Principal) -> MeOut:
        active = None
        if principal.tenant_id is not None:
            try:
                a = await load_tenant_access(
                    self.db, user_id=principal.user_id, tenant_id=principal.tenant_id
                )
                active = ActiveCompanyOut(
                    tenant_id=a.tenant_id,
                    name=a.tenant.name,
                    slug=a.tenant.slug,
                    currency=a.tenant.currency,
                    timezone=a.tenant.timezone,
                    membership_id=a.membership_id,
                    role_code=a.role_code,
                    role_name=a.role_name,
                    permissions=sorted(a.permissions),
                    restricted_to_branches=a.restricted_to_branches,
                    branch_ids=sorted(a.branch_ids),
                )
            except ForbiddenError:
                active = None
        return MeOut(
            user=UserOut.model_validate(principal.user),
            memberships=await self._memberships(principal.user_id),
            active_company=active,
        )

    async def update_profile(self, principal: Principal, data: ProfileUpdate) -> User:
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "full_name" and value is None:
                continue
            setattr(principal.user, field, value)
        await self.db.flush()
        return principal.user

    # ───────────────────────── passwords ─────────────────────────

    async def forgot_password(self, email: str) -> None:
        """Send a short-lived OTP without revealing whether an account exists."""
        normalized = email.lower()
        await rate_limit.hit(self.redis, "password-reset-request", normalized, limit=3, window=3600)
        user = (
            await self.db.execute(select(User).where(User.email == normalized))
        ).scalar_one_or_none()
        if user is None or not user.is_active:
            return

        now = datetime.now(UTC)
        await self.db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.purpose == "password_reset",
                PasswordResetToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = hmac.new(
            self.settings.jwt_secret_key.encode(),
            f"{user.id}:{code}".encode(),
            hashlib.sha256,
        ).hexdigest()
        ttl = 10
        self.db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=digest,
                purpose="password_reset",
                expires_at=now + timedelta(minutes=ttl),
            )
        )
        await self.db.flush()
        await deliver_direct(
            Email(
                to=user.email,
                subject="StockFlow – رمز إعادة تعيين كلمة المرور / Password reset code",
                body=(
                    f"مرحبًا {user.full_name}،\n\nرمز إعادة تعيين كلمة المرور هو: {code}\n"
                    f"صلاحية الرمز {ttl} دقائق. لا تشارك هذا الرمز مع أي شخص.\n\n"
                    f"Your StockFlow password reset code is: {code}\n"
                    f"It expires in {ttl} minutes. Do not share this code with anyone."
                ),
            )
        )

    async def reset_password(
        self, email: str | None, code: str | None, new_password: str, token: str | None = None
    ) -> None:
        now = datetime.now(UTC)
        normalized = email.lower() if email else None
        reset_token = None
        user = None
        token_digest = None

        if token is not None:
            # Employee invitations use a high-entropy opaque token; verification tokens
            # remain isolated by purpose and can never be used to set a password.
            token_digest = security.hash_token(token)
            await rate_limit.hit(
                self.redis, "password-reset-invite", token_digest, limit=5, window=600
            )
            reset_token = (
                await self.db.execute(
                    select(PasswordResetToken)
                    .where(
                        PasswordResetToken.token_hash == token_digest,
                        PasswordResetToken.purpose == "password_reset",
                        PasswordResetToken.used_at.is_(None),
                        PasswordResetToken.expires_at > now,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if reset_token is not None:
                user = await self.db.get(User, reset_token.user_id)
        else:
            if normalized is None or code is None:
                raise AppError("Invalid or expired reset credential", code="INVALID_RESET_TOKEN")
            await rate_limit.hit(self.redis, "password-reset-otp", normalized, limit=5, window=600)
            user = (
                await self.db.execute(select(User).where(User.email == normalized))
            ).scalar_one_or_none()
            if user is not None and user.is_active:
                reset_token = (
                    await self.db.execute(
                        select(PasswordResetToken)
                        .where(
                            PasswordResetToken.user_id == user.id,
                            PasswordResetToken.purpose == "password_reset",
                            PasswordResetToken.used_at.is_(None),
                            PasswordResetToken.expires_at > now,
                        )
                        .order_by(PasswordResetToken.created_at.desc())
                        .limit(1)
                        .with_for_update()
                    )
                ).scalar_one_or_none()
            expected = (
                hmac.new(
                    self.settings.jwt_secret_key.encode(),
                    f"{user.id}:{code}".encode(),
                    hashlib.sha256,
                ).hexdigest()
                if user is not None
                else "0" * 64
            )
            if (
                reset_token is None
                or user is None
                or not user.is_active
                or not hmac.compare_digest(reset_token.token_hash, expected)
            ):
                raise AppError("Invalid or expired reset credential", code="INVALID_RESET_TOKEN")

        if reset_token is None or user is None or not user.is_active:
            raise AppError("Invalid or expired reset credential", code="INVALID_RESET_TOKEN")

        user.password_hash = await security.hash_password(new_password)
        user.email_verified = True  # the OTP or invitation link proves control of the mailbox
        reset_token.used_at = now
        await self._revoke_sessions(user.id, "password_reset")
        await rate_limit.reset(self.redis, "login-fail", user.email.lower())
        if normalized is not None:
            await rate_limit.reset(self.redis, "password-reset-otp", normalized)
        if token_digest is not None:
            await rate_limit.reset(self.redis, "password-reset-invite", token_digest)

    async def change_password(self, principal: Principal, current: str, new: str) -> int:
        if not await security.verify_password(principal.user.password_hash, current):
            raise AppError("Current password is incorrect", code="INVALID_CREDENTIALS")
        principal.user.password_hash = await security.hash_password(new)
        return await self._revoke_sessions(
            principal.user_id, "password_change", keep=principal.session_id
        )

    # ───────────────────────── sessions ─────────────────────────

    async def list_sessions(self, principal: Principal) -> list[SessionOut]:
        rows = await self.db.execute(
            select(AuthSession)
            .where(
                AuthSession.user_id == principal.user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(UTC),
            )
            .order_by(AuthSession.last_seen_at.desc())
        )
        return [
            SessionOut(
                id=s.id,
                user_agent=s.user_agent,
                ip_address=s.ip_address,
                created_at=s.created_at,
                last_seen_at=s.last_seen_at,
                is_current=s.id == principal.session_id,
            )
            for s in rows.scalars().all()
        ]

    async def revoke_session(self, principal: Principal, session_id: uuid.UUID) -> None:
        # Scoped to the caller's own user id: another user's session id is simply "not found".
        if not await self._revoke_sessions(principal.user_id, "user_revoked", only=session_id):
            raise NotFoundError("Session not found")

    async def revoke_other_sessions(self, principal: Principal) -> int:
        return await self._revoke_sessions(
            principal.user_id, "user_revoked", keep=principal.session_id
        )
