from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Status = Literal["ok", "error"]


class LivenessData(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
    time: datetime


class ComponentHealth(BaseModel):
    status: Status
    latency_ms: float | None = None
    detail: str | None = None  # generic, client-safe text only


class DatabaseHealth(ComponentHealth):
    server_version: str | None = None
    schema_revision: str | None = None
    # True when the runtime role can NOT bypass Row Level Security.
    rls_enforced_for_role: bool | None = None


class ReadinessData(BaseModel):
    status: Status
    database: DatabaseHealth
    redis: ComponentHealth
    time: datetime
