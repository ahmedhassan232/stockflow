import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.rate_limit import auth_rate_limit, client_ip
from app.core.redis import get_redis
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.auth.dependencies import Principal, get_principal, verify_origin
from app.modules.auth.schemas import (
    AuthOut,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeOut,
    ProfileUpdate,
    RegisterRequest,
    ResetPasswordRequest,
    SelectCompanyRequest,
    SessionOut,
    TokenOut,
    UserOut,
    VerifyEmailRequest,
)
from app.modules.auth.service import AuthService, ClientMeta, IssuedTokens

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(db, redis, settings)


def _meta(request: Request) -> ClientMeta:
    return ClientMeta(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


def _cookie_path(settings: Settings) -> str:
    return f"{settings.api_v1_prefix}/auth"  # the cookie is sent ONLY to auth endpoints


def _set_refresh_cookie(response: Response, settings: Settings, raw: str) -> None:
    response.set_cookie(
        settings.refresh_cookie_name,
        raw,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,  # unreadable from JavaScript
        secure=settings.cookie_secure_effective,
        samesite=settings.cookie_samesite,
        path=_cookie_path(settings),
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=_cookie_path(settings),
        httponly=True,
        secure=settings.cookie_secure_effective,
        samesite=settings.cookie_samesite,
    )


def _auth_out(t: IssuedTokens) -> AuthOut:
    return AuthOut(
        access_token=t.access_token,
        expires_in=t.expires_in,
        active_tenant_id=t.active_tenant_id,
        user=UserOut.model_validate(t.user),
        memberships=t.memberships,
    )


@router.post(
    "/register",
    response_model=SuccessResponse[AuthOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limit)],
    summary="Register a user and their company",
)
async def register(
    data: RegisterRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
):
    tokens = await service.register(data, _meta(request))
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return ok(_auth_out(tokens), "Company registered successfully")


@router.post(
    "/login", response_model=SuccessResponse[AuthOut], dependencies=[Depends(auth_rate_limit)]
)
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
):
    tokens = await service.login(data.email, data.password, _meta(request))
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return ok(_auth_out(tokens), "Signed in")


@router.post(
    "/refresh",
    response_model=SuccessResponse[AuthOut],
    dependencies=[Depends(verify_origin), Depends(auth_rate_limit)],
    summary="Rotate the refresh token (HttpOnly cookie) and get a new access token",
)
async def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
):
    tokens = await service.refresh(request.cookies.get(settings.refresh_cookie_name))
    _set_refresh_cookie(response, settings, tokens.refresh_token)
    return ok(_auth_out(tokens))


@router.post("/logout", response_model=SuccessResponse[None], dependencies=[Depends(verify_origin)])
async def logout(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
):
    await service.logout(request.cookies.get(settings.refresh_cookie_name))
    _clear_refresh_cookie(response, settings)
    return ok(None, "Signed out")


@router.post(
    "/forgot-password",
    response_model=SuccessResponse[None],
    dependencies=[Depends(auth_rate_limit)],
)
async def forgot_password(
    data: ForgotPasswordRequest, service: AuthService = Depends(get_auth_service)
):
    await service.forgot_password(data.email)
    return ok(None, "If the email is registered, a reset code has been sent")


@router.post(
    "/reset-password",
    response_model=SuccessResponse[None],
    dependencies=[Depends(auth_rate_limit)],
)
async def reset_password(
    data: ResetPasswordRequest, service: AuthService = Depends(get_auth_service)
):
    await service.reset_password(data.email, data.code, data.new_password)
    return ok(None, "Password updated. Please sign in again")


@router.post(
    "/verify-email", response_model=SuccessResponse[None], dependencies=[Depends(auth_rate_limit)]
)
async def verify_email(data: VerifyEmailRequest, service: AuthService = Depends(get_auth_service)):
    await service.verify_email(data.token)
    return ok(None, "E-mail confirmed")


@router.post(
    "/resend-verification",
    response_model=SuccessResponse[None],
    dependencies=[Depends(auth_rate_limit)],
)
async def resend_verification(
    principal: Principal = Depends(get_principal),
    service: AuthService = Depends(get_auth_service),
):
    await service.resend_verification(principal)
    return ok(None, "Confirmation e-mail sent")


@router.post("/change-password", response_model=SuccessResponse[None])
async def change_password(
    data: ChangePasswordRequest,
    principal: Principal = Depends(get_principal),
    service: AuthService = Depends(get_auth_service),
):
    await service.change_password(principal, data.current_password, data.new_password)
    return ok(None, "Password changed. Other devices were signed out")


@router.get("/me", response_model=SuccessResponse[MeOut])
async def me(
    principal: Principal = Depends(get_principal), service: AuthService = Depends(get_auth_service)
):
    return ok(await service.me(principal))


@router.patch("/me", response_model=SuccessResponse[UserOut])
async def update_me(
    data: ProfileUpdate,
    principal: Principal = Depends(get_principal),
    service: AuthService = Depends(get_auth_service),
):
    user = await service.update_profile(principal, data)
    return ok(UserOut.model_validate(user), "Profile updated")


@router.post(
    "/select-company",
    response_model=SuccessResponse[TokenOut],
    summary="Switch the active company (must be one of the caller's active memberships)",
)
async def select_company(
    data: SelectCompanyRequest,
    principal: Principal = Depends(get_principal),
    service: AuthService = Depends(get_auth_service),
):
    token, ttl, access = await service.select_company(principal, data.tenant_id)
    return ok(TokenOut(access_token=token, expires_in=ttl, active_tenant_id=access.tenant_id))


@router.get("/sessions", response_model=SuccessResponse[list[SessionOut]])
async def list_sessions(
    principal: Principal = Depends(get_principal), service: AuthService = Depends(get_auth_service)
):
    return ok(await service.list_sessions(principal))


@router.post("/sessions/revoke-others", response_model=SuccessResponse[dict[str, int]])
async def revoke_other_sessions(
    principal: Principal = Depends(get_principal), service: AuthService = Depends(get_auth_service)
):
    return ok({"revoked": await service.revoke_other_sessions(principal)})


@router.delete("/sessions/{session_id}", response_model=SuccessResponse[None])
async def revoke_session(
    session_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    service: AuthService = Depends(get_auth_service),
):
    await service.revoke_session(principal, session_id)
    return ok(None, "Session revoked")
