"""FastAPI dependency accessors for application services."""

from fastapi import Request

from movie_language_helper.infrastructure.container import AppServices


async def get_services(request: Request) -> AppServices:
    """Return the process-owned service container."""
    services: AppServices = request.app.state.services
    return services
