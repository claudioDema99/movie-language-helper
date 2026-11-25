"""Tests for transcript ordering, overlap, bounds, and identity."""

import hashlib

import pytest

from movie_language_helper.domain.errors import InvalidValueError, ResourceLimitError
from movie_language_helper.domain.subtitle import (
    SubtitleCue,
    Transcript,
    TranscriptLimits,
    TranscriptSource,
    TranscriptSourceKind,
    TranscriptWarning,
    TranscriptWarningCode,
)
from movie_language_helper.domain.time import TimeRange, Timestamp
from tests.factories import cue, transcript


def test_transcript_sorts_unsorted_and_overlapping_cues_stably() -> None:
    later = cue("cue-2", 2000, 3000, "Later")
    overlapping = cue("cue-3", 1000, 2500, "Overlapping")
    first = cue("cue-1", 1000, 2000, "First")

    result = transcript(later, overlapping, first)

    assert tuple(item.id for item in result.cues) == ("cue-1", "cue-3", "cue-2")
    assert result.duration.milliseconds == 3000


def test_duplicate_session_local_cue_id_is_rejected() -> None:
    with pytest.raises(InvalidValueError, match="unique"):
        transcript(
            cue("cue-1", 0, 1000, "One"),
            cue("cue-1", 1000, 2000, "Two"),
        )


@pytest.mark.parametrize(
    ("limits", "texts"),
    [
        (TranscriptLimits(max_cues=1), ("One", "Two")),
        (TranscriptLimits(max_characters_per_cue=3), ("Four",)),
        (TranscriptLimits(max_total_characters=5), ("One", "Two")),
    ],
)
def test_transcript_enforces_resource_limits(
    limits: TranscriptLimits,
    texts: tuple[str, ...],
) -> None:
    cues = tuple(
        cue(f"cue-{index}", index * 1000, (index + 1) * 1000, text)
        for index, text in enumerate(texts, start=1)
    )

    with pytest.raises(ResourceLimitError):
        Transcript(
            cues=cues,
            language="en",
            content_digest=hashlib.sha256(b"bounded").hexdigest(),
            source=TranscriptSource(TranscriptSourceKind.SYNTHETIC),
            limits=limits,
        )


def test_limit_is_inclusive_at_exact_boundary() -> None:
    result = Transcript(
        cues=(cue("cue-1", 0, 1000, "12345"),),
        language="en",
        content_digest=hashlib.sha256(b"bounded").hexdigest(),
        source=TranscriptSource(TranscriptSourceKind.SYNTHETIC),
        limits=TranscriptLimits(
            max_cues=1,
            max_characters_per_cue=5,
            max_total_characters=5,
        ),
    )

    assert result.duration.milliseconds == 1000


def test_warning_source_and_limits_validate_metadata() -> None:
    with pytest.raises(InvalidValueError, match="warning"):
        TranscriptWarning(TranscriptWarningCode.ENCODING_FALLBACK, 0)
    with pytest.raises(InvalidValueError, match="filename"):
        TranscriptSource(TranscriptSourceKind.UPLOAD, " ")
    with pytest.raises(InvalidValueError, match="limits"):
        TranscriptLimits(max_cues=0)


@pytest.mark.parametrize(
    "values",
    [
        {"id": ""},
        {"source_index": 0},
        {"source_text": " "},
    ],
)
def test_cue_validates_identity_and_text(values: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "id": "cue-1",
        "source_index": 1,
        "range": TimeRange(Timestamp(0), Timestamp(1)),
        "source_text": "text",
        "analysis_text": "text",
    }
    arguments.update(values)
    with pytest.raises(InvalidValueError):
        SubtitleCue(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("cues", "language", "digest", "message"),
    [
        ((), "en", hashlib.sha256(b"x").hexdigest(), "at least one"),
        (
            (cue("cue-1", 0, 1, "text"),),
            "fr",
            hashlib.sha256(b"x").hexdigest(),
            "English",
        ),
        ((cue("cue-1", 0, 1, "text"),), "en", "invalid", "SHA-256"),
    ],
)
def test_transcript_validates_required_metadata(
    cues: tuple[SubtitleCue, ...], language: str, digest: str, message: str
) -> None:
    with pytest.raises(InvalidValueError, match=message):
        Transcript(
            cues,
            language,
            digest,
            TranscriptSource(TranscriptSourceKind.SYNTHETIC),
        )
