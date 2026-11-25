"""Tests for half-open time and signed offset semantics."""

import pytest

from movie_language_helper.domain.errors import InvalidValueError
from movie_language_helper.domain.time import SyncOffset, TimeRange, Timestamp


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_timestamp_rejects_invalid_values(value: object) -> None:
    with pytest.raises(InvalidValueError):
        Timestamp(value)  # type: ignore[arg-type]


def test_time_range_requires_positive_duration() -> None:
    with pytest.raises(InvalidValueError):
        TimeRange(Timestamp(1000), Timestamp(1000))


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ((0, 1000), (999, 2000), True),
        ((0, 1000), (1000, 2000), False),
        ((1000, 2000), (0, 1000), False),
        ((1000, 2000), (1500, 1600), True),
    ],
)
def test_half_open_overlap_truth_table(
    left: tuple[int, int],
    right: tuple[int, int],
    expected: bool,
) -> None:
    left_range = TimeRange(Timestamp(left[0]), Timestamp(left[1]))
    right_range = TimeRange(Timestamp(right[0]), Timestamp(right[1]))

    assert left_range.overlaps(right_range) is expected


def test_positive_offset_moves_cue_later() -> None:
    cue_range = TimeRange(Timestamp(1000), Timestamp(2000))

    assert SyncOffset(500).display_range(cue_range) == TimeRange(
        Timestamp(1500), Timestamp(2500)
    )


def test_negative_offset_uses_signed_overlap_and_clamps_only_for_display() -> None:
    cue_range = TimeRange(Timestamp(500), Timestamp(1500))
    playback = TimeRange(Timestamp(0), Timestamp(1000))
    offset = SyncOffset(-1000)

    assert offset.adjusted_bounds(cue_range) == (-500, 500)
    assert offset.overlaps_playback(cue_range, playback)
    assert offset.display_range(cue_range) == TimeRange(Timestamp(0), Timestamp(500))


def test_cue_shifted_entirely_before_zero_has_no_display_range() -> None:
    cue_range = TimeRange(Timestamp(100), Timestamp(500))

    assert SyncOffset(-500).display_range(cue_range) is None
