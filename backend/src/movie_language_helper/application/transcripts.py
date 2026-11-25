"""Uploaded transcript-session application services."""

from dataclasses import dataclass
from datetime import timedelta

from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.domain.errors import DomainError
from movie_language_helper.domain.session import TranscriptSession
from movie_language_helper.domain.subtitle import CueFlag, TranscriptWarning
from movie_language_helper.domain.time import SyncOffset, TimeRange, Timestamp
from movie_language_helper.ports.runtime import Clock, IdGenerator
from movie_language_helper.ports.session import (
    SessionLookupStatus,
    TranscriptSessionStore,
)
from movie_language_helper.ports.subtitle import SubtitleParser, SubtitlePayload


@dataclass(frozen=True, slots=True)
class PreviewCue:
    """One bounded, sanitized cue returned for timing verification."""

    id: str
    display_range: TimeRange
    text: str
    flags: frozenset[CueFlag]


@dataclass(frozen=True, slots=True)
class TranscriptPreview:
    """A bounded preview that cannot represent a full transcript."""

    session_id: str
    at: Timestamp
    sync_offset: SyncOffset
    cues: tuple[PreviewCue, ...]


class CreateUploadedTranscriptSession:
    """Parse upload bytes, discard them, and store a bounded session."""

    def __init__(
        self,
        parser: SubtitleParser,
        store: TranscriptSessionStore,
        clock: Clock,
        id_generator: IdGenerator,
        ttl: timedelta,
    ) -> None:
        self._parser = parser
        self._store = store
        self._clock = clock
        self._id_generator = id_generator
        self._ttl = ttl

    async def execute(self, payload: SubtitlePayload) -> TranscriptSession:
        """Create a transcript session from a bounded upload payload."""
        try:
            transcript = self._parser.parse(payload)
        except DomainError as error:
            raise ApplicationError(error.code, error.message) from error
        created_at = self._clock.now()
        session = TranscriptSession(
            id=self._id_generator.new(),
            transcript=transcript,
            created_at=created_at,
            expires_at=created_at + self._ttl,
        )
        await self._store.put(session)
        return session


class PreviewTranscriptSession:
    """Return a bounded offset-adjusted timing preview."""

    def __init__(
        self,
        store: TranscriptSessionStore,
        *,
        radius_ms: int,
        cue_limit: int,
        max_abs_offset_ms: int,
    ) -> None:
        self._store = store
        self._radius_ms = radius_ms
        self._cue_limit = cue_limit
        self._max_abs_offset_ms = max_abs_offset_ms

    async def execute(
        self,
        session_id: str,
        at: Timestamp,
        sync_offset: SyncOffset,
    ) -> TranscriptPreview:
        """Resolve a session and select only cues near a playback timestamp."""
        if abs(sync_offset.milliseconds) > self._max_abs_offset_ms:
            raise ApplicationError(
                "invalid_sync_offset",
                "Synchronization offset exceeds the configured limit.",
            )
        session = await resolve_session(self._store, session_id)
        start_ms = max(0, at.milliseconds - self._radius_ms)
        end_ms = at.milliseconds + self._radius_ms
        if end_ms == start_ms:
            end_ms += 1
        window = TimeRange(Timestamp(start_ms), Timestamp(end_ms))
        cues: list[PreviewCue] = []
        for cue in session.transcript.cues:
            if not sync_offset.overlaps_playback(cue.range, window):
                continue
            display_range = sync_offset.display_range(cue.range)
            assert display_range is not None, "overlapping cue must be displayable"
            cues.append(PreviewCue(cue.id, display_range, cue.source_text, cue.flags))
            if len(cues) == self._cue_limit:
                break
        return TranscriptPreview(session_id, at, sync_offset, tuple(cues))


class DeleteTranscriptSession:
    """Explicitly delete a transient session."""

    def __init__(self, store: TranscriptSessionStore) -> None:
        self._store = store

    async def execute(self, session_id: str) -> None:
        """Delete a session or return the stable missing error."""
        if not await self._store.delete(session_id):
            raise ApplicationError("session_not_found", "Transcript session not found.")


class CleanupTranscriptSessions:
    """Remove expired sessions without exposing transcript data."""

    def __init__(self, store: TranscriptSessionStore) -> None:
        self._store = store

    async def execute(self) -> tuple[str, ...]:
        """Return only opaque IDs of removed sessions."""
        return await self._store.cleanup_expired()


async def resolve_session(
    store: TranscriptSessionStore,
    session_id: str,
) -> TranscriptSession:
    """Resolve a stored session with stable missing/expired semantics."""
    lookup = await store.get(session_id)
    if lookup.status is SessionLookupStatus.EXPIRED:
        raise ApplicationError("session_expired", "Transcript session has expired.")
    if lookup.status is SessionLookupStatus.MISSING or lookup.session is None:
        raise ApplicationError("session_not_found", "Transcript session not found.")
    return lookup.session


def warning_codes(warnings: tuple[TranscriptWarning, ...]) -> tuple[str, ...]:
    """Return warning codes without content-bearing details."""
    return tuple(warning.code.value for warning in warnings)
