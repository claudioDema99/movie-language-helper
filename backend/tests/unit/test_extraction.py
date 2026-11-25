"""Tests for offset-aware primary and context cue extraction."""

import pytest

from movie_language_helper.domain.errors import EmptyIntervalError, InvalidValueError
from movie_language_helper.domain.extraction import ContextPolicy, extract_analysis_cues
from movie_language_helper.domain.subtitle import CueFlag, SubtitleCue
from movie_language_helper.domain.time import SyncOffset, TimeRange, Timestamp
from tests.factories import cue, transcript


def test_extraction_excludes_exact_boundaries_and_marks_context() -> None:
    source = transcript(
        cue("cue-1", 0, 1000, "Before"),
        cue("cue-2", 1000, 2000, "Inside"),
        cue("cue-3", 2000, 3000, "After"),
    )

    result = extract_analysis_cues(
        source,
        TimeRange(Timestamp(1000), Timestamp(2000)),
        SyncOffset(),
        ContextPolicy(adjacent_cues_per_side=1, window_ms=30_000),
    )

    assert tuple(item.id for item in result) == ("cue-1", "cue-2", "cue-3")
    assert tuple(item.context_only for item in result) == (True, False, True)


def test_offset_changes_selected_cue_and_display_timestamp() -> None:
    source = transcript(cue("cue-1", 1000, 2000, "Shifted"))

    result = extract_analysis_cues(
        source,
        TimeRange(Timestamp(1500), Timestamp(2500)),
        SyncOffset(1000),
    )

    assert result[0].display_range == TimeRange(Timestamp(2000), Timestamp(3000))


def test_non_dialogue_only_interval_is_empty() -> None:
    non_dialogue = SubtitleCue(
        id="cue-1",
        source_index=1,
        range=TimeRange(Timestamp(0), Timestamp(1000)),
        source_text="[music]",
        analysis_text="",
        flags=frozenset({CueFlag.NON_DIALOGUE}),
    )

    with pytest.raises(EmptyIntervalError):
        extract_analysis_cues(
            transcript(non_dialogue),
            TimeRange(Timestamp(0), Timestamp(1000)),
            SyncOffset(),
        )


def test_context_window_excludes_distant_adjacent_cue() -> None:
    source = transcript(
        cue("cue-1", 0, 1000, "Far away"),
        cue("cue-2", 50_000, 51_000, "Inside"),
    )

    result = extract_analysis_cues(
        source,
        TimeRange(Timestamp(50_000), Timestamp(51_000)),
        SyncOffset(),
        ContextPolicy(adjacent_cues_per_side=2, window_ms=30_000),
    )

    assert tuple(item.id for item in result) == ("cue-2",)


def test_context_policy_rejects_negative_bounds() -> None:
    with pytest.raises(InvalidValueError, match="negative"):
        ContextPolicy(-1, 0)
    with pytest.raises(InvalidValueError, match="negative"):
        ContextPolicy(0, -1)


def test_context_fully_before_zero_is_omitted_after_offset() -> None:
    source = transcript(
        cue("cue-1", 0, 500, "Early"),
        cue("cue-2", 2000, 3000, "Primary"),
    )
    result = extract_analysis_cues(
        source,
        TimeRange(Timestamp(1000), Timestamp(2000)),
        SyncOffset(-1000),
        ContextPolicy(1, 2000),
    )
    assert tuple(item.id for item in result) == ("cue-2",)


def test_global_offset_aligns_an_alternate_constant_shift_release() -> None:
    alternate_release = transcript(cue("cue-1", 12_000, 13_000, "Aligned"))
    result = extract_analysis_cues(
        alternate_release,
        TimeRange(Timestamp(10_000), Timestamp(11_000)),
        SyncOffset(-2_000),
    )
    assert result[0].display_range.start.milliseconds == 10_000


def test_global_offset_does_not_hide_progressive_release_drift() -> None:
    drifting_release = transcript(
        cue("cue-1", 12_000, 13_000, "Early scene"),
        cue("cue-2", 72_500, 73_500, "Later scene"),
    )
    early = extract_analysis_cues(
        drifting_release,
        TimeRange(Timestamp(10_000), Timestamp(11_000)),
        SyncOffset(-2_000),
    )
    assert early[0].id == "cue-1"
    with pytest.raises(EmptyIntervalError):
        extract_analysis_cues(
            drifting_release,
            TimeRange(Timestamp(70_000), Timestamp(70_500)),
            SyncOffset(-2_000),
        )
