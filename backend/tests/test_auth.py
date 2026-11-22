import re
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import text

from app.core import email as email_module
from app.db.tenant import TenantContext, context_transaction
from tests.api_helpers import API, PASSWORD, bearer, login, new_client, register_company
from tests.factories import unique


def _register_payload(**over):
    base = {
        "full_name": "Sara Ali",
        "email": f"{unique('u')}@example.com",
        "password": PASSWORD,
        "company": {"name": "Nile Trading", "slug": unique("nile")},
    }
    base.update(over)
    return base


async def _db(sql: str, **params):
    async with context_transaction(TenantContext()) as s:
        result = await s.execute(text(sql), params)
        return result.all() if result.returns_rows else result.rowcount


# ───────────────────────── registration ─────────────────────────


async def test_register_creates_user_company_and_owner_session(client):
    payload = _register_payload()
    r = await client.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["token_type"] == "bearer" and data["expires_in"] == 900
    assert "password" not in r.text and "hash" not in r.text

    cookie = r.headers["set-cookie"]
    assert cookie.startswith("sf_refresh=")
    assert "HttpOnly" in cookie and "Path=/api/v1/auth" in cookie and "SameSite=lax" in cookie

    me = (await client.get(f"{API}/auth/me", headers=bearer(data["access_token"]))).json()["data"]
    company = me["active_company"]
    assert company["name"] == "Nile Trading" and company["role_code"] == "owner"
    assert company["currency"] == "EGP"
    assert "employees.manage" in company["permissions"] and len(company["permissions"]) >= 30
    assert [m["tenant_name"] for m in me["memberships"]] == ["Nile Trading"]

    [(stored,)] = await _db("SELECT password_hash FROM users WHERE email = :e", e=payload["email"])
    assert stored.startswith("$argon2id$") and PASSWORD not in stored


async def test_register_is_atomic_when_company_slug_is_taken(client, app):
    existing = _register_payload()
    assert (await client.post(f"{API}/auth/register", json=existing)).status_code == 201

    payload = _register_payload(company={"name": "Dup", "slug": existing["company"]["slug"]})
    r = await new_client(app).post(f"{API}/auth/register", json=payload)
    assert r.status_code == 409
    # The user row created earlier in the same request was rolled back with it.
    assert await _db("SELECT 1 FROM users WHERE email = :e", e=payload["email"]) == []
    payload["company"]["slug"] = unique("free")
    assert (await new_client(app).post(f"{API}/auth/register", json=payload)).status_code == 201


async def test_register_rejects_duplicate_email_case_insensitively(client, app):
    payload = _register_payload()
    await client.post(f"{API}/auth/register", json=payload)
    again = _register_payload(email=payload["email"].upper())
    r = await new_client(app).post(f"{API}/auth/register", json=again)
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"
    assert await _db("SELECT 1 FROM tenants WHERE slug = :s", s=again["company"]["slug"]) == []


async def test_register_validation_and_mass_assignment(client):
    for bad in (
        _register_payload(password="short"),
        _register_payload(email="not-an-email"),
        _register_payload(is_active=False),
        _register_payload(company={"name": "X Co", "slug": unique("x"), "status": "active"}),
    ):
        r = await client.post(f"{API}/auth/register", json=bad)
        assert r.status_code == 422, bad
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"


# ───────────────────────── login ─────────────────────────


