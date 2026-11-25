"""Transcript-session use-case tests."""

import asyncio
from datetime import timedelta

import pytest

from movie_language_helper.adapters.outbound.memory_session_store import (
    InMemoryTranscriptSessionStore,
)
from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.application.transcripts import (
    CleanupTranscriptSessions,
    CreateUploadedTranscriptSession,
    DeleteTranscriptSession,
    PreviewTranscriptSession,
    resolve_session,
    warning_codes,
)
from movie_language_helper.domain.errors import SubtitleParseError
from movie_language_helper.domain.subtitle import (
    TranscriptSourceKind,
    TranscriptWarning,
    TranscriptWarningCode,
)
from movie_language_helper.domain.time import SyncOffset, Timestamp
from movie_language_helper.ports.subtitle import SubtitlePayload
from tests.factories import cue, session
from tests.fakes import MutableClock, SequentialIds


class RejectingParser:
    def parse(self, _payload: SubtitlePayload) -> object:
        raise SubtitleParseError("safe parse failure")


def payload() -> SubtitlePayload:
    return SubtitlePayload(
        b"1\n00:00:01,000 --> 00:00:02,000\nHello there\n",
        TranscriptSourceKind.UPLOAD,
        "movie.srt",
        "srt",
        "application/x-subrip",
    )


def test_create_maps_parser_error_without_storing() -> None:
    async def scenario() -> None:
        clock = MutableClock()
        store = InMemoryTranscriptSessionStore(clock, 2)
        use_case = CreateUploadedTranscriptSession(
            RejectingParser(),  # type: ignore[arg-type]
            store,
            clock,
            SequentialIds(),
            timedelta(minutes=1),
        )
        with pytest.raises(ApplicationError, match="safe parse failure") as caught:
            await use_case.execute(payload())
        assert caught.value.code == "subtitle_parse_failed"

    asyncio.run(scenario())


def test_preview_is_bounded_offset_adjusted_and_deletable() -> None:
    async def scenario() -> None:
        clock = MutableClock()
        store = InMemoryTranscriptSessionStore(clock, 2)
        stored = session(
            cue("cue-1", 0, 1000, "First"),
            cue("cue-2", 1000, 2000, "Second"),
            cue("cue-3", 2000, 3000, "Third"),
            created_at=clock.now(),
        )
        await store.put(stored)
        preview = PreviewTranscriptSession(
            store, radius_ms=400, cue_limit=1, max_abs_offset_ms=500
        )
        result = await preview.execute(stored.id, Timestamp(1500), SyncOffset(100))
        assert len(result.cues) == 1
        assert result.cues[0].display_range.start.milliseconds == 1100

        with pytest.raises(ApplicationError) as offset_error:
            await preview.execute(stored.id, Timestamp(0), SyncOffset(501))
        assert offset_error.value.code == "invalid_sync_offset"

        deletion = DeleteTranscriptSession(store)
        await deletion.execute(stored.id)
        with pytest.raises(ApplicationError) as missing:
            await deletion.execute(stored.id)
        assert missing.value.code == "session_not_found"

    asyncio.run(scenario())


def test_session_resolution_and_cleanup_preserve_expiry_semantics() -> None:
    async def scenario() -> None:
        clock = MutableClock()
        store = InMemoryTranscriptSessionStore(clock, 2)
        with pytest.raises(ApplicationError) as missing:
            await resolve_session(store, "none")
        assert missing.value.code == "session_not_found"

        expired = session(
            cue("cue-1", 0, 1, "text"),
            session_id="expired",
            created_at=clock.now(),
            ttl=timedelta(seconds=1),
        )
        await store.put(expired)
        clock.advance(timedelta(seconds=1))
        with pytest.raises(ApplicationError) as gone:
            await resolve_session(store, expired.id)
        assert gone.value.code == "session_expired"
        assert await CleanupTranscriptSessions(store).execute() == ()

    asyncio.run(scenario())


def test_warning_codes_are_content_free() -> None:
    warnings = (TranscriptWarning(TranscriptWarningCode.DUPLICATE_SOURCE_INDEX, 2),)
    assert warning_codes(warnings) == ("duplicate_source_index",)


def test_zero_radius_preview_still_builds_a_valid_half_open_window() -> None:
    async def scenario() -> None:
        clock = MutableClock()
        store = InMemoryTranscriptSessionStore(clock, 1)
        stored = session(cue("cue-1", 0, 1, "text"), created_at=clock.now())
        await store.put(stored)
        preview = PreviewTranscriptSession(
            store, radius_ms=0, cue_limit=1, max_abs_offset_ms=0
        )
        result = await preview.execute(stored.id, Timestamp(0), SyncOffset())
        assert len(result.cues) == 1

    asyncio.run(scenario())
