"""Analyzer evaluation metrics over synthetic examples."""

import asyncio
from decimal import Decimal

import pytest

from movie_language_helper.domain.analysis import (
    AnalysisCue,
    AnalysisInput,
    AnalyzerCandidate,
    AnalyzerMetadata,
    AnalyzerOutput,
    LearnerProfile,
    LearningItemType,
)
from movie_language_helper.domain.time import TimeRange, Timestamp
from movie_language_helper.evaluation.harness import (
    EvaluationThresholds,
    GoldenCase,
    evaluate,
)


class _SequenceAnalyzer:
    def __init__(self, outputs: list[AnalyzerOutput]) -> None:
        self.outputs = outputs

    async def analyze(self, _analysis_input: AnalysisInput) -> AnalyzerOutput:
        return self.outputs.pop(0)


def _candidate(expression: str, cue_id: str = "cue-1") -> AnalyzerCandidate:
    return AnalyzerCandidate(
        expression=expression,
        normalized_form=expression.casefold(),
        type=LearningItemType.OTHER_EXPRESSION,
        general_meaning="Synthetic meaning",
        contextual_meaning="Synthetic context",
        cue_ids=(cue_id,),
    )


def _output(*candidates: AnalyzerCandidate) -> AnalyzerOutput:
    return AnalyzerOutput(
        candidates,
        AnalyzerMetadata("fake", "fixture", "prompt", "schema", 10, 100, 20),
    )


def _case(case_id: str, *expected: str) -> GoldenCase:
    analysis_input = AnalysisInput(
        (
            AnalysisCue(
                "cue-1",
                TimeRange(Timestamp(0), Timestamp(1_000)),
                "Synthetic dialogue",
                False,
            ),
        ),
        LearnerProfile(),
        5,
    )
    return GoldenCase(case_id, analysis_input, frozenset(expected))


def _thresholds() -> EvaluationThresholds:
    return EvaluationThresholds(
        Decimal("0.5"),
        Decimal("0.5"),
        Decimal("0.5"),
        Decimal("0.5"),
        Decimal("0.5"),
    )


def test_evaluation_reports_quality_usage_and_cost() -> None:
    analyzer = _SequenceAnalyzer(
        [
            _output(
                _candidate("Call it a day"),
                _candidate("call it a day"),
                _candidate("unsupported", "missing"),
            ),
            _output(),
        ]
    )
    report = asyncio.run(
        evaluate(
            analyzer,
            (_case("one", "call it a day"), _case("two", "break a leg")),
            _thresholds(),
            input_cost_per_million=Decimal("2"),
            output_cost_per_million=Decimal("8"),
        )
    )
    assert report.precision == Decimal(1) / Decimal(3)
    assert report.recall == Decimal("0.5")
    assert report.useful_at_n == Decimal("0.5")
    assert report.duplicate_rate == Decimal(1) / Decimal(3)
    assert report.unsupported_rate == Decimal(1) / Decimal(3)
    assert report.average_latency_ms == 10
    assert report.input_tokens == 200
    assert report.output_tokens == 40
    assert report.estimated_cost_usd == Decimal("0.00072")
    assert report.passed is False


def test_evaluation_without_token_prices_can_pass() -> None:
    report = asyncio.run(
        evaluate(
            _SequenceAnalyzer([_output(_candidate("useful"))]),
            (_case("one", "useful"),),
            _thresholds(),
        )
    )
    assert report.passed is True
    assert report.estimated_cost_usd is None


def test_evaluation_rejects_empty_corpus() -> None:
    with pytest.raises(ValueError, match="golden case"):
        asyncio.run(evaluate(_SequenceAnalyzer([]), (), _thresholds()))
