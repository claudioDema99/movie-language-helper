"""Stable safe HTTP error mapping."""

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from movie_language_helper.adapters.inbound.http.schemas import (
    ErrorDetail,
    ErrorResponse,
)
from movie_language_helper.application.errors import ApplicationError

STATUS_BY_CODE = {
    "invalid_request": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "invalid_value": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "invalid_range": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "invalid_sync_offset": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "invalid_item_limit": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "unsupported_subtitle": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "subtitle_parse_failed": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "resource_limit_exceeded": status.HTTP_413_CONTENT_TOO_LARGE,
    "session_not_found": status.HTTP_404_NOT_FOUND,
    "session_expired": status.HTTP_410_GONE,
    "empty_interval": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "analyzer_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "analyzer_rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "analyzer_refused": status.HTTP_502_BAD_GATEWAY,
    "analyzer_incomplete": status.HTTP_502_BAD_GATEWAY,
    "analyzer_invalid_output": status.HTTP_502_BAD_GATEWAY,
    "provider_disabled": status.HTTP_503_SERVICE_UNAVAILABLE,
    "provider_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "provider_rate_limited": status.HTTP_429_TOO_MANY_REQUESTS,
    "provider_invalid_response": status.HTTP_502_BAD_GATEWAY,
    "provider_resource_limit": status.HTTP_413_CONTENT_TOO_LARGE,
    "provider_invalid_archive": status.HTTP_502_BAD_GATEWAY,
}


def _correlation_id(request: Request) -> str:
    value: str = getattr(request.state, "correlation_id", "unavailable")
    return value


def error_response(
    request: Request,
    *,
    code: str,
    message: str,
    retryable: bool,
    status_code: int,
) -> JSONResponse:
    """Build the one public error envelope."""
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            correlation_id=_correlation_id(request),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


async def application_error_handler(
    request: Request,
    error: ApplicationError,
) -> JSONResponse:
    """Map a safe application error without exposing its cause."""
    request.app.state.services.metrics.observe_error(error.code)
    return error_response(
        request,
        code=error.code,
        message=error.message,
        retryable=error.retryable,
        status_code=STATUS_BY_CODE.get(
            error.code, status.HTTP_500_INTERNAL_SERVER_ERROR
        ),
    )


async def validation_error_handler(
    request: Request,
    _error: RequestValidationError,
) -> JSONResponse:
    """Hide framework validation internals behind the stable envelope."""
    return error_response(
        request,
        code="invalid_request",
        message="Request parameters are invalid.",
        retryable=False,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
