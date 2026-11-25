"""Subtitle payload and parser port."""

from dataclasses import dataclass
from typing import Protocol

from movie_language_helper.domain.subtitle import Transcript, TranscriptSourceKind


@dataclass(frozen=True, slots=True)
class SubtitlePayload:
    """Bounded raw subtitle bytes with trusted acquisition metadata."""

    content: bytes
    source_kind: TranscriptSourceKind
    filename: str | None
    declared_format: str
    content_type: str | None = None


class SubtitleParser(Protocol):
    """Map a bounded subtitle payload into a provider-neutral transcript."""

    def parse(self, payload: SubtitlePayload) -> Transcript: ...
