"""Offline HTTP contracts for the SubDL v2 adapter."""

import asyncio
import io
import json
import zipfile
from collections.abc import Callable
from unittest.mock import patch

import httpx
import pytest

from movie_language_helper.adapters.outbound.subdl import SubDLAdapter, _retry_after
from movie_language_helper.domain.subtitle import TranscriptSourceKind
from movie_language_helper.ports.catalog import ProviderFailure, ProviderFailureCode


def _zip(content: bytes = b"1\n00:00:00,000 --> 00:00:01,000\nSynthetic.\n") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("synthetic.srt", content)
    return buffer.getvalue()


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_bytes: int = 10_000,
) -> tuple[SubDLAdapter, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        SubDLAdapter(
            client,
            base_url="https://api.subdl.com",
            allowed_download_hosts=("api.subdl.com", "dl.subdl.com"),
            download_max_bytes=max_bytes,
            archive_max_members=5,
            archive_max_uncompressed_bytes=2_000,
            archive_max_ratio=100,
        ),
        client,
    )


def test_search_and_english_subtitle_mapping_tolerate_extra_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("movies/search"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "movies": [
                            {
                                "sd_id": 42,
                                "name": "Synthetic Movie",
                                "year": 2020,
                                "poster_url": "ignored",
                            }
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "subtitles": [
                    {
                        "subtitle_id": 7,
                        "release": "Synthetic.1080p",
                        "language": "English",
                        "hearing_impaired": False,
                        "format": "srt",
                        "fps": 23.976,
                    },
                    {"id": 8, "name": "French", "lang": "fr"},
                ]
            },
        )

    async def scenario() -> None:
        adapter, client = _adapter(handler)
        async with client:
            movies = await adapter.search("Synthetic", 10)
            subtitles = await adapter.list_for_movie("42", 20)
        assert movies[0].id.value == "42"
        assert movies[0].title == "Synthetic Movie"
        assert subtitles[0].id == "7"
        assert subtitles[0].language == "en"
        assert subtitles[0].fps == 23.976

    asyncio.run(scenario())
    assert requests[0].url.params["type"] == "movie"
    assert requests[1].url.params["languages"] == "en"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"results": "wrong"},
        {"results": [{"sd_id": 1}]},
        {"results": [{"sd_id": 1, "name": "", "year": 2020}]},
    ],
)
def test_search_rejects_invalid_provider_payload(payload: object) -> None:
    adapter, client = _adapter(lambda _request: httpx.Response(200, json=payload))

    async def scenario() -> None:
        async with client:
            with pytest.raises(ProviderFailure) as caught:
                await adapter.search("Synthetic", 10)
        assert caught.value.code is ProviderFailureCode.INVALID_RESPONSE

    asyncio.run(scenario())


def test_subtitle_list_rejects_invalid_metadata() -> None:
    adapter, client = _adapter(
        lambda _request: httpx.Response(
            200,
            json={
                "data": {
                    "subtitles": [
                        {"id": 1, "name": "Release", "lang": "en", "fps": 999}
                    ]
                }
            },
        )
    )

    async def scenario() -> None:
        async with client:
            with pytest.raises(ProviderFailure) as caught:
                await adapter.list_for_movie("42", 10)
        assert caught.value.code is ProviderFailureCode.INVALID_RESPONSE

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["direct", "redirect", "json"])
def test_download_streams_validated_archive(mode: str) -> None:
    archive = _zip()
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.raw_path.decode())
        if request.url.path.endswith("/download"):
            if mode == "redirect":
                return httpx.Response(
                    302, headers={"location": "https://dl.subdl.com/a.zip"}
                )
            if mode == "json":
                return httpx.Response(
                    200,
                    content=json.dumps({"download_url": "https://dl.subdl.com/a.zip"}),
                    headers={"content-type": "application/json"},
                )
        return httpx.Response(
            200, content=archive, headers={"content-type": "application/zip"}
        )

    async def scenario() -> None:
        adapter, client = _adapter(handler)
        async with client:
            payload = await adapter.fetch("id/with slash")
        assert payload.source_kind is TranscriptSourceKind.PROVIDER
        assert payload.filename == "synthetic.srt"

    asyncio.run(scenario())
    assert "%2F" in paths[0]
    if mode != "direct":
        assert paths[-1] == "/a.zip"


