"""Transcript entities, limits, warnings, and source metadata."""

import re
from dataclasses import dataclass, field
from enum import StrEnum

from movie_language_helper.domain.errors import InvalidValueError, ResourceLimitError
from movie_language_helper.domain.time import TimeRange, Timestamp

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class CueFlag(StrEnum):
    """Deterministically derived cue properties."""

    MARKUP_REMOVED = "markup_removed"
    NON_DIALOGUE = "non_dialogue"


class TranscriptWarningCode(StrEnum):
    """Non-fatal parser outcomes safe to expose without subtitle text."""

    DUPLICATE_SOURCE_INDEX = "duplicate_source_index"
    ENCODING_FALLBACK = "encoding_fallback"
    MALFORMED_CUE_DROPPED = "malformed_cue_dropped"


class TranscriptSourceKind(StrEnum):
    """How a transcript payload entered the application."""

    UPLOAD = "upload"
    PROVIDER = "provider"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True, slots=True)
class TranscriptWarning:
    """A typed non-fatal transcript warning."""

    code: TranscriptWarningCode
    count: int = 1

    def __post_init__(self) -> None:
        if self.count < 1:
            raise InvalidValueError("warning count must be positive")


@dataclass(frozen=True, slots=True)
class TranscriptSource:
    """Minimal acquisition metadata that never retains payload bytes."""

    kind: TranscriptSourceKind
    filename: str | None = None

    def __post_init__(self) -> None:
        if self.filename is not None and not self.filename.strip():
            raise InvalidValueError("source filename must not be blank")


@dataclass(frozen=True, slots=True)
class TranscriptLimits:
    """Configuration-backed transcript resource limits."""

    max_cues: int = 20_000
    max_characters_per_cue: int = 10_000
    max_total_characters: int = 2_000_000

    def __post_init__(self) -> None:
        if (
            min(
                self.max_cues,
                self.max_characters_per_cue,
                self.max_total_characters,
            )
            < 1
        ):
            raise InvalidValueError("transcript limits must be positive")


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    """One sanitized, session-local subtitle cue."""

    id: str
    source_index: int | None
    range: TimeRange
    source_text: str
    analysis_text: str
    flags: frozenset[CueFlag] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidValueError("cue ID must not be blank")
        if self.source_index is not None and self.source_index < 1:
            raise InvalidValueError("source cue index must be positive")
        if not self.source_text.strip():
            raise InvalidValueError("cue source text must not be blank")


@dataclass(frozen=True, slots=True)
class Transcript:
    """A bounded, immutable, chronologically ordered transcript."""

    cues: tuple[SubtitleCue, ...]
    language: str
    content_digest: str
    source: TranscriptSource
    warnings: tuple[TranscriptWarning, ...] = ()
    limits: TranscriptLimits = field(default_factory=TranscriptLimits, repr=False)

    def __post_init__(self) -> None:
        if not self.cues:
            raise InvalidValueError("transcript must contain at least one cue")
        if self.language != "en":
            raise InvalidValueError("MVP transcripts must use English")
        if SHA256_PATTERN.fullmatch(self.content_digest) is None:
            raise InvalidValueError("content digest must be lowercase SHA-256 hex")
        if len(self.cues) > self.limits.max_cues:
            raise ResourceLimitError("transcript cue count exceeds configured limit")

        cue_ids: set[str] = set()
        total_characters = 0
        for cue in self.cues:
            if cue.id in cue_ids:
                raise InvalidValueError("cue IDs must be unique within a transcript")
            cue_ids.add(cue.id)
            cue_characters = max(len(cue.source_text), len(cue.analysis_text))
            if cue_characters > self.limits.max_characters_per_cue:
                raise ResourceLimitError("cue text exceeds configured limit")
            total_characters += len(cue.source_text)

        if total_characters > self.limits.max_total_characters:
            raise ResourceLimitError("transcript text exceeds configured limit")

        ordered = tuple(
            cue
            for _, cue in sorted(
                enumerate(self.cues),
                key=lambda item: (
                    item[1].range.start.milliseconds,
                    item[1].range.end.milliseconds,
                    item[0],
                ),
            )
        )
        object.__setattr__(self, "cues", ordered)

    @property
    def duration(self) -> Timestamp:
        """Return the greatest cue end as the transcript duration."""
        return Timestamp(max(cue.range.end.milliseconds for cue in self.cues))
