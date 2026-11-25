"""Correlation, no-store, and content-free request logging middleware."""

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from movie_language_helper.adapters.inbound.http.errors import error_response
from movie_language_helper.infrastructure.container import AppServices
from movie_language_helper.infrastructure.security import (
    FixedWindowRateLimiter,
    bearer_token,
    client_key,
    token_matches,
)

logger = logging.getLogger("movie_language_helper.http")
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,100}")


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach a safe correlation ID and log metadata only."""
    supplied = request.headers.get("X-Request-ID", "")
    correlation_id = supplied if REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
    request.state.correlation_id = correlation_id
    started = time.perf_counter()
    services: AppServices = request.app.state.services
    settings = services.settings
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_bytes = int(content_length)
        except ValueError:
            declared_bytes = settings.request_max_bytes + 1
        if declared_bytes > settings.request_max_bytes:
            return _rejected(
                request,
                error_response(
                    request,
                    code="resource_limit_exceeded",
                    message="Request body exceeds the configured byte limit.",
                    retryable=False,
                    status_code=413,
                ),
                correlation_id,
                services,
                started,
                "resource_limit_exceeded",
            )
    if settings.deployment_profile == "private" and request.url.path.startswith(
        ("/api/v1", "/metrics")
    ):
        assert settings.private_access_token is not None
        token = bearer_token(request.headers.get("authorization"))
        if not token_matches(token, settings.private_access_token.get_secret_value()):
            return _rejected(
                request,
                error_response(
                    request,
                    code="unauthorized",
                    message="Valid private-deployment authentication is required.",
                    retryable=False,
                    status_code=401,
                ),
                correlation_id,
                services,
                started,
                "unauthorized",
            )
        peer = request.client.host if request.client is not None else "unknown"
        key = client_key(request.headers.get("x-forwarded-for"), peer)
        limiter: FixedWindowRateLimiter = request.app.state.rate_limiter
        retry_after = limiter.check(key)
        if retry_after is not None:
            limited_response = error_response(
                request,
                code="rate_limited",
                message="Request rate limit exceeded.",
                retryable=True,
                status_code=429,
            )
            limited_response.headers["Retry-After"] = str(retry_after)
            return _rejected(
                request,
                limited_response,
                correlation_id,
                services,
                started,
                "rate_limited",
            )
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = correlation_id
    if request.url.path.startswith(("/api/v1/transcript-sessions", "/api/v1/analyses")):
        response.headers["Cache-Control"] = "no-store"
    _security_headers(response, request.url.path)
    services.metrics.observe_http(
        request.method, request.url.path, response.status_code, duration_ms
    )
    logger.info(
        "request_complete method=%s path=%s status=%d duration_ms=%d correlation_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        correlation_id,
    )
    return response


def _secured(response: Response, correlation_id: str) -> Response:
    response.headers["X-Request-ID"] = correlation_id
    response.headers["Cache-Control"] = "no-store"
    _security_headers(response, "/api/v1")
    return response


def _rejected(
    request: Request,
    response: Response,
    correlation_id: str,
    services: AppServices,
    started: float,
    error_code: str,
) -> Response:
    duration_ms = round((time.perf_counter() - started) * 1000)
    secured = _secured(response, correlation_id)
    services.metrics.observe_http(
        request.method, request.url.path, secured.status_code, duration_ms
    )
    services.metrics.observe_error(error_code)
    logger.info(
        "request_rejected method=%s path=%s status=%d duration_ms=%d "
        "correlation_id=%s error_code=%s",
        request.method,
        request.url.path,
        secured.status_code,
        duration_ms,
        correlation_id,
        error_code,
    )
    return secured


def _security_headers(response: Response, path: str) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if path.startswith(("/api/", "/metrics")):
        response.headers["Content-Security-Policy"] = "default-src 'none'"
