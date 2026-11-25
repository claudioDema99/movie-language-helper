"""Pure transcript range extraction with bounded adjacent context."""

from dataclasses import dataclass

from movie_language_helper.domain.analysis import AnalysisCue
from movie_language_helper.domain.errors import EmptyIntervalError, InvalidValueError
from movie_language_helper.domain.subtitle import CueFlag, Transcript
from movie_language_helper.domain.time import SyncOffset, TimeRange


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    """Bounds for context-only cues surrounding an analysis interval."""

    adjacent_cues_per_side: int = 2
    window_ms: int = 30_000

    def __post_init__(self) -> None:
        if self.adjacent_cues_per_side < 0 or self.window_ms < 0:
            raise InvalidValueError("context bounds must not be negative")


DEFAULT_CONTEXT_POLICY = ContextPolicy()


def extract_analysis_cues(
    transcript: Transcript,
    playback_range: TimeRange,
    sync_offset: SyncOffset,
    policy: ContextPolicy = DEFAULT_CONTEXT_POLICY,
) -> tuple[AnalysisCue, ...]:
    """Select dialogue cues and context while preserving interval membership."""
    primary_indices = [
        index
        for index, cue in enumerate(transcript.cues)
        if cue.analysis_text
        and CueFlag.NON_DIALOGUE not in cue.flags
        and sync_offset.overlaps_playback(cue.range, playback_range)
    ]
    if not primary_indices:
        raise EmptyIntervalError("no dialogue overlaps the requested interval")

    first = min(primary_indices)
    last = max(primary_indices)
    before = _eligible_context_indices(
        transcript,
        range(max(0, first - policy.adjacent_cues_per_side), first),
        playback_range,
        sync_offset,
        policy,
    )
    after = _eligible_context_indices(
        transcript,
        range(
            last + 1,
            min(len(transcript.cues), last + 1 + policy.adjacent_cues_per_side),
        ),
        playback_range,
        sync_offset,
        policy,
    )
    selected = sorted(set(primary_indices) | set(before) | set(after))
    primary_set = set(primary_indices)

    result: list[AnalysisCue] = []
    for index in selected:
        cue = transcript.cues[index]
        display_range = sync_offset.display_range(cue.range)
        if display_range is None or not cue.analysis_text:
            continue
        result.append(
            AnalysisCue(
                id=cue.id,
                display_range=display_range,
                text=cue.analysis_text,
                context_only=index not in primary_set,
            )
        )
    return tuple(result)


def _eligible_context_indices(
    transcript: Transcript,
    indices: range,
    playback_range: TimeRange,
    sync_offset: SyncOffset,
    policy: ContextPolicy,
) -> tuple[int, ...]:
    lower = playback_range.start.milliseconds - policy.window_ms
    upper = playback_range.end.milliseconds + policy.window_ms
    eligible: list[int] = []
    for index in indices:
        cue = transcript.cues[index]
        start, end = sync_offset.adjusted_bounds(cue.range)
        if cue.analysis_text and end >= lower and start <= upper:
            eligible.append(index)
    return tuple(eligible)
