"""Provider-independent catalog and provider-session use cases."""

from dataclasses import dataclass

from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.application.transcripts import (
    CreateUploadedTranscriptSession,
)
from movie_language_helper.domain.movie import MovieMatch, SubtitleCandidate
from movie_language_helper.domain.session import TranscriptSession
from movie_language_helper.ports.catalog import (
    MovieCatalog,
    ProviderFailure,
    SubtitleCatalog,
    SubtitleSource,
)


def _provider_error(error: ProviderFailure) -> ApplicationError:
    suffix = (
        f" Try again in about {error.retry_after_seconds} seconds."
        if error.retry_after_seconds is not None
        else ""
    )
    return ApplicationError(
        error.code.value,
        f"{error}{suffix}",
        retryable=error.code.value in {"provider_unavailable", "provider_rate_limited"},
    )


@dataclass(frozen=True, slots=True)
class SearchMovies:
    catalog: MovieCatalog

    async def execute(
        self, query: str, *, year: int | None, limit: int
    ) -> tuple[MovieMatch, ...]:
        normalized = query.strip()
        if len(normalized) < 2:
            raise ApplicationError(
                "invalid_request", "Movie search must contain at least two characters."
            )
        try:
            matches = await self.catalog.search(normalized, limit)
        except ProviderFailure as error:
            raise _provider_error(error) from error
        if year is None:
            return matches
        return tuple(match for match in matches if match.year == year)


@dataclass(frozen=True, slots=True)
class ListSubtitles:
    catalog: SubtitleCatalog

    async def execute(self, movie_id: str, limit: int) -> tuple[SubtitleCandidate, ...]:
        if not movie_id.strip():
            raise ApplicationError("invalid_request", "Movie ID must not be blank.")
        try:
            return await self.catalog.list_for_movie(movie_id, limit)
        except ProviderFailure as error:
            raise _provider_error(error) from error


@dataclass(frozen=True, slots=True)
class CreateProviderTranscriptSession:
    source: SubtitleSource
    create_session: CreateUploadedTranscriptSession

    async def execute(self, subtitle_id: str) -> TranscriptSession:
        if not subtitle_id.strip():
            raise ApplicationError("invalid_request", "Subtitle ID must not be blank.")
        try:
            payload = await self.source.fetch(subtitle_id)
        except ProviderFailure as error:
            raise _provider_error(error) from error
        return await self.create_session.execute(payload)
