"""Synthetic domain factories shared by deterministic tests."""

import hashlib
from datetime import UTC, datetime, timedelta

from movie_language_helper.domain.session import TranscriptSession
from movie_language_helper.domain.subtitle import (
    SubtitleCue,
    Transcript,
    TranscriptSource,
    TranscriptSourceKind,
)
from movie_language_helper.domain.time import TimeRange, Timestamp


def cue(
    cue_id: str,
    start_ms: int,
    end_ms: int,
    text: str,
    *,
    analysis_text: str | None = None,
) -> SubtitleCue:
    """Build a valid synthetic cue."""
    return SubtitleCue(
        id=cue_id,
        source_index=int(cue_id.removeprefix("cue-")),
        range=TimeRange(Timestamp(start_ms), Timestamp(end_ms)),
        source_text=text,
        analysis_text=text if analysis_text is None else analysis_text,
    )


def transcript(*cues: SubtitleCue) -> Transcript:
    """Build a valid synthetic transcript."""
    return Transcript(
        cues=tuple(cues),
        language="en",
        content_digest=hashlib.sha256(b"synthetic transcript").hexdigest(),
        source=TranscriptSource(TranscriptSourceKind.SYNTHETIC, "synthetic.srt"),
    )


def session(
    *cues: SubtitleCue,
    session_id: str = "session-test",
    created_at: datetime | None = None,
    ttl: timedelta = timedelta(minutes=30),
) -> TranscriptSession:
    """Build a valid synthetic transcript session."""
    created = created_at or datetime(2026, 8, 26, tzinfo=UTC)
    return TranscriptSession(
        id=session_id,
        transcript=transcript(*cues),
        created_at=created,
        expires_at=created + ttl,
    )
