"""Configurable offline analyzer adapter for development and tests."""

from movie_language_helper.domain.analysis import (
    AnalysisInput,
    AnalyzerMetadata,
    AnalyzerOutput,
)
from movie_language_helper.ports.analyzer import (
    AnalyzerFailure,
    AnalyzerFailureCode,
    LanguageAnalyzer,
)


def empty_fake_output() -> AnalyzerOutput:
    """Return stable metadata with no proposed candidates."""
    return AnalyzerOutput(
        candidates=(),
        metadata=AnalyzerMetadata(
            analyzer_name="offline-fake",
            model_identifier="deterministic-empty",
            prompt_version="fake-prompt-v1",
            schema_version="candidate-v1",
            latency_ms=0,
        ),
    )


class FakeLanguageAnalyzer(LanguageAnalyzer):
    """Return configured output/failures and record calls without any network."""

    def __init__(
        self,
        output: AnalyzerOutput | None = None,
        *,
        failure: AnalyzerFailureCode | None = None,
        unexpected_failure: bool = False,
    ) -> None:
        self._output = output or empty_fake_output()
        self._failure = failure
        self._unexpected_failure = unexpected_failure
        self.calls: list[AnalysisInput] = []

    async def analyze(self, analysis_input: AnalysisInput) -> AnalyzerOutput:
        self.calls.append(analysis_input)
        if self._unexpected_failure:
            raise RuntimeError("synthetic internal detail that must not escape")
        if self._failure is not None:
            raise AnalyzerFailure(self._failure, "synthetic provider detail")
        return self._output
