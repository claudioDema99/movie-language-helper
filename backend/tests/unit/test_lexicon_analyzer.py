"""Offline lexicon analyzer: matching, grounding and container wiring."""

import asyncio
from decimal import Decimal

from movie_language_helper.adapters.outbound.lexicon_analyzer import (
    LexiconLanguageAnalyzer,
)
from movie_language_helper.adapters.outbound.lexicon_data import ENTRIES
from movie_language_helper.domain.analysis import (
    AnalysisCue,
    AnalysisInput,
    AnalyzerOutput,
    CefrLevel,
    LearnerProfile,
    LearningItemType,
    validate_and_rank_candidates,
)
from movie_language_helper.domain.time import TimeRange, Timestamp
from movie_language_helper.infrastructure.config import Settings
from movie_language_helper.infrastructure.container import build_services


def cue(cue_id: str, text: str, *, context_only: bool = False) -> AnalysisCue:
    return AnalysisCue(
        cue_id, TimeRange(Timestamp(1000), Timestamp(2000)), text, context_only
    )


def analyze(*cues: AnalysisCue) -> AnalyzerOutput:
    analysis_input = AnalysisInput(cues, LearnerProfile(CefrLevel.B1), item_limit=12)
    return asyncio.run(LexiconLanguageAnalyzer().analyze(analysis_input))


def lemmas(output: AnalyzerOutput) -> set[str]:
    return {candidate.normalized_form for candidate in output.candidates}


def test_finds_inflected_and_separable_phrasal_verbs() -> None:
    output = analyze(
        cue("1", "She gave up after a week."),
        cue("2", "We'll figure it out tomorrow."),
    )
    by_lemma = {c.normalized_form: c for c in output.candidates}
    assert by_lemma["give up"].expression == "gave up"
    assert by_lemma["give up"].type is LearningItemType.PHRASAL_VERB
    assert by_lemma["figure out"].expression == "figure it out"
    assert by_lemma["figure out"].cue_ids == ("2",)


def test_finds_idioms_with_variable_parts_and_informal_speech() -> None:
    output = analyze(
        cue("1", "Quit pulling my leg, that car cost him an arm and a leg."),
        cue("2", "I'm gonna hit the sack."),
    )
    assert {"pull someone's leg", "cost an arm and a leg", "gonna", "hit the sack"} <= (
        lemmas(output)
    )
    gonna = next(c for c in output.candidates if c.normalized_form == "gonna")
    assert gonna.usage_note is not None
    assert gonna.type is LearningItemType.SLANG


def test_matching_is_case_insensitive_and_respects_word_boundaries() -> None:
    output = analyze(cue("1", "OUT OF THE BLUE she called."), cue("2", "Nogonna."))
    assert lemmas(output) == {"out of the blue"}
    assert output.candidates[0].expression == "OUT OF THE BLUE"


def test_groups_repeated_expression_and_skips_context_only_cues() -> None:
    output = analyze(
        cue("1", "No way."),
        cue("2", "No way!"),
        cue("3", "no way", context_only=True),
    )
    assert len(output.candidates) == 1
    assert output.candidates[0].cue_ids == ("1", "2")


def test_same_cue_matched_twice_is_listed_once() -> None:
    output = analyze(cue("1", "No way, no way."))
    assert output.candidates[0].cue_ids == ("1",)


def test_no_match_returns_empty_output_with_metadata() -> None:
    output = analyze(cue("1", "The weather is nice today."))
    assert output.candidates == ()
    assert output.metadata.analyzer_name == "offline-lexicon"
    assert output.metadata.model_identifier.endswith(f"{len(ENTRIES)}-entries")
    assert output.metadata.latency_ms >= 0


def test_output_passes_local_grounding_and_ranking() -> None:
    cues = (
        cue("1", "Long story short, he showed up late and we broke up."),
        cue("2", "Don't freak out, it's a piece of cake."),
    )
    output = analyze(*cues)
    items, _ = validate_and_rank_candidates(
        output.candidates, cues, LearnerProfile(CefrLevel.B1), item_limit=12
    )
    assert {item.normalized_form for item in items} == {
        "long story short",
        "show up",
        "break up",
        "freak out",
        "a piece of cake",
    }
    assert all(c.confidence == Decimal("0.7") for c in output.candidates)


def test_every_lexicon_entry_matches_its_own_lemma_or_a_form() -> None:
    samples = {
        "pull someone's leg": "you're pulling my leg",
        "lose one's mind": "I'm losing my mind",
        "cut it out": "cut it out",
    }
    for entry in ENTRIES:
        text = samples.get(entry.lemma, entry.lemma)
        assert any(p.search(text) for p in entry.patterns), entry.lemma


def test_container_selects_lexicon_analyzer_when_enabled() -> None:
    services = build_services(Settings(lexicon_analyzer_enabled=True))
    assert isinstance(services.analyze_interval._analyzer, LexiconLanguageAnalyzer)
