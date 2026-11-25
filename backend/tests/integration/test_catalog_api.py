"""Capability-gated catalog and provider-session HTTP flow."""

import asyncio
from dataclasses import replace

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from movie_language_helper.adapters.inbound.http.app import create_app
from movie_language_helper.application.catalog import (
    CreateProviderTranscriptSession,
    ListSubtitles,
    SearchMovies,
)
from movie_language_helper.domain.movie import (
    ExternalId,
    MediaType,
    MovieMatch,
    SubtitleCandidate,
)
from movie_language_helper.domain.subtitle import TranscriptSourceKind
from movie_language_helper.infrastructure.config import Settings
from movie_language_helper.ports.subtitle import SubtitlePayload
from tests.fakes import compose_test_services


class _Catalog:
    async def search(self, _query: str, _limit: int) -> tuple[MovieMatch, ...]:
        return (
            MovieMatch(
                ExternalId("subdl", MediaType.MOVIE, "42"),
                "Synthetic Movie",
                2020,
            ),
        )

    async def list_for_movie(
        self, movie_id: str, _limit: int
    ) -> tuple[SubtitleCandidate, ...]:
        return (
            SubtitleCandidate(
                "subdl",
                "7",
                ExternalId("subdl", MediaType.MOVIE, movie_id),
                "Synthetic.1080p",
                "en",
                False,
                "srt",
                24,
            ),
        )


class _Source:
    async def fetch(self, _subtitle_id: str) -> SubtitlePayload:
        return SubtitlePayload(
            b"1\n00:00:01,000 --> 00:00:02,000\nSynthetic dialogue.\n",
            TranscriptSourceKind.PROVIDER,
            "synthetic.srt",
            "srt",
        )


def test_disabled_capability_and_provider_error_contract() -> None:
    async def scenario() -> None:
        services, _clock, _analyzer = compose_test_services()
        async with AsyncClient(
            transport=ASGITransport(app=create_app(services.settings, services)),
            base_url="http://testserver",
        ) as client:
            capabilities = await client.get("/api/v1/capabilities")
            movies = await client.get("/api/v1/movies", params={"q": "Movie"})
            subtitles = await client.get("/api/v1/movies/42/subtitles")
            session = await client.post(
                "/api/v1/transcript-sessions/provider",
                json={"subtitle_id": "7"},
            )
        assert capabilities.json() == {
            "upload": True,
            "live_analyzer": False,
            "subtitle_provider": False,
            "provider_name": None,
            "provider_attribution": None,
        }
        for response in (movies, subtitles, session):
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "provider_disabled"

    asyncio.run(scenario())


def test_provider_search_list_and_session_contract() -> None:
    async def scenario() -> None:
        settings = Settings(
            openai_enabled=True,
            openai_risk_acknowledged=True,
            openai_api_key=SecretStr("synthetic"),
            openai_model="gpt-test-snapshot",
        )
        base, _clock, _analyzer = compose_test_services(settings=settings)
        catalog = _Catalog()
        services = replace(
            base,
            search_movies=SearchMovies(catalog),
            list_subtitles=ListSubtitles(catalog),
            create_provider_session=CreateProviderTranscriptSession(
                _Source(), base.create_uploaded_session
            ),
        )
        app = create_app(settings, services)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            capabilities = await client.get("/api/v1/capabilities")
            movies = await client.get(
                "/api/v1/movies", params={"q": "Synthetic", "year": 2020}
            )
            subtitles = await client.get("/api/v1/movies/42/subtitles")
            session = await client.post(
                "/api/v1/transcript-sessions/provider",
                json={"subtitle_id": "7"},
            )
            openapi = (await client.get("/openapi.json")).json()
        assert capabilities.json()["live_analyzer"] is True
        assert capabilities.json()["provider_name"] == "SubDL"
        assert "provided by SubDL" in capabilities.json()["provider_attribution"]
        assert movies.json()[0]["id"] == "42"
        assert subtitles.json()[0]["release_name"] == "Synthetic.1080p"
        assert session.status_code == 201
        assert session.json()["cue_count"] == 1
        assert "/api/v1/movies" in openapi["paths"]

    asyncio.run(scenario())


def test_lifespan_closes_outbound_resources() -> None:
    closed = False

    async def close() -> None:
        nonlocal closed
        closed = True

    async def scenario() -> None:
        services, _clock, _analyzer = compose_test_services()
        services = replace(services, resource_closers=(close,))
        app = create_app(services.settings, services)
        async with app.router.lifespan_context(app):
            assert closed is False
        assert closed is True

    asyncio.run(scenario())
