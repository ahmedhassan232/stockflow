import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.responses import SuccessResponse, ok
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.authorization.service import TenantAccess
from app.modules.team.schemas import (
    EmployeeInvite,
    EmployeeOut,
    EmployeeUpdate,
    PermissionOut,
    RoleIn,
    RoleOut,
    SettingsOut,
    SettingsUpdate,
)
from app.modules.team.service import TeamService

employees_router = APIRouter(prefix="/employees", tags=["Employees"])
roles_router = APIRouter(prefix="/roles", tags=["Roles & permissions"])
settings_router = APIRouter(prefix="/settings", tags=["Company settings"])


def _service(permission: str):
    def factory(
        access: TenantAccess = Depends(require_permission(permission)),
        db: AsyncSession = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> TeamService:
        return TeamService(db, access, settings)

    return factory


@employees_router.get("", response_model=SuccessResponse[list[EmployeeOut]])
async def list_employees(service: TeamService = Depends(_service("employees.view"))):
    return ok(await service.list_employees())


@employees_router.post(
    "", response_model=SuccessResponse[EmployeeOut], status_code=status.HTTP_201_CREATED
)
async def invite_employee(
    data: EmployeeInvite, service: TeamService = Depends(_service("employees.manage"))
):
    return ok(await service.invite(data), "Invitation sent")


@employees_router.patch("/{membership_id}", response_model=SuccessResponse[EmployeeOut])
async def update_employee(
    membership_id: uuid.UUID,
    data: EmployeeUpdate,
    service: TeamService = Depends(_service("employees.manage")),
):
    return ok(await service.update_employee(membership_id, data), "Employee updated")


@employees_router.delete("/{membership_id}", response_model=SuccessResponse[None])
async def remove_employee(
    membership_id: uuid.UUID, service: TeamService = Depends(_service("employees.manage"))
):
    await service.remove_employee(membership_id)
    return ok(None, "Employee removed")


@roles_router.get("", response_model=SuccessResponse[list[RoleOut]])
async def list_roles(service: TeamService = Depends(_service("employees.view"))):
    return ok(await service.list_roles())


@roles_router.get("/permissions", response_model=SuccessResponse[list[PermissionOut]])
async def list_permissions(service: TeamService = Depends(_service("employees.view"))):
    return ok(service.permission_catalogue())


@roles_router.post("", response_model=SuccessResponse[RoleOut], status_code=status.HTTP_201_CREATED)
async def create_role(data: RoleIn, service: TeamService = Depends(_service("roles.manage"))):
    return ok(await service.create_role(data), "Role created")


@roles_router.put("/{role_id}", response_model=SuccessResponse[RoleOut])
async def update_role(
    role_id: uuid.UUID, data: RoleIn, service: TeamService = Depends(_service("roles.manage"))
):
    return ok(await service.update_role(role_id, data), "Role updated")


@roles_router.delete("/{role_id}", response_model=SuccessResponse[None])
async def delete_role(role_id: uuid.UUID, service: TeamService = Depends(_service("roles.manage"))):
    await service.delete_role(role_id)
    return ok(None, "Role deleted")


@settings_router.get("", response_model=SuccessResponse[SettingsOut])
async def get_company_settings(service: TeamService = Depends(_service("settings.view"))):
    return ok(await service.get_settings())


@settings_router.patch("", response_model=SuccessResponse[SettingsOut])
async def update_company_settings(
    data: SettingsUpdate, service: TeamService = Depends(_service("settings.update"))
):
    return ok(await service.update_settings(data), "Settings saved")
