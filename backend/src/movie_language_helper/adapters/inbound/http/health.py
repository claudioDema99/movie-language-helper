"""Process-health endpoints that never call external providers."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict

from movie_language_helper.adapters.inbound.http.dependencies import get_services
from movie_language_helper.infrastructure.container import AppServices

router = APIRouter(prefix="/health", tags=["health"])
metrics_router = APIRouter()


class HealthResponse(BaseModel):
    """Stable response shared by health probes."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


@router.get(
    "/live",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check process liveness",
)
async def liveness() -> HealthResponse:
    """Report that the API process can serve requests."""
    return HealthResponse()


@router.get(
    "/ready",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check process readiness",
)
async def readiness() -> HealthResponse:
    """Report readiness for the provider-free local process."""
    return HealthResponse()


@metrics_router.get("/metrics", include_in_schema=False)
async def metrics(
    services: Annotated[AppServices, Depends(get_services)],
) -> Response:
    """Expose content-free Prometheus text metrics."""
    return Response(
        services.metrics.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
