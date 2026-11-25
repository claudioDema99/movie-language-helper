"""Deterministic quality metrics for a rights-cleared analyzer corpus."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from movie_language_helper.domain.analysis import AnalysisInput, AnalyzerOutput
from movie_language_helper.domain.normalization import normalize_for_matching
from movie_language_helper.ports.analyzer import LanguageAnalyzer


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One rights-cleared input and its human-approved useful expressions."""

    id: str
    analysis_input: AnalysisInput
    expected_expressions: frozenset[str]


@dataclass(frozen=True, slots=True)
class EvaluationThresholds:
    """Release thresholds chosen by the product owner before model selection."""

    minimum_precision: Decimal
    minimum_recall: Decimal
    minimum_useful_at_n: Decimal
    maximum_duplicate_rate: Decimal
    maximum_unsupported_rate: Decimal


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    cases: int
    precision: Decimal
    recall: Decimal
    useful_at_n: Decimal
    duplicate_rate: Decimal
    unsupported_rate: Decimal
    average_latency_ms: Decimal
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal | None
    passed: bool


def _ratio(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) if denominator else Decimal("0")


async def evaluate(
    analyzer: LanguageAnalyzer,
    cases: tuple[GoldenCase, ...],
    thresholds: EvaluationThresholds,
    *,
    input_cost_per_million: Decimal | None = None,
    output_cost_per_million: Decimal | None = None,
) -> EvaluationReport:
    """Run an analyzer without retaining or logging corpus content."""
    if not cases:
        raise ValueError("at least one golden case is required")
    true_positive = expected_total = proposed_total = duplicates = unsupported = 0
    useful_cases = latency_total = input_tokens = output_tokens = 0

    for case in cases:
        output: AnalyzerOutput = await analyzer.analyze(case.analysis_input)
        expected = {
            normalize_for_matching(value) for value in case.expected_expressions
        }
        proposed = [
            normalize_for_matching(candidate.expression)
            for candidate in output.candidates
        ]
        unique = set(proposed)
        true_positive += len(unique & expected)
        expected_total += len(expected)
        proposed_total += len(proposed)
        duplicates += len(proposed) - len(unique)
        cue_ids = {cue.id for cue in case.analysis_input.cues if not cue.context_only}
        unsupported += sum(
            1 for candidate in output.candidates if not set(candidate.cue_ids) & cue_ids
        )
        useful_cases += int(bool(unique & expected))
        latency_total += output.metadata.latency_ms
        input_tokens += output.metadata.input_tokens or 0
        output_tokens += output.metadata.output_tokens or 0

    precision = _ratio(true_positive, proposed_total)
    recall = _ratio(true_positive, expected_total)
    useful_at_n = _ratio(useful_cases, len(cases))
    duplicate_rate = _ratio(duplicates, proposed_total)
    unsupported_rate = _ratio(unsupported, proposed_total)
    estimated_cost: Decimal | None = None
    if input_cost_per_million is not None and output_cost_per_million is not None:
        estimated_cost = (
            Decimal(input_tokens) * input_cost_per_million
            + Decimal(output_tokens) * output_cost_per_million
        ) / Decimal(1_000_000)

    passed = (
        precision >= thresholds.minimum_precision
        and recall >= thresholds.minimum_recall
        and useful_at_n >= thresholds.minimum_useful_at_n
        and duplicate_rate <= thresholds.maximum_duplicate_rate
        and unsupported_rate <= thresholds.maximum_unsupported_rate
    )
    return EvaluationReport(
        cases=len(cases),
        precision=precision,
        recall=recall,
        useful_at_n=useful_at_n,
        duplicate_rate=duplicate_rate,
        unsupported_rate=unsupported_rate,
        average_latency_ms=Decimal(latency_total) / Decimal(len(cases)),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost,
        passed=passed,
    )
