from sqlalchemy import Boolean, String, Text, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Global identity. Deliberately has NO tenant_id: one person may belong to several
    companies through `memberships`. Only the auth/user repositories may query it."""

    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    # NULL until the user sets a password (e.g. invited employee). Argon2id from Phase 3.
    password_hash: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # Operator of the whole platform (can list / suspend companies). Granted only by the
    # CLI `python -m app.scripts.platform_admin`, never through the API.
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
