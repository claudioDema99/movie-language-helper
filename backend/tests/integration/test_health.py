"""HTTP contract tests for dependency-free process-health probes."""

import asyncio

from httpx2 import ASGITransport, AsyncClient, Response

from movie_language_helper import __version__
from movie_language_helper.adapters.inbound.http.app import create_app
from movie_language_helper.infrastructure.config import Settings
from tests.fakes import compose_test_services


async def get(path: str) -> Response:
    """Send one request through the in-process ASGI transport."""
    transport = ASGITransport(app=create_app())
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get(path)


def test_application_metadata() -> None:
    app = create_app()

    assert app.title == "Movie Language Helper API"
    assert app.version == __version__


def test_application_uses_injected_service_settings_by_default() -> None:
    services, _clock, _analyzer = compose_test_services(
        settings=Settings(cors_origins=("https://example.test",))
    )
    app = create_app(services=services)
    assert app.state.services.settings.cors_origins == ("https://example.test",)


def test_liveness_probe() -> None:
    response = asyncio.run(get("/health/live"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_probe_has_no_external_prerequisites() -> None:
    response = asyncio.run(get("/health/ready"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_application_lifespan_runs_cleanup() -> None:
    async def scenario() -> None:
        app = create_app()
        async with app.router.lifespan_context(app):
            assert app.state.services is not None

    asyncio.run(scenario())
