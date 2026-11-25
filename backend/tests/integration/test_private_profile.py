"""Private single-process deployment security and metrics contract."""

import asyncio

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from movie_language_helper.adapters.inbound.http.app import create_app
from movie_language_helper.infrastructure.config import Settings
from tests.fakes import compose_test_services


def test_private_profile_auth_rate_limit_headers_body_limit_and_metrics() -> None:
    async def scenario() -> None:
        settings = Settings(
            deployment_profile="private",
            private_access_token=SecretStr("test-secret-with-at-least-32-characters"),
            rate_limit_requests=2,
            request_max_bytes=2 * 1024 * 1024,
        )
        services, _clock, _analyzer = compose_test_services(settings=settings)
        app = create_app(settings, services)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            live = await client.get("/health/live")
            unauthorized = await client.get("/api/v1/capabilities")
            headers = {
                "Authorization": "Bearer test-secret-with-at-least-32-characters"
            }
            allowed = await client.get("/api/v1/capabilities", headers=headers)
            metrics = await client.get("/metrics", headers=headers)
            limited = await client.get("/api/v1/capabilities", headers=headers)
            oversized = await client.post(
                "/api/v1/analyses",
                headers={**headers, "Content-Length": str(3 * 1024 * 1024)},
                content=b"{}",
            )
        assert live.status_code == 200
        assert unauthorized.status_code == 401
        assert unauthorized.json()["error"]["code"] == "unauthorized"
        assert allowed.status_code == 200
        assert allowed.headers["x-content-type-options"] == "nosniff"
        assert allowed.headers["x-frame-options"] == "DENY"
        assert "default-src 'none'" in allowed.headers["content-security-policy"]
        assert "mlh_http_requests_total" in metrics.text
        assert limited.status_code == 429
        assert limited.headers["retry-after"]
        assert oversized.status_code == 413

    asyncio.run(scenario())


def test_invalid_content_length_is_rejected_safely() -> None:
    async def scenario() -> None:
        settings = Settings()
        services, _clock, _analyzer = compose_test_services(settings=settings)
        async with AsyncClient(
            transport=ASGITransport(app=create_app(settings, services)),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/api/v1/analyses",
                headers={"Content-Length": "not-a-number"},
                content=b"{}",
            )
        assert response.status_code == 413
        assert response.headers["cache-control"] == "no-store"

    asyncio.run(scenario())
