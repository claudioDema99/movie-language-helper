"""Analyzer-independent interval analysis orchestration."""

import asyncio
from dataclasses import dataclass

from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.application.transcripts import resolve_session
from movie_language_helper.domain.analysis import (
    GROUNDING_VERSION,
    RANKING_VERSION,
    AnalysisInput,
    AnalysisParameters,
    AnalysisProvenance,
    AnalysisResult,
    LearnerProfile,
    analysis_fingerprint,
    validate_and_rank_candidates,
)
from movie_language_helper.domain.errors import (
    EmptyIntervalError,
    InvalidAnalyzerOutputError,
)
from movie_language_helper.domain.extraction import ContextPolicy, extract_analysis_cues
from movie_language_helper.domain.time import SyncOffset, TimeRange
from movie_language_helper.ports.analyzer import (
    AnalyzerFailure,
    AnalyzerFailureCode,
    LanguageAnalyzer,
)
from movie_language_helper.ports.runtime import Clock
from movie_language_helper.ports.session import TranscriptSessionStore


@dataclass(frozen=True, slots=True)
class AnalyzeIntervalRequest:
    """Validated application-boundary analysis parameters."""

    transcript_session_id: str
    playback_range: TimeRange
    sync_offset: SyncOffset
    learner: LearnerProfile
    item_limit: int


class AnalyzeInterval:
    """Extract, call once, locally ground, rank, and version an analysis."""

    def __init__(
        self,
        store: TranscriptSessionStore,
        analyzer: LanguageAnalyzer,
        clock: Clock,
        *,
        max_interval_ms: int,
        max_abs_offset_ms: int,
        max_item_limit: int,
        context_policy: ContextPolicy,
        timeout_seconds: float,
    ) -> None:
        self._store = store
        self._analyzer = analyzer
        self._clock = clock
        self._max_interval_ms = max_interval_ms
        self._max_abs_offset_ms = max_abs_offset_ms
        self._max_item_limit = max_item_limit
        self._context_policy = context_policy
        self._timeout_seconds = timeout_seconds

    async def execute(self, request: AnalyzeIntervalRequest) -> AnalysisResult:
        """Execute one synchronous analyzer attempt for a valid selected interval."""
        self._validate_request(request)
        session = await resolve_session(self._store, request.transcript_session_id)
        try:
            cues = extract_analysis_cues(
                session.transcript,
                request.playback_range,
                request.sync_offset,
                self._context_policy,
            )
        except EmptyIntervalError as error:
            raise ApplicationError(error.code, error.message) from error

        analysis_input = AnalysisInput(cues, request.learner, request.item_limit)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                output = await self._analyzer.analyze(analysis_input)
        except TimeoutError as error:
            raise ApplicationError(
                "analyzer_unavailable",
                "Language analysis timed out.",
                retryable=True,
            ) from error
        except AnalyzerFailure as error:
            raise _map_analyzer_failure(error) from error
        except Exception as error:
            raise ApplicationError(
                "analyzer_unavailable",
                "Language analysis is currently unavailable.",
                retryable=True,
            ) from error

        try:
            items, warnings = validate_and_rank_candidates(
                output.candidates,
                cues,
                request.learner,
                request.item_limit,
            )
        except InvalidAnalyzerOutputError as error:
            raise ApplicationError(error.code, error.message) from error

        fingerprint = analysis_fingerprint(
            transcript_digest=session.transcript.content_digest,
            start_ms=request.playback_range.start.milliseconds,
            end_ms=request.playback_range.end.milliseconds,
            offset_ms=request.sync_offset.milliseconds,
            learner=request.learner,
            item_limit=request.item_limit,
            metadata=output.metadata,
        )
        provenance = AnalysisProvenance(
            analyzer_name=output.metadata.analyzer_name,
            model_identifier=output.metadata.model_identifier,
            prompt_version=output.metadata.prompt_version,
            schema_version=output.metadata.schema_version,
            grounding_version=GROUNDING_VERSION,
            ranking_version=RANKING_VERSION,
            latency_ms=output.metadata.latency_ms,
            input_tokens=output.metadata.input_tokens,
            output_tokens=output.metadata.output_tokens,
        )
        parameters = AnalysisParameters(
            request.transcript_session_id,
            request.playback_range,
            request.sync_offset,
            request.learner,
            request.item_limit,
        )
        return AnalysisResult(
            id=f"analysis-{fingerprint[:16]}",
            fingerprint=fingerprint,
            request=parameters,
            items=items,
            warnings=warnings,
            provenance=provenance,
            created_at=self._clock.now(),
        )

    def _validate_request(self, request: AnalyzeIntervalRequest) -> None:
        if request.playback_range.duration_ms > self._max_interval_ms:
            raise ApplicationError(
                "invalid_range",
                "Analysis interval exceeds the configured limit.",
            )
        if abs(request.sync_offset.milliseconds) > self._max_abs_offset_ms:
            raise ApplicationError(
                "invalid_sync_offset",
                "Synchronization offset exceeds the configured limit.",
            )
        if not 1 <= request.item_limit <= self._max_item_limit:
            raise ApplicationError(
                "invalid_item_limit",
                "Learning item limit is outside the configured bounds.",
            )


def _map_analyzer_failure(error: AnalyzerFailure) -> ApplicationError:
    messages = {
        AnalyzerFailureCode.UNAVAILABLE: "Language analysis is currently unavailable.",
        AnalyzerFailureCode.RATE_LIMITED: (
            "Language analysis is temporarily rate limited."
        ),
        AnalyzerFailureCode.REFUSED: (
            "Language analysis could not process this interval."
        ),
        AnalyzerFailureCode.INCOMPLETE: (
            "Language analysis returned an incomplete result."
        ),
        AnalyzerFailureCode.INVALID_OUTPUT: (
            "Language analysis returned invalid output."
        ),
    }
    retryable = error.code in {
        AnalyzerFailureCode.UNAVAILABLE,
        AnalyzerFailureCode.RATE_LIMITED,
    }
    return ApplicationError(error.code.value, messages[error.code], retryable=retryable)
