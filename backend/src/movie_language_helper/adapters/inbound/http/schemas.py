"""Pydantic-only HTTP request, response, and error DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from movie_language_helper.domain.analysis import CefrLevel, LearningItemType


class ApiModel(BaseModel):
    """Strict-shape base for public API models."""

    model_config = ConfigDict(extra="forbid")


class ErrorDetail(ApiModel):
    code: str
    message: str
    retryable: bool
    correlation_id: str


class ErrorResponse(ApiModel):
    error: ErrorDetail


class TranscriptSessionCreatedResponse(ApiModel):
    id: str
    created_at: datetime
    expires_at: datetime
    cue_count: int
    duration_ms: int
    warnings: tuple[str, ...]


class PreviewCueResponse(ApiModel):
    id: str
    start_ms: int
    end_ms: int
    text: str
    flags: tuple[str, ...]


class TranscriptPreviewResponse(ApiModel):
    session_id: str
    at_ms: int
    sync_offset_ms: int
    cues: tuple[PreviewCueResponse, ...]


class AnalysisRequest(ApiModel):
    transcript_session_id: str = Field(min_length=1, max_length=200)
    start_ms: int = Field(ge=0, strict=True)
    end_ms: int = Field(gt=0, strict=True)
    sync_offset_ms: int = Field(default=0, strict=True)
    cefr_level: CefrLevel = CefrLevel.UNSPECIFIED
    item_limit: int | None = Field(default=None, ge=1, strict=True)


class OccurrenceResponse(ApiModel):
    cue_id: str
    start_ms: int
    end_ms: int
    context_excerpt: str


class LearningItemResponse(ApiModel):
    id: str
    expression: str
    normalized_form: str
    type: LearningItemType
    general_meaning: str
    contextual_meaning: str
    pronunciation: str | None
    pronunciation_notation: str | None
    estimated_cefr: CefrLevel | None
    confidence: float | None
    occurrences: tuple[OccurrenceResponse, ...]
    relevance_score: float
    usage_note: str | None


class AnalysisProvenanceResponse(ApiModel):
    analyzer_name: str
    model_identifier: str
    prompt_version: str
    schema_version: str
    grounding_version: str
    ranking_version: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None


class AnalysisResponse(ApiModel):
    id: str
    transcript_session_id: str
    start_ms: int
    end_ms: int
    sync_offset_ms: int
    cefr_level: CefrLevel
    item_limit: int
    items: tuple[LearningItemResponse, ...]
    warnings: tuple[str, ...]
    provenance: AnalysisProvenanceResponse
    created_at: datetime


class CapabilitiesResponse(ApiModel):
    upload: bool
    live_analyzer: bool
    subtitle_provider: bool
    provider_name: str | None
    provider_attribution: str | None


class MovieMatchResponse(ApiModel):
    provider: str
    id: str
    title: str
    year: int | None


class SubtitleCandidateResponse(ApiModel):
    provider: str
    id: str
    movie_id: str
    release_name: str
    language: str
    hearing_impaired: bool | None
    format: str | None
    fps: float | None


class ProviderSessionRequest(ApiModel):
    subtitle_id: str = Field(min_length=1, max_length=200)
