"""Synchronous provider-neutral language analysis endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from movie_language_helper.adapters.inbound.http.dependencies import get_services
from movie_language_helper.adapters.inbound.http.schemas import (
    AnalysisProvenanceResponse,
    AnalysisRequest,
    AnalysisResponse,
    LearningItemResponse,
    OccurrenceResponse,
)
from movie_language_helper.application.analysis import (
    AnalyzeIntervalRequest,
)
from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.domain.analysis import LearnerProfile
from movie_language_helper.domain.errors import DomainError
from movie_language_helper.domain.time import SyncOffset, TimeRange, Timestamp
from movie_language_helper.infrastructure.container import AppServices

router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])


@router.post("", response_model=AnalysisResponse)
async def analyze_interval(
    request: AnalysisRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> AnalysisResponse:
    """Analyze a bounded interval through the configured offline analyzer."""
    try:
        playback_range = TimeRange(
            Timestamp(request.start_ms), Timestamp(request.end_ms)
        )
        sync_offset = SyncOffset(request.sync_offset_ms)
    except DomainError as error:
        raise ApplicationError("invalid_range", error.message) from error
    result = await services.analyze_interval.execute(
        AnalyzeIntervalRequest(
            transcript_session_id=request.transcript_session_id,
            playback_range=playback_range,
            sync_offset=sync_offset,
            learner=LearnerProfile(request.cefr_level),
            item_limit=request.item_limit or services.settings.default_item_limit,
        )
    )
    services.metrics.observe_analysis(
        latency_ms=result.provenance.latency_ms,
        input_tokens=result.provenance.input_tokens,
        output_tokens=result.provenance.output_tokens,
    )
    return AnalysisResponse(
        id=result.id,
        transcript_session_id=result.request.transcript_session_id,
        start_ms=result.request.playback_range.start.milliseconds,
        end_ms=result.request.playback_range.end.milliseconds,
        sync_offset_ms=result.request.sync_offset.milliseconds,
        cefr_level=result.request.learner.cefr_level,
        item_limit=result.request.item_limit,
        items=tuple(
            LearningItemResponse(
                id=item.id,
                expression=item.expression,
                normalized_form=item.normalized_form,
                type=item.type,
                general_meaning=item.general_meaning,
                contextual_meaning=item.contextual_meaning,
                pronunciation=item.pronunciation,
                pronunciation_notation=item.pronunciation_notation,
                estimated_cefr=item.estimated_cefr,
                confidence=(
                    float(item.confidence) if item.confidence is not None else None
                ),
                occurrences=tuple(
                    OccurrenceResponse(
                        cue_id=occurrence.cue_id,
                        start_ms=occurrence.display_range.start.milliseconds,
                        end_ms=occurrence.display_range.end.milliseconds,
                        context_excerpt=occurrence.context_excerpt,
                    )
                    for occurrence in item.occurrences
                ),
                relevance_score=float(item.relevance_score),
                usage_note=item.usage_note,
            )
            for item in result.items
        ),
        warnings=tuple(warning.value for warning in result.warnings),
        provenance=AnalysisProvenanceResponse(
            analyzer_name=result.provenance.analyzer_name,
            model_identifier=result.provenance.model_identifier,
            prompt_version=result.provenance.prompt_version,
            schema_version=result.provenance.schema_version,
            grounding_version=result.provenance.grounding_version,
            ranking_version=result.provenance.ranking_version,
            latency_ms=result.provenance.latency_ms,
            input_tokens=result.provenance.input_tokens,
            output_tokens=result.provenance.output_tokens,
        ),
        created_at=result.created_at,
    )