def test_search_maps_malformed_json() -> None:
    adapter, client = _adapter(lambda _request: httpx.Response(200, content=b"{"))

    async def scenario() -> None:
        async with client:
            with pytest.raises(ProviderFailure) as caught:
                await adapter.search("Synthetic", 10)
        assert caught.value.code is ProviderFailureCode.INVALID_RESPONSE

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(302), ProviderFailureCode.INVALID_RESPONSE),
        (
            httpx.Response(
                200,
                content=b"not json",
                headers={"content-type": "application/json"},
            ),
            ProviderFailureCode.INVALID_RESPONSE,
        ),
        (
            httpx.Response(
                200,
                json={"download_url": 12},
                headers={"content-type": "application/json"},
            ),
            ProviderFailureCode.INVALID_RESPONSE,
        ),
        (
            httpx.Response(
                200,
                json={"url": "http://evil.test/a.zip"},
                headers={"content-type": "application/json"},
            ),
            ProviderFailureCode.INVALID_RESPONSE,
        ),
    ],
)
def test_download_rejects_invalid_locations(
    response: httpx.Response, code: ProviderFailureCode
) -> None:
    adapter, client = _adapter(lambda _request: response)

    async def scenario() -> None:
        async with client:
            with pytest.raises(ProviderFailure) as caught:
                await adapter.fetch("1")
        assert caught.value.code is code

    asyncio.run(scenario())


def test_download_enforces_stream_limit() -> None:
    adapter, client = _adapter(
        lambda _request: httpx.Response(200, content=b"x" * 11), max_bytes=10
    )

    async def scenario() -> None:
        async with client:
            with pytest.raises(ProviderFailure) as caught:
                await adapter.fetch("1")
        assert caught.value.code is ProviderFailureCode.RESOURCE_LIMIT

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("headers", "retry_after"),
    [
        ({"retry-after": "15"}, 15),
        ({"retry-after": "invalid"}, None),
        ({}, None),
    ],
)
def test_rate_limit_is_not_retried(
    headers: dict[str, str], retry_after: int | None
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers=headers)

    adapter, client = _adapter(handler)

    async def scenario() -> None:
        async with client:
            with pytest.raises(ProviderFailure) as caught:
                await adapter.search("Synthetic", 10)
        assert caught.value.code is ProviderFailureCode.RATE_LIMITED
        assert caught.value.retry_after_seconds == retry_after

    asyncio.run(scenario())
    assert calls == 1


def test_epoch_rate_limit_reset_is_converted_to_seconds() -> None:
    with patch(
        "movie_language_helper.adapters.outbound.subdl.time.time",
        return_value=1_999_999_990,
    ):
        assert _retry_after(httpx.Headers({"x-ratelimit-reset": "2000000000"})) == 10


def test_transient_status_and_network_failure_have_one_bounded_retry() -> None:
    calls = 0

    def recovering(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("synthetic", request=request)
        return httpx.Response(200, json={"results": []})

    async def scenario() -> None:
        adapter, client = _adapter(recovering)
        async with client:
            assert await adapter.search("Synthetic", 10) == ()

    asyncio.run(scenario())
    assert calls == 2

    for status in (500, 400):
        calls = 0

        def failing(_request: httpx.Request, status: int = status) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(status)

        async def failed_scenario() -> None:
            adapter, client = _adapter(failing)
            async with client:
                with pytest.raises(ProviderFailure) as caught:
                    await adapter.search("Synthetic", 10)
            assert caught.value.code is ProviderFailureCode.UNAVAILABLE

        asyncio.run(failed_scenario())
        assert calls == (2 if status == 500 else 1)


def test_two_network_failures_map_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic", request=request)

    async def scenario() -> None:
        adapter, client = _adapter(handler)
        async with client:
            with pytest.raises(ProviderFailure) as caught:
                await adapter.search("Synthetic", 10)
        assert caught.value.code is ProviderFailureCode.UNAVAILABLE

    asyncio.run(scenario())
