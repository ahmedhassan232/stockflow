from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.core.redis import get_redis
from app.core.responses import ErrorBody, ErrorResponse, SuccessResponse, ok
from app.db.session import get_engine
from app.modules.health.schemas import LivenessData, ReadinessData
from app.modules.health.service import HealthService

router = APIRouter(prefix="/health", tags=["Health"])


def get_health_service(
    settings: Settings = Depends(get_settings),
    engine: AsyncEngine = Depends(get_engine),
    redis: Redis = Depends(get_redis),
) -> HealthService:
    return HealthService(settings, engine, redis)


@router.get(
    "/live",
    response_model=SuccessResponse[LivenessData],
    summary="Liveness probe – the process is running",
)
async def live(service: HealthService = Depends(get_health_service)):
    return ok(service.liveness(), "Service is alive")


@router.get(
    "/ready",
    response_model=SuccessResponse[ReadinessData],
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse}},
    summary="Readiness probe – PostgreSQL and Redis are reachable",
)
async def ready(service: HealthService = Depends(get_health_service)):
    result = await service.readiness()
    if result.status == "ok":
        return ok(result, "All dependencies are healthy")
    body = ErrorResponse(
        error=ErrorBody(
            code="SERVICE_UNAVAILABLE",
            message="One or more dependencies are unavailable",
            details=result,
        )
    )
    return JSONResponse(status_code=503, content=jsonable_encoder(body, exclude_none=True))
