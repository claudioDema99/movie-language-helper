"""Deterministic in-process collaborators for application tests."""

from datetime import UTC, datetime, timedelta

from movie_language_helper.adapters.outbound.fake_analyzer import FakeLanguageAnalyzer
from movie_language_helper.adapters.outbound.memory_session_store import (
    InMemoryTranscriptSessionStore,
)
from movie_language_helper.adapters.outbound.srt import (
    Pysubs2SrtParser,
    SrtParserConfig,
)
from movie_language_helper.application.analysis import AnalyzeInterval
from movie_language_helper.application.transcripts import (
    CleanupTranscriptSessions,
    CreateUploadedTranscriptSession,
    DeleteTranscriptSession,
    PreviewTranscriptSession,
)
from movie_language_helper.domain.extraction import ContextPolicy
from movie_language_helper.domain.subtitle import TranscriptLimits
from movie_language_helper.infrastructure.config import Settings
from movie_language_helper.infrastructure.container import AppServices


class MutableClock:
    """UTC clock advanced explicitly by a test."""

    def __init__(self, value: datetime | None = None) -> None:
        self.value = value or datetime(2026, 8, 26, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class SequentialIds:
    """Opaque deterministic ID source."""

    def __init__(self) -> None:
        self.count = 0

    def new(self) -> str:
        self.count += 1
        return f"session-{self.count}"


def compose_test_services(
    *,
    settings: Settings | None = None,
    clock: MutableClock | None = None,
    analyzer: FakeLanguageAnalyzer | None = None,
) -> tuple[AppServices, MutableClock, FakeLanguageAnalyzer]:
    """Compose test services while preserving production boundaries."""
    configured = settings or Settings()
    test_clock = clock or MutableClock()
    fake_analyzer = analyzer or FakeLanguageAnalyzer()
    store = InMemoryTranscriptSessionStore(test_clock, configured.session_capacity)
    parser = Pysubs2SrtParser(
        SrtParserConfig(
            max_input_bytes=configured.upload_max_bytes,
            transcript_limits=TranscriptLimits(
                max_cues=configured.transcript_max_cues,
                max_characters_per_cue=(configured.transcript_max_characters_per_cue),
                max_total_characters=configured.transcript_max_total_characters,
            ),
        )
    )
    services = AppServices(
        settings=configured,
        create_uploaded_session=CreateUploadedTranscriptSession(
            parser,
            store,
            test_clock,
            SequentialIds(),
            timedelta(seconds=configured.session_ttl_seconds),
        ),
        preview_session=PreviewTranscriptSession(
            store,
            radius_ms=configured.preview_radius_ms,
            cue_limit=configured.preview_cue_limit,
            max_abs_offset_ms=configured.max_sync_offset_ms,
        ),
        delete_session=DeleteTranscriptSession(store),
        cleanup_sessions=CleanupTranscriptSessions(store),
        analyze_interval=AnalyzeInterval(
            store,
            fake_analyzer,
            test_clock,
            max_interval_ms=configured.max_analysis_interval_ms,
            max_abs_offset_ms=configured.max_sync_offset_ms,
            max_item_limit=configured.max_item_limit,
            context_policy=ContextPolicy(
                configured.context_adjacent_cues,
                configured.context_window_ms,
            ),
            timeout_seconds=configured.analyzer_timeout_seconds,
        ),
    )
    return services, test_clock, fake_analyzer
