"""Provider-neutral analyzer candidates and final learning-item policy."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from movie_language_helper.domain.errors import (
    InvalidAnalyzerOutputError,
    InvalidValueError,
)
from movie_language_helper.domain.normalization import normalize_for_matching
from movie_language_helper.domain.time import SyncOffset, TimeRange

GROUNDING_VERSION = "grounding-v1"
RANKING_VERSION = "ranking-v2"
MAX_MEANING_CHARACTERS = 500
MAX_USAGE_NOTE_CHARACTERS = 300
MAX_EXCERPT_CHARACTERS = 240


class CefrLevel(StrEnum):
    """Supported learner and estimated proficiency levels."""

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    UNSPECIFIED = "unspecified"


class LearningItemType(StrEnum):
    """Product vocabulary for candidate and final item types."""

    WORD = "word"
    IDIOM = "idiom"
    PHRASAL_VERB = "phrasal_verb"
    SLANG = "slang"
    OTHER_EXPRESSION = "other_expression"


class AnalysisWarning(StrEnum):
    """Safe deterministic analysis warnings."""

    DUPLICATES_REMOVED = "duplicates_removed"
    NOISE_REMOVED = "noise_removed"


@dataclass(frozen=True, slots=True)
class LearnerProfile:
    """Provider-neutral learner settings."""

    cefr_level: CefrLevel = CefrLevel.UNSPECIFIED


@dataclass(frozen=True, slots=True)
class AnalysisCue:
    """One selected cue sent through the analyzer port."""

    id: str
    display_range: TimeRange
    text: str
    context_only: bool

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.text.strip():
            raise InvalidValueError("analysis cue ID and text must not be blank")


@dataclass(frozen=True, slots=True)
class AnalyzerCandidate:
    """Untrusted provider-neutral language analyzer output."""

    expression: str
    normalized_form: str
    type: LearningItemType
    general_meaning: str
    contextual_meaning: str
    cue_ids: tuple[str, ...]
    estimated_cefr: CefrLevel | None = None
    confidence: Decimal | None = None
    salience: Decimal = Decimal("0.5")
    pronunciation: str | None = None
    pronunciation_notation: str | None = None
    usage_note: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.expression,
            self.normalized_form,
            self.general_meaning,
            self.contextual_meaning,
        )
        if any(not value.strip() for value in required):
            raise InvalidAnalyzerOutputError(
                "candidate required text must not be blank"
            )
        if not self.cue_ids or any(not cue_id.strip() for cue_id in self.cue_ids):
            raise InvalidAnalyzerOutputError(
                "candidate cue references must not be empty"
            )
        if (
            len(self.general_meaning) > MAX_MEANING_CHARACTERS
            or len(self.contextual_meaning) > MAX_MEANING_CHARACTERS
        ):
            raise InvalidAnalyzerOutputError(
                "candidate meaning exceeds configured limit"
            )
        if (
            self.usage_note is not None
            and len(self.usage_note) > MAX_USAGE_NOTE_CHARACTERS
        ):
            raise InvalidAnalyzerOutputError(
                "candidate usage note exceeds configured limit"
            )
        if (self.pronunciation is None) != (self.pronunciation_notation is None):
            raise InvalidAnalyzerOutputError(
                "pronunciation and notation must be supplied together"
            )
        for value, field_name in (
            (self.confidence, "confidence"),
            (self.salience, "salience"),
        ):
            if value is not None and (
                not value.is_finite() or not Decimal("0") <= value <= Decimal("1")
            ):
                raise InvalidAnalyzerOutputError(f"candidate {field_name} must be 0..1")


@dataclass(frozen=True, slots=True)
class AnalyzerMetadata:
    """Safe analyzer execution metadata."""

    analyzer_name: str
    model_identifier: str
    prompt_version: str
    schema_version: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.analyzer_name,
                self.model_identifier,
                self.prompt_version,
                self.schema_version,
            )
        ):
            raise InvalidAnalyzerOutputError("analyzer metadata must not be blank")
        if self.latency_ms < 0:
            raise InvalidAnalyzerOutputError("analyzer latency must not be negative")
        if any(
            value is not None and value < 0
            for value in (self.input_tokens, self.output_tokens)
        ):
            raise InvalidAnalyzerOutputError(
                "analyzer token counts must not be negative"
            )


@dataclass(frozen=True, slots=True)
class AnalyzerOutput:
    """Candidate batch returned by a language analyzer port."""

    candidates: tuple[AnalyzerCandidate, ...]
    metadata: AnalyzerMetadata


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    """Minimal provider-neutral input for a language analyzer."""

    cues: tuple[AnalysisCue, ...]
    learner: LearnerProfile
    item_limit: int
    grounding_version: str = GROUNDING_VERSION
    ranking_version: str = RANKING_VERSION


@dataclass(frozen=True, slots=True)
class Occurrence:
    """A locally derived, grounded expression occurrence."""

    cue_id: str
    display_range: TimeRange
    context_excerpt: str


@dataclass(frozen=True, slots=True)
class LearningItem:
    """A validated, grounded, deterministically ranked learning item."""

    id: str
    expression: str
    normalized_form: str
    type: LearningItemType
    general_meaning: str
    contextual_meaning: str
    occurrences: tuple[Occurrence, ...]
    relevance_score: Decimal
    estimated_cefr: CefrLevel | None = None
    confidence: Decimal | None = None
    pronunciation: str | None = None
    pronunciation_notation: str | None = None
    usage_note: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisProvenance:
    """Versions and safe analyzer metadata needed for reproducibility."""

    analyzer_name: str
    model_identifier: str
    prompt_version: str
    schema_version: str
    grounding_version: str
    ranking_version: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True, slots=True)
class AnalysisParameters:
    """Immutable user-supplied parameters represented in a result."""

    transcript_session_id: str
    playback_range: TimeRange
    sync_offset: SyncOffset
    learner: LearnerProfile
    item_limit: int


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """A final ordered provider-neutral analysis result."""

    id: str
    fingerprint: str
    request: AnalysisParameters
    items: tuple[LearningItem, ...]
    warnings: tuple[AnalysisWarning, ...]
    provenance: AnalysisProvenance
    created_at: datetime

    def __post_init__(self) -> None:
        if (
            self.created_at.tzinfo is None
            or self.created_at.utcoffset() != UTC.utcoffset(self.created_at)
        ):
            raise InvalidValueError("analysis creation time must be aware UTC")


@dataclass(frozen=True, slots=True)
class _GroundedCandidate:
    candidate: AnalyzerCandidate
    occurrences: tuple[Occurrence, ...]
    score: Decimal


def _excerpt(text: str) -> str:
    if len(text) <= MAX_EXCERPT_CHARACTERS:
        return text
    return f"{text[: MAX_EXCERPT_CHARACTERS - 1].rstrip()}…"


def _difficulty_score(candidate: AnalyzerCandidate, learner: LearnerProfile) -> Decimal:
    levels = {
        CefrLevel.A1: 1,
        CefrLevel.A2: 2,
        CefrLevel.B1: 3,
        CefrLevel.B2: 4,
        CefrLevel.C1: 5,
        CefrLevel.C2: 6,
    }
    estimated = candidate.estimated_cefr
    if (
        learner.cefr_level is CefrLevel.UNSPECIFIED
        or estimated not in levels
        or candidate.confidence is None
        or candidate.confidence < Decimal("0.6")
    ):
        return Decimal("0.6")
    difference = levels[estimated] - levels[learner.cefr_level]
    if difference >= 1:
        return Decimal("1")
    if difference == 0:
        return Decimal("0.8")
    if difference == -1:
        return Decimal("0.4")
    return Decimal("0.1")


def _score(
    candidate: AnalyzerCandidate,
    learner: LearnerProfile,
    occurrence_count: int,
) -> Decimal:
    confidence = (
        candidate.confidence if candidate.confidence is not None else Decimal("0.5")
    )
    repetition_bonus = min(Decimal("0.08"), Decimal("0.02") * (occurrence_count - 1))
    score = (
        candidate.salience * Decimal("0.5")
        + confidence * Decimal("0.3")
        + _difficulty_score(candidate, learner) * Decimal("0.2")
        + repetition_bonus
    )
    return max(Decimal("0"), min(Decimal("1"), score.quantize(Decimal("0.001"))))


def _is_noise(candidate: AnalyzerCandidate) -> bool:
    normalized = normalize_for_matching(candidate.expression)
    if len(normalized) < 2 or not any(character.isalpha() for character in normalized):
        return True
    return (
        candidate.expression.istitle()
        and "name" in normalize_for_matching(candidate.general_meaning)
        and " " not in candidate.expression.strip()
    )


def validate_and_rank_candidates(
    candidates: tuple[AnalyzerCandidate, ...],
    cues: tuple[AnalysisCue, ...],
    learner: LearnerProfile,
    item_limit: int,
) -> tuple[tuple[LearningItem, ...], tuple[AnalysisWarning, ...]]:
    """Ground, deduplicate, score, and cap untrusted analyzer candidates."""
    if item_limit < 1:
        raise InvalidValueError("item limit must be positive")
    cue_map = {cue.id: cue for cue in cues}
    grounded: list[_GroundedCandidate] = []
    warnings: set[AnalysisWarning] = set()

    for candidate in candidates:
        if _is_noise(candidate):
            warnings.add(AnalysisWarning.NOISE_REMOVED)
            continue
        expression = normalize_for_matching(candidate.expression)
        occurrences: list[Occurrence] = []
        for cue_id in dict.fromkeys(candidate.cue_ids):
            cue = cue_map.get(cue_id)
            if cue is None:
                raise InvalidAnalyzerOutputError("candidate references an unknown cue")
            if expression not in normalize_for_matching(cue.text):
                raise InvalidAnalyzerOutputError("candidate expression is not grounded")
            if not cue.context_only:
                occurrences.append(
                    Occurrence(cue.id, cue.display_range, _excerpt(cue.text))
                )
        if not occurrences:
            raise InvalidAnalyzerOutputError(
                "candidate is grounded only in context-only cues"
            )
        grounded.append(
            _GroundedCandidate(
                candidate,
                tuple(occurrences),
                _score(candidate, learner, len(occurrences)),
            )
        )

    deduplicated: dict[tuple[str, LearningItemType, str], _GroundedCandidate] = {}
    for item in grounded:
        key = (
            normalize_for_matching(item.candidate.normalized_form),
            item.candidate.type,
            normalize_for_matching(item.candidate.contextual_meaning),
        )
        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = item
            continue
        warnings.add(AnalysisWarning.DUPLICATES_REMOVED)
        selected = max((existing, item), key=lambda value: value.score)
        occurrence_map = {
            occurrence.cue_id: occurrence
            for occurrence in (*existing.occurrences, *item.occurrences)
        }
        deduplicated[key] = _GroundedCandidate(
            selected.candidate,
            tuple(occurrence_map.values()),
            _score(selected.candidate, learner, len(occurrence_map)),
        )

    ordered = sorted(
        deduplicated.values(),
        key=lambda value: (
            -value.score,
            normalize_for_matching(value.candidate.normalized_form),
            value.candidate.type.value,
        ),
    )[:item_limit]
    final_items = tuple(_to_learning_item(item) for item in ordered)
    return final_items, tuple(sorted(warnings, key=lambda warning: warning.value))


def _to_learning_item(item: _GroundedCandidate) -> LearningItem:
    candidate = item.candidate
    stable_key = "|".join(
        (
            normalize_for_matching(candidate.normalized_form),
            candidate.type.value,
            normalize_for_matching(candidate.contextual_meaning),
        )
    )
    item_id = hashlib.sha256(stable_key.encode()).hexdigest()[:16]
    return LearningItem(
        id=item_id,
        expression=candidate.expression,
        normalized_form=candidate.normalized_form,
        type=candidate.type,
        general_meaning=candidate.general_meaning,
        contextual_meaning=candidate.contextual_meaning,
        occurrences=item.occurrences,
        relevance_score=item.score,
        estimated_cefr=candidate.estimated_cefr,
        confidence=candidate.confidence,
        pronunciation=candidate.pronunciation,
        pronunciation_notation=candidate.pronunciation_notation,
        usage_note=candidate.usage_note,
    )


def analysis_fingerprint(
    *,
    transcript_digest: str,
    start_ms: int,
    end_ms: int,
    offset_ms: int,
    learner: LearnerProfile,
    item_limit: int,
    metadata: AnalyzerMetadata,
) -> str:
    """Hash every behavior-affecting input without exposing subtitle content."""
    data = {
        "digest": transcript_digest,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "offset_ms": offset_ms,
        "learner": learner.cefr_level.value,
        "item_limit": item_limit,
        "analyzer": metadata.analyzer_name,
        "model": metadata.model_identifier,
        "prompt": metadata.prompt_version,
        "schema": metadata.schema_version,
        "grounding": GROUNDING_VERSION,
        "ranking": RANKING_VERSION,
    }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
