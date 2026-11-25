"""Local single-process dependency composition."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

import httpx
from openai import AsyncOpenAI

from movie_language_helper.adapters.outbound.fake_analyzer import FakeLanguageAnalyzer
from movie_language_helper.adapters.outbound.lexicon_analyzer import (
    LexiconLanguageAnalyzer,
)
from movie_language_helper.adapters.outbound.memory_session_store import (
    InMemoryTranscriptSessionStore,
)
from movie_language_helper.adapters.outbound.openai_analyzer import (
    OpenAIResponsesAnalyzer,
)
from movie_language_helper.adapters.outbound.srt import (
    Pysubs2SrtParser,
    SrtParserConfig,
)
from movie_language_helper.adapters.outbound.subdl import SubDLAdapter
from movie_language_helper.application.analysis import AnalyzeInterval
from movie_language_helper.application.catalog import (
    CreateProviderTranscriptSession,
    ListSubtitles,
    SearchMovies,
)
from movie_language_helper.application.transcripts import (
    CleanupTranscriptSessions,
    CreateUploadedTranscriptSession,
    DeleteTranscriptSession,
    PreviewTranscriptSession,
)
from movie_language_helper.domain.extraction import ContextPolicy
from movie_language_helper.domain.subtitle import TranscriptLimits
from movie_language_helper.infrastructure.config import Settings
from movie_language_helper.infrastructure.metrics import MetricsRegistry
from movie_language_helper.infrastructure.runtime import SecureIdGenerator, SystemClock
from movie_language_helper.ports.analyzer import LanguageAnalyzer


@dataclass(frozen=True, slots=True)
class AppServices:
    """Use cases and state owned by one application process."""

    settings: Settings
    create_uploaded_session: CreateUploadedTranscriptSession
    preview_session: PreviewTranscriptSession
    delete_session: DeleteTranscriptSession
    cleanup_sessions: CleanupTranscriptSessions
    analyze_interval: AnalyzeInterval
    metrics: MetricsRegistry = field(default_factory=MetricsRegistry)
    search_movies: SearchMovies | None = None
    list_subtitles: ListSubtitles | None = None
    create_provider_session: CreateProviderTranscriptSession | None = None
    resource_closers: tuple[Callable[[], Awaitable[None]], ...] = ()


def build_services(settings: Settings) -> AppServices:
    """Compose the provider-free local application."""
    clock = SystemClock()
    id_generator = SecureIdGenerator()
    store = InMemoryTranscriptSessionStore(clock, settings.session_capacity)
    parser = Pysubs2SrtParser(
        SrtParserConfig(
            max_input_bytes=settings.upload_max_bytes,
            transcript_limits=TranscriptLimits(
                max_cues=settings.transcript_max_cues,
                max_characters_per_cue=settings.transcript_max_characters_per_cue,
                max_total_characters=settings.transcript_max_total_characters,
            ),
        )
    )
    resource_closers: list[Callable[[], Awaitable[None]]] = []
    analyzer: LanguageAnalyzer
    if settings.openai_enabled:
        assert settings.openai_api_key is not None
        assert settings.openai_model is not None
        openai_client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            max_retries=0,
        )
        analyzer = OpenAIResponsesAnalyzer(
            openai_client,
            model=settings.openai_model,
            max_output_tokens=settings.openai_max_output_tokens,
            timeout_seconds=settings.analyzer_timeout_seconds,
        )
        resource_closers.append(openai_client.close)
    elif settings.lexicon_analyzer_enabled:
        analyzer = LexiconLanguageAnalyzer()
    else:
        analyzer = FakeLanguageAnalyzer()
    create_session = CreateUploadedTranscriptSession(
        parser,
        store,
        clock,
        id_generator,
        timedelta(seconds=settings.session_ttl_seconds),
    )
    search_movies: SearchMovies | None = None
    list_subtitles: ListSubtitles | None = None
    create_provider_session: CreateProviderTranscriptSession | None = None
    if settings.subdl_enabled:
        assert settings.subdl_api_key is not None
        subdl_client = httpx.AsyncClient(
            headers={
                "Authorization": (
                    f"Bearer {settings.subdl_api_key.get_secret_value()}"
                ),
                "Accept": "application/json, application/zip",
            },
            timeout=httpx.Timeout(settings.subdl_timeout_seconds),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            follow_redirects=False,
        )
        subdl = SubDLAdapter(
            subdl_client,
            base_url=settings.subdl_base_url,
            allowed_download_hosts=settings.subdl_allowed_download_hosts,
            download_max_bytes=settings.provider_download_max_bytes,
            archive_max_members=settings.provider_archive_max_members,
            archive_max_uncompressed_bytes=(
                settings.provider_archive_max_uncompressed_bytes
            ),
            archive_max_ratio=settings.provider_archive_max_ratio,
        )
        search_movies = SearchMovies(subdl)
        list_subtitles = ListSubtitles(subdl)
        create_provider_session = CreateProviderTranscriptSession(subdl, create_session)
        resource_closers.append(subdl_client.aclose)
    return AppServices(
        settings=settings,
        create_uploaded_session=create_session,
        preview_session=PreviewTranscriptSession(
            store,
            radius_ms=settings.preview_radius_ms,
            cue_limit=settings.preview_cue_limit,
            max_abs_offset_ms=settings.max_sync_offset_ms,
        ),
        delete_session=DeleteTranscriptSession(store),
        cleanup_sessions=CleanupTranscriptSessions(store),
        analyze_interval=AnalyzeInterval(
            store,
            analyzer,
            clock,
            max_interval_ms=settings.max_analysis_interval_ms,
            max_abs_offset_ms=settings.max_sync_offset_ms,
            max_item_limit=settings.max_item_limit,
            context_policy=ContextPolicy(
                settings.context_adjacent_cues,
                settings.context_window_ms,
            ),
            timeout_seconds=settings.analyzer_timeout_seconds,
        ),
        metrics=MetricsRegistry(),
        search_movies=search_movies,
        list_subtitles=list_subtitles,
        create_provider_session=create_provider_session,
        resource_closers=tuple(resource_closers),
    )
