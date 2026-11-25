"""End-to-end upload, preview, analysis, deletion, and error contracts."""

import asyncio
import logging
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient, Response

from movie_language_helper.adapters.inbound.http.app import create_app
from movie_language_helper.adapters.outbound.fake_analyzer import FakeLanguageAnalyzer
from movie_language_helper.domain.analysis import (
    AnalyzerCandidate,
    AnalyzerMetadata,
    AnalyzerOutput,
    CefrLevel,
    LearningItemType,
)
from movie_language_helper.infrastructure.config import Settings
from movie_language_helper.ports.analyzer import AnalyzerFailureCode
from tests.fakes import MutableClock, compose_test_services

SRT = (
    b"1\n00:00:01,000 --> 00:00:02,000\nLet's call it a day.\n\n"
    b"2\n00:00:02,000 --> 00:00:03,000\nSee you tomorrow.\n"
)


def output() -> AnalyzerOutput:
    return AnalyzerOutput(
        (
            AnalyzerCandidate(
                expression="call it a day",
                normalized_form="call it a day",
                type=LearningItemType.IDIOM,
                general_meaning="stop an activity",
                contextual_meaning="finish now",
                cue_ids=("cue-1",),
                estimated_cefr=CefrLevel.B2,
                confidence=Decimal("0.95"),
                pronunciation="call-it-a-day",
                pronunciation_notation="IPA",
                usage_note="informal",
            ),
        ),
        AnalyzerMetadata("offline-test", "fixture-v1", "prompt-v1", "schema-v1", 3),
    )


async def client_for(
    *,
    settings: Settings | None = None,
    analyzer: FakeLanguageAnalyzer | None = None,
) -> tuple[AsyncClient, MutableClock, FakeLanguageAnalyzer]:
    services, clock, fake = compose_test_services(settings=settings, analyzer=analyzer)
    transport = ASGITransport(app=create_app(services.settings, services))
    client = AsyncClient(transport=transport, base_url="http://testserver")
    return client, clock, fake


async def upload(client: AsyncClient, content: bytes = SRT) -> Response:
    return await client.post(
        "/api/v1/transcript-sessions/upload",
        files={"file": ("movie.srt", content, "application/x-subrip")},
        data={"rights_acknowledged": "true"},
    )


def test_complete_local_api_path_and_openapi_contract() -> None:
    async def scenario() -> None:
        client, _clock, analyzer = await client_for(
            analyzer=FakeLanguageAnalyzer(output())
        )
        async with client:
            created = await upload(client)
            assert created.status_code == 201
            session_id = created.json()["id"]
            assert created.json()["cue_count"] == 2
            assert created.headers["cache-control"] == "no-store"

            preview = await client.get(
                f"/api/v1/transcript-sessions/{session_id}/preview",
                params={"at_ms": 1500, "sync_offset_ms": 100},
            )
            assert preview.status_code == 200
            assert preview.json()["cues"][0]["start_ms"] == 1100

            analysis = await client.post(
                "/api/v1/analyses",
                json={
                    "transcript_session_id": session_id,
                    "start_ms": 1000,
                    "end_ms": 2000,
                    "cefr_level": "B1",
                },
                headers={"X-Request-ID": "contract-request-1"},
            )
            assert analysis.status_code == 200
            body = analysis.json()
            assert body["items"][0]["expression"] == "call it a day"
            assert body["items"][0]["occurrences"][0]["cue_id"] == "cue-1"
            assert body["provenance"]["grounding_version"] == "grounding-v1"
            assert analysis.headers["x-request-id"] == "contract-request-1"
            assert len(analyzer.calls) == 1

            deleted = await client.delete(f"/api/v1/transcript-sessions/{session_id}")
            assert deleted.status_code == 204
            missing = await client.get(
                f"/api/v1/transcript-sessions/{session_id}/preview",
                params={"at_ms": 0},
            )
            assert missing.status_code == 404
            assert missing.json()["error"]["code"] == "session_not_found"

            openapi = (await client.get("/openapi.json")).json()
            assert "/api/v1/transcript-sessions/upload" in openapi["paths"]
            assert "/api/v1/analyses" in openapi["paths"]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("filename", "content_type", "rights", "expected_status", "expected_code"),
    [
        ("movie.srt", "application/x-subrip", "false", 422, "invalid_request"),
        ("movie.vtt", "application/x-subrip", "true", 415, "unsupported_subtitle"),
        ("movie.srt", "text/vtt", "true", 415, "unsupported_subtitle"),
    ],
)
def test_upload_admission_errors_use_stable_envelope(
    filename: str,
    content_type: str,
    rights: str,
    expected_status: int,
    expected_code: str,
) -> None:
    async def scenario() -> None:
        client, _clock, _analyzer = await client_for()
        async with client:
            response = await client.post(
                "/api/v1/transcript-sessions/upload",
                files={"file": (filename, SRT, content_type)},
                data={"rights_acknowledged": rights},
            )
        assert response.status_code == expected_status
        assert response.json()["error"]["code"] == expected_code
        assert response.json()["error"]["correlation_id"]

    asyncio.run(scenario())


def test_upload_size_parse_and_framework_validation_errors() -> None:
    async def scenario() -> None:
        settings = Settings(upload_max_bytes=10)
        client, _clock, _analyzer = await client_for(settings=settings)
        async with client:
            too_large = await upload(client)
            malformed = await client.post(
                "/api/v1/transcript-sessions/upload",
                files={
                    "file": (
                        "movie.srt",
                        b"broken",
                        "application/x-subrip",
                    )
                },
                data={"rights_acknowledged": "true"},
            )
            invalid = await client.post("/api/v1/analyses", json={})
        assert too_large.status_code == 413
        assert too_large.json()["error"]["code"] == "resource_limit_exceeded"
        assert malformed.status_code == 422
        assert malformed.json()["error"]["code"] == "subtitle_parse_failed"
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "invalid_request"

    asyncio.run(scenario())


def test_invalid_analysis_range_and_analyzer_failure_are_safe() -> None:
    async def scenario() -> None:
        analyzer = FakeLanguageAnalyzer(failure=AnalyzerFailureCode.REFUSED)
        client, _clock, _fake = await client_for(analyzer=analyzer)
        async with client:
            created = await upload(client)
            session_id = created.json()["id"]
            invalid = await client.post(
                "/api/v1/analyses",
                json={
                    "transcript_session_id": session_id,
                    "start_ms": 2000,
                    "end_ms": 1000,
                },
            )
            failed = await client.post(
                "/api/v1/analyses",
                json={
                    "transcript_session_id": session_id,
                    "start_ms": 1000,
                    "end_ms": 2000,
                },
            )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "invalid_range"
        assert failed.status_code == 502
        assert failed.json()["error"]["code"] == "analyzer_refused"
        assert "synthetic" not in failed.text

    asyncio.run(scenario())


def test_logs_only_request_metadata_and_invalid_request_id_is_replaced(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        client, _clock, _analyzer = await client_for()
        with caplog.at_level(logging.INFO, logger="movie_language_helper.http"):
            async with client:
                response = await upload(client)
        assert response.headers["x-request-id"] != "invalid id!"

    asyncio.run(scenario())
    text = caplog.text
    assert "call it a day" not in text
    assert "request_complete" in text
