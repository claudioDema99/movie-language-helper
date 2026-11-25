"""Integer-millisecond time values and half-open interval policy."""

from __future__ import annotations

from dataclasses import dataclass

from movie_language_helper.domain.errors import InvalidValueError


def _require_integer(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidValueError(f"{field} must be an integer")


@dataclass(frozen=True, order=True, slots=True)
class Timestamp:
    """A non-negative integer-millisecond timestamp."""

    milliseconds: int

    def __post_init__(self) -> None:
        _require_integer(self.milliseconds, "timestamp")
        if self.milliseconds < 0:
            raise InvalidValueError("timestamp must not be negative")


@dataclass(frozen=True, slots=True)
class TimeRange:
    """A positive-duration half-open interval."""

    start: Timestamp
    end: Timestamp

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise InvalidValueError("range end must be greater than start")

    @property
    def duration_ms(self) -> int:
        """Return the exact integer duration."""
        return self.end.milliseconds - self.start.milliseconds

    def overlaps(self, other: TimeRange) -> bool:
        """Return whether two half-open intervals overlap."""
        return (
            self.start.milliseconds < other.end.milliseconds
            and other.start.milliseconds < self.end.milliseconds
        )


@dataclass(frozen=True, order=True, slots=True)
class SyncOffset:
    """A signed subtitle-to-playback offset in integer milliseconds."""

    milliseconds: int = 0

    def __post_init__(self) -> None:
        _require_integer(self.milliseconds, "synchronization offset")

    def adjusted_bounds(self, source_range: TimeRange) -> tuple[int, int]:
        """Apply the offset without unsigned clamping."""
        return (
            source_range.start.milliseconds + self.milliseconds,
            source_range.end.milliseconds + self.milliseconds,
        )

    def overlaps_playback(self, source_range: TimeRange, playback: TimeRange) -> bool:
        """Compare signed adjusted cue bounds with a playback interval."""
        start, end = self.adjusted_bounds(source_range)
        return start < playback.end.milliseconds and playback.start.milliseconds < end

    def display_range(self, source_range: TimeRange) -> TimeRange | None:
        """Return a clamped display range, or None when entirely before zero."""
        start, end = self.adjusted_bounds(source_range)
        if end <= 0:
            return None
        return TimeRange(Timestamp(max(0, start)), Timestamp(max(0, end)))
