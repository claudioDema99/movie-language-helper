"""FastAPI application factory and composition boundary."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from movie_language_helper import __version__
from movie_language_helper.adapters.inbound.http.analyses import (
    router as analyses_router,
)
from movie_language_helper.adapters.inbound.http.catalog import router as catalog_router
from movie_language_helper.adapters.inbound.http.errors import (
    application_error_handler,
    validation_error_handler,
)
from movie_language_helper.adapters.inbound.http.health import metrics_router
from movie_language_helper.adapters.inbound.http.health import router as health_router
from movie_language_helper.adapters.inbound.http.middleware import (
    request_context_middleware,
)
from movie_language_helper.adapters.inbound.http.transcripts import (
    router as transcripts_router,
)
from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.infrastructure.config import Settings
from movie_language_helper.infrastructure.container import AppServices, build_services
from movie_language_helper.infrastructure.security import FixedWindowRateLimiter


def create_app(
    settings: Settings | None = None,
    services: AppServices | None = None,
) -> FastAPI:
    """Build a fresh application instance for a server or test process."""
    resolved_settings = settings or (
        services.settings if services is not None else Settings()
    )
    resolved_services = services or build_services(resolved_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await resolved_services.cleanup_sessions.execute()
        for close_resource in resolved_services.resource_closers:
            await close_resource()

    app = FastAPI(
        title="Movie Language Helper API",
        description="Backend API for Movie Language Helper.",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.services = resolved_services
    app.state.rate_limiter = FixedWindowRateLimiter(
        resolved_settings.rate_limit_requests,
        resolved_settings.rate_limit_window_seconds,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(resolved_settings.trusted_hosts),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.middleware("http")(request_context_middleware)
    app.add_exception_handler(ApplicationError, application_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(transcripts_router)
    app.include_router(analyses_router)
    app.include_router(catalog_router)
    return app
