"""Bounded SRT decoder and pysubs2 mapping adapter."""

import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum

import pysubs2

from movie_language_helper.domain.errors import (
    ResourceLimitError,
    SubtitleParseError,
    UnsupportedSubtitleError,
)
from movie_language_helper.domain.normalization import normalize_cue_text
from movie_language_helper.domain.subtitle import (
    SubtitleCue,
    Transcript,
    TranscriptLimits,
    TranscriptSource,
    TranscriptWarning,
    TranscriptWarningCode,
)
from movie_language_helper.domain.time import TimeRange, Timestamp
from movie_language_helper.ports.subtitle import SubtitleParser, SubtitlePayload

BLOCK_SEPARATOR = re.compile(r"\n[ \t]*\n+")
TIMING_LINE = re.compile(
    r"^(?P<start>\d{1,}:[0-5]\d:[0-5]\d,\d{3})[ \t]+-->[ \t]+"
    r"(?P<end>\d{1,}:[0-5]\d:[0-5]\d,\d{3})(?:[ \t].*)?$"
)


class MalformedCuePolicy(StrEnum):
    """Whether a malformed SRT block rejects the file or is dropped."""

    REJECT = "reject"
    DROP_WITH_WARNING = "drop_with_warning"


@dataclass(frozen=True, slots=True)
class SrtParserConfig:
    """Explicit bounded parsing and decoding policy."""

    max_input_bytes: int = 2 * 1024 * 1024
    encodings: tuple[str, ...] = ("utf-8-sig", "cp1252")
    malformed_cue_policy: MalformedCuePolicy = MalformedCuePolicy.REJECT
    transcript_limits: TranscriptLimits = field(default_factory=TranscriptLimits)

    def __post_init__(self) -> None:
        if self.max_input_bytes < 1 or not self.encodings:
            raise ValueError("parser byte limit and encoding list must be non-empty")


DEFAULT_SRT_PARSER_CONFIG = SrtParserConfig()


@dataclass(frozen=True, slots=True)
class _ValidatedSrt:
    text: str
    source_indices: tuple[int, ...]
    dropped_count: int


class Pysubs2SrtParser(SubtitleParser):
    """Parse only SRT into bounded domain cues."""

    def __init__(self, config: SrtParserConfig = DEFAULT_SRT_PARSER_CONFIG) -> None:
        self._config = config

    def parse(self, payload: SubtitlePayload) -> Transcript:
        """Decode, structurally validate, parse, sanitize, and bound a payload."""
        self._validate_payload(payload)
        decoded, used_fallback = self._decode(payload.content)
        validated = self._validate_blocks(decoded)
        try:
            subtitles = pysubs2.SSAFile.from_string(validated.text, format_="srt")
        except Exception as error:
            raise SubtitleParseError("SRT parsing failed") from error

        if len(subtitles.events) != len(validated.source_indices):
            raise SubtitleParseError("SRT parser returned an unexpected cue count")

        cues = self._map_cues(subtitles, validated.source_indices)
        warnings = self._warnings(
            validated.source_indices,
            used_fallback=used_fallback,
            dropped_count=validated.dropped_count,
        )
        return Transcript(
            cues=cues,
            language="en",
            content_digest=hashlib.sha256(payload.content).hexdigest(),
            source=TranscriptSource(payload.source_kind, payload.filename),
            warnings=warnings,
            limits=self._config.transcript_limits,
        )

    def _validate_payload(self, payload: SubtitlePayload) -> None:
        if len(payload.content) > self._config.max_input_bytes:
            raise ResourceLimitError("subtitle input exceeds configured byte limit")
        if not payload.content:
            raise SubtitleParseError("subtitle input is empty")
        if payload.declared_format.casefold() != "srt":
            raise UnsupportedSubtitleError("only SRT subtitles are supported")
        if payload.filename is not None and not payload.filename.casefold().endswith(
            ".srt"
        ):
            raise UnsupportedSubtitleError("subtitle filename must end in .srt")

    def _decode(self, content: bytes) -> tuple[str, bool]:
        for index, encoding in enumerate(self._config.encodings):
            try:
                return content.decode(encoding, errors="strict"), index > 0
            except UnicodeDecodeError:
                continue
        raise UnsupportedSubtitleError("subtitle encoding is unsupported")

    def _validate_blocks(self, decoded: str) -> _ValidatedSrt:
        normalized = decoded.replace("\r\n", "\n").replace("\r", "\n").strip()
        blocks = BLOCK_SEPARATOR.split(normalized) if normalized else []
        valid_blocks: list[str] = []
        source_indices: list[int] = []
        dropped_count = 0
        for block in blocks:
            lines = block.split("\n")
            valid = (
                len(lines) >= 3
                and lines[0].strip().isdigit()
                and TIMING_LINE.fullmatch(lines[1].strip()) is not None
                and any(line.strip() for line in lines[2:])
            )
            if not valid:
                if self._config.malformed_cue_policy is MalformedCuePolicy.REJECT:
                    raise SubtitleParseError("SRT contains a malformed cue")
                dropped_count += 1
                continue
            source_indices.append(int(lines[0].strip()))
            valid_blocks.append("\n".join(lines))

        if not valid_blocks:
            raise SubtitleParseError("SRT contains no valid cues")
        return _ValidatedSrt(
            "\n\n".join(valid_blocks), tuple(source_indices), dropped_count
        )

    def _map_cues(
        self,
        subtitles: pysubs2.SSAFile,
        source_indices: tuple[int, ...],
    ) -> tuple[SubtitleCue, ...]:
        cues: list[SubtitleCue] = []
        limits = self._config.transcript_limits
        total_characters = 0
        for source_order, (event, source_index) in enumerate(
            zip(subtitles.events, source_indices, strict=True),
            start=1,
        ):
            if event.end <= event.start:
                raise SubtitleParseError("SRT cue must have positive duration")
            text = normalize_cue_text(event.text)
            if not text.source_text:
                raise SubtitleParseError("SRT cue becomes empty after normalization")
            cue_characters = max(len(text.source_text), len(text.analysis_text))
            if cue_characters > limits.max_characters_per_cue:
                raise ResourceLimitError("cue text exceeds configured limit")
            total_characters += len(text.source_text)
            if total_characters > limits.max_total_characters:
                raise ResourceLimitError("transcript text exceeds configured limit")
            if source_order > limits.max_cues:
                raise ResourceLimitError(
                    "transcript cue count exceeds configured limit"
                )
            cues.append(
                SubtitleCue(
                    id=f"cue-{source_order}",
                    source_index=source_index,
                    range=TimeRange(Timestamp(event.start), Timestamp(event.end)),
                    source_text=text.source_text,
                    analysis_text=text.analysis_text,
                    flags=text.flags,
                )
            )
        return tuple(cues)

    @staticmethod
    def _warnings(
        source_indices: tuple[int, ...],
        *,
        used_fallback: bool,
        dropped_count: int,
    ) -> tuple[TranscriptWarning, ...]:
        warnings: list[TranscriptWarning] = []
        duplicate_count = len(source_indices) - len(set(source_indices))
        if duplicate_count:
            warnings.append(
                TranscriptWarning(
                    TranscriptWarningCode.DUPLICATE_SOURCE_INDEX,
                    duplicate_count,
                )
            )
        if used_fallback:
            warnings.append(TranscriptWarning(TranscriptWarningCode.ENCODING_FALLBACK))
        if dropped_count:
            warnings.append(
                TranscriptWarning(
                    TranscriptWarningCode.MALFORMED_CUE_DROPPED,
                    dropped_count,
                )
            )
        return tuple(warnings)
