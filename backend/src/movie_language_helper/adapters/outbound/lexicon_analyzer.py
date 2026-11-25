"""Offline analyzer that matches a curated lexicon against subtitle cues.

It needs no network and no credentials, so it works as a demo mode and as a
baseline for the model-backed analyzer. It only finds expressions that are in
the lexicon, and the contextual meaning is the general one: it does not look
at the scene.
"""

from __future__ import annotations

from decimal import Decimal
from time import monotonic

from movie_language_helper.adapters.outbound.lexicon_data import ENTRIES, LexiconEntry
from movie_language_helper.domain.analysis import (
    AnalysisInput,
    AnalyzerCandidate,
    AnalyzerMetadata,
    AnalyzerOutput,
    LearningItemType,
)
from movie_language_helper.domain.normalization import normalize_for_matching
from movie_language_helper.ports.analyzer import LanguageAnalyzer

LEXICON_VERSION = "lexicon-v1"
_CONFIDENCE = Decimal("0.7")
_SALIENCE = {
    LearningItemType.IDIOM: Decimal("0.8"),
    LearningItemType.SLANG: Decimal("0.75"),
    LearningItemType.PHRASAL_VERB: Decimal("0.7"),
    LearningItemType.OTHER_EXPRESSION: Decimal("0.6"),
    LearningItemType.WORD: Decimal("0.5"),
}


class LexiconLanguageAnalyzer(LanguageAnalyzer):
    """Find lexicon expressions in the non-context cues of an analysis input."""

    def __init__(self, entries: tuple[LexiconEntry, ...] = ENTRIES) -> None:
        self._entries = entries

    async def analyze(self, analysis_input: AnalysisInput) -> AnalyzerOutput:
        started = monotonic()
        # (lemma, surface form) -> (entry, surface text, cue IDs in order)
        found: dict[tuple[str, str], tuple[LexiconEntry, str, list[str]]] = {}
        for cue in analysis_input.cues:
            if cue.context_only:
                continue
            for entry in self._entries:
                for pattern in entry.patterns:
                    for match in pattern.finditer(cue.text):
                        surface = match.group(0)
                        key = (entry.lemma, normalize_for_matching(surface))
                        _, _, cue_ids = found.setdefault(key, (entry, surface, []))
                        if cue.id not in cue_ids:
                            cue_ids.append(cue.id)
        candidates = tuple(
            AnalyzerCandidate(
                expression=surface,
                normalized_form=entry.lemma,
                type=entry.type,
                general_meaning=entry.meaning,
                contextual_meaning=entry.meaning,
                cue_ids=tuple(cue_ids),
                estimated_cefr=entry.cefr,
                confidence=_CONFIDENCE,
                salience=_SALIENCE[entry.type],
                usage_note=entry.usage_note,
            )
            for entry, surface, cue_ids in found.values()
        )
        return AnalyzerOutput(
            candidates=candidates,
            metadata=AnalyzerMetadata(
                analyzer_name="offline-lexicon",
                model_identifier=f"{LEXICON_VERSION}-{len(self._entries)}-entries",
                prompt_version="not-applicable",
                schema_version="candidate-v1",
                latency_ms=int((monotonic() - started) * 1000),
            ),
        )
