"""Transcript session invariant tests."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from movie_language_helper.domain.errors import InvalidValueError
from movie_language_helper.domain.session import TranscriptSession
from movie_language_helper.domain.subtitle import Transcript
from tests.factories import cue, transcript


def valid_transcript() -> Transcript:
    return transcript(cue("cue-1", 0, 1, "text"))


@pytest.mark.parametrize("session_id", ["", "   "])
def test_session_requires_id(session_id: str) -> None:
    now = datetime.now(UTC)
    with pytest.raises(InvalidValueError, match="ID"):
        TranscriptSession(
            session_id,
            valid_transcript(),
            now,
            now + timedelta(seconds=1),
        )


@pytest.mark.parametrize(
    ("created", "expires"),
    [
        (datetime(2026, 1, 1), datetime(2026, 1, 2)),
        (
            datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1))),
            datetime(2026, 1, 2, tzinfo=timezone(timedelta(hours=1))),
        ),
    ],
)
def test_session_requires_aware_utc(created: datetime, expires: datetime) -> None:
    with pytest.raises(InvalidValueError, match="UTC"):
        TranscriptSession("id", valid_transcript(), created, expires)


def test_session_expiry_must_follow_creation() -> None:
    now = datetime.now(UTC)
    with pytest.raises(InvalidValueError, match="expiry"):
        TranscriptSession("id", valid_transcript(), now, now)
