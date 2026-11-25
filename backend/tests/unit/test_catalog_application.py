"""Provider-independent catalog use cases and safe errors."""

import asyncio
from dataclasses import dataclass

import pytest

from movie_language_helper.application.catalog import (
    CreateProviderTranscriptSession,
    ListSubtitles,
    SearchMovies,
)
from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.domain.movie import (
    ExternalId,
    MediaType,
    MovieMatch,
    SubtitleCandidate,
)
from movie_language_helper.domain.subtitle import TranscriptSourceKind
from movie_language_helper.ports.catalog import ProviderFailure, ProviderFailureCode
from movie_language_helper.ports.subtitle import SubtitlePayload
from tests.fakes import compose_test_services


@dataclass
class _Catalog:
    failure: ProviderFailure | None = None

    async def search(self, _query: str, _limit: int) -> tuple[MovieMatch, ...]:
        if self.failure:
            raise self.failure
        return (
            MovieMatch(ExternalId("fake", MediaType.MOVIE, "1"), "One", 2001),
            MovieMatch(ExternalId("fake", MediaType.MOVIE, "2"), "Two", 2002),
        )

    async def list_for_movie(
        self, movie_id: str, _limit: int
    ) -> tuple[SubtitleCandidate, ...]:
        if self.failure:
            raise self.failure
        external_id = ExternalId("fake", MediaType.MOVIE, movie_id)
        return (SubtitleCandidate("fake", "s1", external_id, "Release", "en"),)


class _Source:
    def __init__(self, failure: ProviderFailure | None = None) -> None:
        self.failure = failure

    async def fetch(self, _subtitle_id: str) -> SubtitlePayload:
        if self.failure:
            raise self.failure
        return SubtitlePayload(
            b"1\n00:00:01,000 --> 00:00:02,000\nSynthetic.\n",
            TranscriptSourceKind.PROVIDER,
            "provider.srt",
            "srt",
        )


def test_catalog_services_filter_year_and_create_session() -> None:
    catalog = _Catalog()
    assert (
        len(asyncio.run(SearchMovies(catalog).execute("One", year=None, limit=5))) == 2
    )
    filtered = asyncio.run(SearchMovies(catalog).execute("One", year=2002, limit=5))
    assert filtered[0].title == "Two"
    subtitles = asyncio.run(ListSubtitles(catalog).execute("1", 5))
    assert subtitles[0].id == "s1"
    services, _clock, _analyzer = compose_test_services()
    created = asyncio.run(
        CreateProviderTranscriptSession(
            _Source(), services.create_uploaded_session
        ).execute("s1")
    )
    assert created.transcript.source.kind is TranscriptSourceKind.PROVIDER


@pytest.mark.parametrize(
    "operation",
    [
        lambda: SearchMovies(_Catalog()).execute(" ", year=None, limit=5),
        lambda: ListSubtitles(_Catalog()).execute(" ", 5),
    ],
)
def test_catalog_services_validate_identifiers(operation: object) -> None:
    with pytest.raises(ApplicationError, match="must"):
        asyncio.run(operation())  # type: ignore[operator]


@pytest.mark.parametrize(
    ("failure", "retryable", "message"),
    [
        (
            ProviderFailure(
                ProviderFailureCode.RATE_LIMITED,
                "Quota exhausted.",
                retry_after_seconds=12,
            ),
            True,
            "12 seconds",
        ),
        (
            ProviderFailure(ProviderFailureCode.INVALID_RESPONSE, "Bad response."),
            False,
            "Bad response",
        ),
    ],
)
def test_catalog_services_map_provider_failures(
    failure: ProviderFailure, retryable: bool, message: str
) -> None:
    with pytest.raises(ApplicationError) as caught:
        asyncio.run(
            SearchMovies(_Catalog(failure)).execute("Title", year=None, limit=5)
        )
    assert caught.value.retryable is retryable
    assert message in caught.value.message
    with pytest.raises(ApplicationError):
        asyncio.run(ListSubtitles(_Catalog(failure)).execute("1", 5))
    services, _clock, _analyzer = compose_test_services()
    with pytest.raises(ApplicationError):
        asyncio.run(
            CreateProviderTranscriptSession(
                _Source(failure), services.create_uploaded_session
            ).execute("s1")
        )


def test_provider_session_rejects_blank_id() -> None:
    services, _clock, _analyzer = compose_test_services()
    with pytest.raises(ApplicationError, match="must not be blank"):
        asyncio.run(
            CreateProviderTranscriptSession(
                _Source(), services.create_uploaded_session
            ).execute(" ")
        )
