"""Password hashing (Argon2id), access tokens (JWT) and opaque token helpers."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from anyio import to_thread
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.core.exceptions import UnauthenticatedError

JWT_ALGORITHM = "HS256"


@lru_cache
def _hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(
        time_cost=s.argon2_time_cost, memory_cost=s.argon2_memory_kib, parallelism=1, type=Type.ID
    )


@lru_cache
def _dummy_hash() -> str:
    return _hasher().hash(secrets.token_urlsafe(16))


def _verify(password_hash: str | None, password: str) -> bool:
    # Unknown user / no password: still spend the same hashing time (no user enumeration
    # through response timing), then fail.
    target = password_hash or _dummy_hash()
    try:
        ok = _hasher().verify(target, password)
    except (VerificationError, InvalidHashError):
        return False
    return ok and password_hash is not None


async def hash_password(password: str) -> str:
    return await to_thread.run_sync(_hasher().hash, password)  # CPU-bound: off the event loop


async def verify_password(password_hash: str | None, password: str) -> bool:
    return await to_thread.run_sync(_verify, password_hash, password)


def needs_rehash(password_hash: str) -> bool:
    return _hasher().check_needs_rehash(password_hash)


def new_opaque_token() -> tuple[str, str]:
    """Returns (raw token for the client, SHA-256 hash for the database)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID | None


def create_access_token(
    *, user_id: uuid.UUID, session_id: uuid.UUID, tenant_id: uuid.UUID | None
) -> tuple[str, int]:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "iss": s.jwt_issuer,
        "sub": str(user_id),
        "sid": str(session_id),
        "tid": str(tenant_id) if tenant_id else None,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(seconds=s.access_token_ttl_seconds),
    }
    token = jwt.encode(payload, s.jwt_secret_key, algorithm=JWT_ALGORITHM)
    return token, s.access_token_ttl_seconds


def decode_access_token(token: str) -> AccessClaims:
    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            s.jwt_secret_key,
            algorithms=[JWT_ALGORITHM],  # pinned: no "none", no algorithm confusion
            issuer=s.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "sid", "iss"]},
        )
        if payload.get("typ") != "access":
            raise jwt.InvalidTokenError("wrong token type")
        tid = payload.get("tid")
        return AccessClaims(
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(payload["sid"]),
            tenant_id=uuid.UUID(tid) if tid else None,
        )
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise UnauthenticatedError("Invalid or expired access token") from exc
