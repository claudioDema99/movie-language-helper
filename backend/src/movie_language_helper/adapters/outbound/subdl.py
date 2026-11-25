"""Defensive SubDL v2 catalog and subtitle-source adapter."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from movie_language_helper.adapters.outbound.safe_zip import read_srt_member
from movie_language_helper.domain.movie import (
    ExternalId,
    MediaType,
    MovieMatch,
    SubtitleCandidate,
)
from movie_language_helper.domain.subtitle import TranscriptSourceKind
from movie_language_helper.ports.catalog import ProviderFailure, ProviderFailureCode
from movie_language_helper.ports.subtitle import SubtitlePayload

PROVIDER = "subdl"


class _MovieDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | int = Field(validation_alias=AliasChoices("sd_id", "id"))
    title: str = Field(validation_alias=AliasChoices("name", "title"))
    year: int | None = None


class _SubtitleDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | int = Field(validation_alias=AliasChoices("id", "sd_id", "subtitle_id"))
    release_name: str = Field(
        validation_alias=AliasChoices("release_name", "release", "name")
    )
    language: str = Field(validation_alias=AliasChoices("lang", "language"))
    hearing_impaired: bool | None = Field(
        default=None, validation_alias=AliasChoices("hi", "hearing_impaired")
    )
    format: str | None = None
    fps: float | None = None


class SubDLAdapter:
    """Implement the three catalog ports through only SubDL v2 endpoints."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        allowed_download_hosts: tuple[str, ...],
        download_max_bytes: int,
        archive_max_members: int,
        archive_max_uncompressed_bytes: int,
        archive_max_ratio: int,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._allowed_download_hosts = frozenset(allowed_download_hosts)
        self._download_max_bytes = download_max_bytes
        self._archive_max_members = archive_max_members
        self._archive_max_uncompressed_bytes = archive_max_uncompressed_bytes
        self._archive_max_ratio = archive_max_ratio

    async def search(self, query: str, limit: int) -> tuple[MovieMatch, ...]:
        payload = await self._get_json(
            "/api/v2/movies/search",
            params={"q": query, "type": "movie", "limit": str(limit)},
        )
        try:
            return tuple(
                MovieMatch(
                    ExternalId(PROVIDER, MediaType.MOVIE, str(dto.id)),
                    dto.title,
                    dto.year,
                )
                for dto in (_MovieDto.model_validate(item) for item in _items(payload))
            )
        except (ValidationError, ValueError) as error:
            raise _invalid_response() from error

    async def list_for_movie(
        self, movie_id: str, limit: int
    ) -> tuple[SubtitleCandidate, ...]:
        payload = await self._get_json(
            "/api/v2/subtitles/search",
            params={
                "sd_id": movie_id,
                "type": "movie",
                "languages": "en",
                "limit": str(limit),
            },
        )
        try:
            result: list[SubtitleCandidate] = []
            for item in _items(payload):
                dto = _SubtitleDto.model_validate(item)
                if dto.language.casefold() not in {"en", "eng", "english"}:
                    continue
                result.append(
                    SubtitleCandidate(
                        provider=PROVIDER,
                        id=str(dto.id),
                        movie_id=ExternalId(PROVIDER, MediaType.MOVIE, movie_id),
                        release_name=dto.release_name,
                        language="en",
                        hearing_impaired=dto.hearing_impaired,
                        format=dto.format,
                        fps=dto.fps,
                    )
                )
            return tuple(result)
        except (ValidationError, ValueError) as error:
            raise _invalid_response() from error

    async def fetch(self, subtitle_id: str) -> SubtitlePayload:
        response = await self._send(
            "/api/v2/subtitles/" + quote(subtitle_id, safe="") + "/download",
            params={"format": "zip"},
        )
        try:
            if response.is_redirect:
                location = response.headers.get("location")
                if location is None:
                    raise _invalid_response()
                destination = self._validated_url(location)
                await response.aclose()
                response = await self._send_absolute(destination)
            elif "json" in response.headers.get("content-type", ""):
                try:
                    await response.aread()
                    payload = response.json()
                    location = payload.get("download_url") or payload.get("url")
                except (ValueError, AttributeError) as error:
                    raise _invalid_response() from error
                if not isinstance(location, str):
                    raise _invalid_response()
                destination = self._validated_url(location)
                await response.aclose()
                response = await self._send_absolute(destination)
            archive = await self._bounded_body(response)
        finally:
            await response.aclose()
        filename, content = read_srt_member(
            archive,
            max_members=self._archive_max_members,
            max_uncompressed_bytes=self._archive_max_uncompressed_bytes,
            max_ratio=self._archive_max_ratio,
        )
        return SubtitlePayload(
            content=content,
            source_kind=TranscriptSourceKind.PROVIDER,
            filename=filename,
            declared_format="srt",
            content_type="application/x-subrip",
        )

    async def _get_json(self, path: str, *, params: dict[str, str]) -> dict[str, Any]:
        response = await self._send(path, params=params)
        try:
            await response.aread()
            payload = response.json()
            if not isinstance(payload, dict):
                raise _invalid_response()
            return payload
        except ValueError as error:
            raise _invalid_response() from error
        finally:
            await response.aclose()

    async def _send(self, path: str, *, params: dict[str, str]) -> httpx.Response:
        return await self._send_absolute(
            urljoin(self._base_url + "/", path.lstrip("/")), params=params
        )

    async def _send_absolute(
        self, url: str, *, params: dict[str, str] | None = None
    ) -> httpx.Response:
        for attempt in range(2):
            try:
                request = self._client.build_request("GET", url, params=params)
                response = await self._client.send(request, stream=True)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt == 0:
                    continue
                raise ProviderFailure(
                    ProviderFailureCode.UNAVAILABLE,
                    "Subtitle provider is temporarily unavailable.",
                ) from error
            if response.status_code == 429:
                retry_after = _retry_after(response.headers)
                await response.aclose()
                raise ProviderFailure(
                    ProviderFailureCode.RATE_LIMITED,
                    "Subtitle provider quota is exhausted.",
                    retry_after_seconds=retry_after,
                )
            if response.status_code >= 500 and attempt == 0:
                await response.aclose()
                continue
            if response.is_error and not response.is_redirect:
                await response.aclose()
                raise ProviderFailure(
                    ProviderFailureCode.UNAVAILABLE,
                    "Subtitle provider request failed.",
                )
            return response
        raise AssertionError(
            "bounded retry loop must return or raise"
        )  # pragma: no cover

    async def _bounded_body(self, response: httpx.Response) -> bytes:
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > self._download_max_bytes:
                raise ProviderFailure(
                    ProviderFailureCode.RESOURCE_LIMIT,
                    "Subtitle provider download exceeds the size limit.",
                )
        return bytes(content)

    def _validated_url(self, location: str) -> str:
        url = urljoin(self._base_url + "/", location)
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self._allowed_download_hosts
        ):
            raise ProviderFailure(
                ProviderFailureCode.INVALID_RESPONSE,
                "Subtitle provider returned an unsafe download location.",
            )
        return url


def _items(payload: dict[str, Any]) -> list[Any]:
    for key in ("results", "movies", "subtitles", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested_key in ("results", "movies", "subtitles"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return nested
    raise _invalid_response()


def _retry_after(headers: httpx.Headers) -> int | None:
    raw = headers.get("retry-after") or headers.get("x-ratelimit-reset")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value > 10_000_000:
        value -= round(time.time())
    return max(0, value)


def _invalid_response() -> ProviderFailure:
    return ProviderFailure(
        ProviderFailureCode.INVALID_RESPONSE,
        "Subtitle provider returned an invalid response.",
    )
