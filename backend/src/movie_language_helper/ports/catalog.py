"""Provider-neutral movie and subtitle catalog ports."""

from enum import StrEnum
from typing import Protocol

from movie_language_helper.domain.movie import MovieMatch, SubtitleCandidate
from movie_language_helper.ports.subtitle import SubtitlePayload


class ProviderFailureCode(StrEnum):
    DISABLED = "provider_disabled"
    UNAVAILABLE = "provider_unavailable"
    RATE_LIMITED = "provider_rate_limited"
    INVALID_RESPONSE = "provider_invalid_response"
    RESOURCE_LIMIT = "provider_resource_limit"
    INVALID_ARCHIVE = "provider_invalid_archive"


class ProviderFailure(RuntimeError):
    """Safe provider error with optional quota reset seconds."""

    def __init__(
        self,
        code: ProviderFailureCode,
        message: str,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds


class MovieCatalog(Protocol):
    async def search(self, query: str, limit: int) -> tuple[MovieMatch, ...]: ...


class SubtitleCatalog(Protocol):
    async def list_for_movie(
        self, movie_id: str, limit: int
    ) -> tuple[SubtitleCandidate, ...]: ...


class SubtitleSource(Protocol):
    async def fetch(self, subtitle_id: str) -> SubtitlePayload: ...