async def test_login_success_and_identical_failures(app, client):
    owner = await register_company(app)
    ok = await client.post(f"{API}/auth/login", json={"email": owner.email, "password": PASSWORD})
    assert ok.status_code == 200
    assert ok.json()["data"]["active_tenant_id"] == str(owner.tenant_id)  # single company

    wrong = await client.post(
        f"{API}/auth/login", json={"email": owner.email, "password": "nope-nope-nope"}
    )
    unknown = await client.post(
        f"{API}/auth/login", json={"email": "ghost@example.com", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # nothing reveals whether the e-mail exists
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_is_locked_after_repeated_failures(app, client):
    owner = await register_company(app)
    for _ in range(5):
        r = await client.post(
            f"{API}/auth/login", json={"email": owner.email, "password": "wrong-wrong-1"}
        )
        assert r.status_code == 401
    locked = await client.post(
        f"{API}/auth/login", json={"email": owner.email, "password": PASSWORD}
    )
    assert locked.status_code == 429 and locked.json()["error"]["code"] == "LOGIN_LOCKED"


async def test_auth_endpoints_are_rate_limited_per_ip(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 3)
    body = {"email": "nobody@example.com", "password": "whatever-123"}
    codes = [(await client.post(f"{API}/auth/login", json=body)).status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]


async def test_disabled_account_cannot_login_or_use_existing_token(app, client):
    owner = await register_company(app)
    await _db("UPDATE users SET is_active = false WHERE id = :i", i=owner.user_id)
    r = await client.get(f"{API}/auth/me", headers=owner.h)
    assert r.status_code == 401 and r.json()["error"]["code"] == "ACCOUNT_DISABLED"
    r = await client.post(f"{API}/auth/login", json={"email": owner.email, "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_CREDENTIALS"


# ───────────────────────── access tokens ─────────────────────────


async def test_access_token_validation(app, client, settings):
    owner = await register_company(app)
    claims = jwt.decode(
        owner.token, settings.jwt_secret_key, algorithms=["HS256"], issuer="stockflow"
    )
    now = datetime.now(UTC)

    def forge(key=settings.jwt_secret_key, alg="HS256", **over):
        return jwt.encode({**claims, **over}, key, algorithm=alg)

    cases = {
        "missing": None,
        "garbage": "not.a.jwt",
        "wrong key": forge(key="x" * 40),
        "alg none": forge(key=None, alg="none"),
        "expired": forge(exp=now - timedelta(seconds=5)),
        "wrong type": forge(typ="refresh"),
        "wrong issuer": forge(iss="someone-else"),
        "unknown session": forge(sid=str(uuid.uuid4())),
        "other user's id": forge(sub=str(uuid.uuid4())),
    }
    for name, token in cases.items():
        r = await client.get(f"{API}/auth/me", headers=bearer(token) if token else {})
        assert r.status_code == 401, name
        assert r.json()["success"] is False
    assert (await client.get(f"{API}/auth/me", headers=owner.h)).status_code == 200


# ───────────────────────── refresh rotation ─────────────────────────


async def test_refresh_rotates_token_and_old_one_is_single_use(app):
    owner = await register_company(app)
    c = owner.client
    first = c.cookies.get("sf_refresh")
    r = await c.post(f"{API}/auth/refresh")
    assert r.status_code == 200
    second = c.cookies.get("sf_refresh")
    assert second and second != first
    assert (
        await c.get(f"{API}/auth/me", headers=bearer(r.json()["data"]["access_token"]))
    ).status_code == 200
    # Raw tokens are never stored.
    assert (
        await _db("SELECT 1 FROM refresh_tokens WHERE token_hash IN (:a, :b)", a=first, b=second)
        == []
    )


async def test_replaying_an_old_refresh_token_revokes_the_whole_session(app):
    owner = await register_company(app)
    c = owner.client
    stolen = c.cookies.get("sf_refresh")
    fresh_access = (await c.post(f"{API}/auth/refresh")).json()["data"]["access_token"]
    # Move the rotation outside the short "two tabs" grace window.
    await _db(
        "UPDATE refresh_tokens SET revoked_at = revoked_at - interval '1 minute' "
        "WHERE revoked_at IS NOT NULL AND user_id = :u",
        u=owner.user_id,
    )

    thief = new_client(app)
    thief.cookies.set("sf_refresh", stolen)
    r = await thief.post(f"{API}/auth/refresh")
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_REUSED"

    # The legitimate user's newer tokens are dead too – both parties must log in again.
    assert (await c.post(f"{API}/auth/refresh")).status_code == 401
    r = await c.get(f"{API}/auth/me", headers=bearer(fresh_access))
    assert r.status_code == 401 and r.json()["error"]["code"] == "SESSION_REVOKED"


async def test_simultaneous_refresh_is_not_treated_as_theft(app):
    owner = await register_company(app)
    c = owner.client
    old = c.cookies.get("sf_refresh")
    assert (await c.post(f"{API}/auth/refresh")).status_code == 200
    other_tab = new_client(app)
    other_tab.cookies.set("sf_refresh", old)
    r = await other_tab.post(f"{API}/auth/refresh")
    assert r.status_code == 401 and r.json()["error"]["code"] == "REFRESH_RACE"
    assert (await c.post(f"{API}/auth/refresh")).status_code == 200  # session survived


async def test_refresh_requires_cookie_and_same_site_origin(app, client):
    r = await client.post(f"{API}/auth/refresh")
    assert r.status_code == 401
    owner = await register_company(app)
    r = await owner.client.post(f"{API}/auth/refresh", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_REJECTED"
    r = await owner.client.post(f"{API}/auth/refresh", headers={"Origin": "http://testserver"})
    assert r.status_code == 200


async def test_logout_kills_access_and_refresh_immediately(app):
    owner = await register_company(app)
    c = owner.client
    kept = c.cookies.get("sf_refresh")
    r = await c.post(f"{API}/auth/logout")
    assert r.status_code == 200 and 'sf_refresh=""' in r.headers["set-cookie"]
    assert (await c.get(f"{API}/auth/me", headers=owner.h)).status_code == 401
    c.cookies.set("sf_refresh", kept)
    assert (await c.post(f"{API}/auth/refresh")).status_code == 401
    assert (await c.post(f"{API}/auth/logout")).status_code == 200  # idempotent


# ───────────────────────── passwords ─────────────────────────


async def test_forgot_and_reset_password_flow(app, client):
    owner = await register_company(app)
    r1 = await client.post(f"{API}/auth/forgot-password", json={"email": owner.email})
    r2 = await client.post(f"{API}/auth/forgot-password", json={"email": "ghost@example.com"})
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    assert len(email_module.outbox) == 2 and email_module.outbox[-1].to == owner.email
    code = re.search(r"(?<!\d)\d{6}(?!\d)", email_module.outbox[-1].body).group()
    stored = await _db(
        "SELECT token_hash FROM password_reset_tokens WHERE user_id = :u AND purpose = 'password_reset'",
        u=owner.user_id,
    )
    assert (
        len(stored) == 1 and stored[0]["token_hash"] != code and len(stored[0]["token_hash"]) == 64
    )

    new_password = "a brand new passphrase"
    weak = await client.post(
        f"{API}/auth/reset-password",
        json={"email": owner.email, "code": code, "new_password": "x"},
    )
    assert weak.status_code == 422
    done = await client.post(
        f"{API}/auth/reset-password",
        json={"email": owner.email, "code": code, "new_password": new_password},
    )
    assert done.status_code == 200

    # Every existing session is signed out; old password is dead; OTP is single-use.
    assert (await client.get(f"{API}/auth/me", headers=owner.h)).status_code == 401
    assert (await owner.client.post(f"{API}/auth/refresh")).status_code == 401
    old = await client.post(f"{API}/auth/login", json={"email": owner.email, "password": PASSWORD})
    assert old.status_code == 401
    again = await client.post(
        f"{API}/auth/reset-password",
        json={"email": owner.email, "code": code, "new_password": "yet another phrase"},
    )
    assert again.status_code == 400 and again.json()["error"]["code"] == "INVALID_RESET_TOKEN"
    await login(app, owner.email, new_password)


async def test_expired_reset_otp_is_rejected(app, client):
    owner = await register_company(app)
    await client.post(f"{API}/auth/forgot-password", json={"email": owner.email})
    code = re.search(r"(?<!\d)\d{6}(?!\d)", email_module.outbox[-1].body).group()
    await _db(
        "UPDATE password_reset_tokens SET expires_at = now() - interval '1 second' "
        "WHERE user_id = :u AND purpose = 'password_reset'",
        u=owner.user_id,
    )
    r = await client.post(
        f"{API}/auth/reset-password",
        json={"email": owner.email, "code": code, "new_password": "a brand new passphrase"},
    )
    assert r.status_code == 400


async def test_change_password_keeps_current_session_and_revokes_others(app):
    owner = await register_company(app)
    other_device = await login(app, owner.email)
    c = owner.client
    bad = await c.post(
        f"{API}/auth/change-password",
        headers=owner.h,
        json={"current_password": "wrong-wrong-1", "new_password": "new long passphrase"},
    )
    assert bad.status_code == 400
    good = await c.post(
        f"{API}/auth/change-password",
        headers=owner.h,
        json={"current_password": PASSWORD, "new_password": "new long passphrase"},
    )
    assert good.status_code == 200
    assert (await c.get(f"{API}/auth/me", headers=owner.h)).status_code == 200
    assert (await c.get(f"{API}/auth/me", headers=other_device.h)).status_code == 401
    await login(app, owner.email, "new long passphrase")


# ───────────────────────── sessions & profile ─────────────────────────


async def test_sessions_can_be_listed_and_revoked_but_only_your_own(app):
    owner = await register_company(app)
    phone = await login(app, owner.email)
    stranger = await register_company(app, "Other")
    c = owner.client

    sessions = (await c.get(f"{API}/auth/sessions", headers=owner.h)).json()["data"]
    assert len(sessions) == 2 and sum(s["is_current"] for s in sessions) == 1
    phone_session = next(s["id"] for s in sessions if not s["is_current"])

    # A stranger cannot revoke (or even confirm the existence of) someone else's session.
    r = await stranger.client.delete(f"{API}/auth/sessions/{phone_session}", headers=stranger.h)
    assert r.status_code == 404
    assert (await c.get(f"{API}/auth/me", headers=phone.h)).status_code == 200

    assert (
        await c.delete(f"{API}/auth/sessions/{phone_session}", headers=owner.h)
    ).status_code == 200
    assert (await c.get(f"{API}/auth/me", headers=phone.h)).status_code == 401

    await login(app, owner.email)
    r = await c.post(f"{API}/auth/sessions/revoke-others", headers=owner.h)
    assert r.json()["data"] == {"revoked": 1}


async def test_profile_update_only_touches_allowed_fields(app):
    owner = await register_company(app)
    c = owner.client
    r = await c.patch(
        f"{API}/auth/me", headers=owner.h, json={"full_name": "New Name", "phone": "0100"}
    )
    assert r.status_code == 200 and r.json()["data"]["full_name"] == "New Name"
    for forbidden in ({"email": "x@example.com"}, {"is_active": False}, {"password_hash": "x"}):
        assert (await c.patch(f"{API}/auth/me", headers=owner.h, json=forbidden)).status_code == 422
