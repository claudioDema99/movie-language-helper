"""Capability-gated movie and subtitle provider endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from movie_language_helper.adapters.inbound.http.dependencies import get_services
from movie_language_helper.adapters.inbound.http.schemas import (
    CapabilitiesResponse,
    MovieMatchResponse,
    ProviderSessionRequest,
    SubtitleCandidateResponse,
    TranscriptSessionCreatedResponse,
)
from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.application.transcripts import warning_codes
from movie_language_helper.infrastructure.container import AppServices

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(
    services: Annotated[AppServices, Depends(get_services)],
) -> CapabilitiesResponse:
    return CapabilitiesResponse(
        upload=True,
        live_analyzer=services.settings.openai_enabled,
        subtitle_provider=services.search_movies is not None,
        provider_name="SubDL" if services.search_movies is not None else None,
        provider_attribution=(
            "Subtitle search and downloads are provided by SubDL."
            if services.search_movies is not None
            else None
        ),
    )


@router.get("/movies", response_model=tuple[MovieMatchResponse, ...])
async def search_movies(
    services: Annotated[AppServices, Depends(get_services)],
    q: Annotated[str, Query(min_length=2, max_length=200)],
    year: Annotated[int | None, Query(ge=1870, le=2200)] = None,
    limit: Annotated[int, Query(ge=1, le=30)] = 10,
) -> tuple[MovieMatchResponse, ...]:
    service = services.search_movies
    if service is None:
        raise _disabled()
    matches = await service.execute(q, year=year, limit=limit)
    return tuple(
        MovieMatchResponse(
            provider=match.id.provider,
            id=match.id.value,
            title=match.title,
            year=match.year,
        )
        for match in matches
    )


@router.get(
    "/movies/{movie_id}/subtitles",
    response_model=tuple[SubtitleCandidateResponse, ...],
)
async def list_subtitles(
    movie_id: str,
    services: Annotated[AppServices, Depends(get_services)],
    limit: Annotated[int, Query(ge=1, le=30)] = 20,
) -> tuple[SubtitleCandidateResponse, ...]:
    service = services.list_subtitles
    if service is None:
        raise _disabled()
    candidates = await service.execute(movie_id, limit)
    return tuple(
        SubtitleCandidateResponse(
            provider=item.provider,
            id=item.id,
            movie_id=item.movie_id.value,
            release_name=item.release_name,
            language=item.language,
            hearing_impaired=item.hearing_impaired,
            format=item.format,
            fps=item.fps,
        )
        for item in candidates
    )


@router.post(
    "/transcript-sessions/provider",
    response_model=TranscriptSessionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_session(
    request: ProviderSessionRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> TranscriptSessionCreatedResponse:
    service = services.create_provider_session
    if service is None:
        raise _disabled()
    session = await service.execute(request.subtitle_id)
    return TranscriptSessionCreatedResponse(
        id=session.id,
        created_at=session.created_at,
        expires_at=session.expires_at,
        cue_count=len(session.transcript.cues),
        duration_ms=session.transcript.duration.milliseconds,
        warnings=warning_codes(session.transcript.warnings),
    )


def _disabled() -> ApplicationError:
    return ApplicationError(
        "provider_disabled",
        "Subtitle-provider access is not enabled for this deployment.",
    )
