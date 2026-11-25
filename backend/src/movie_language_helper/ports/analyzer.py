"""Language analyzer port and stable upstream failure taxonomy."""

from enum import StrEnum
from typing import Protocol

from movie_language_helper.domain.analysis import AnalysisInput, AnalyzerOutput


class AnalyzerFailureCode(StrEnum):
    """Provider-neutral analyzer failures."""

    UNAVAILABLE = "analyzer_unavailable"
    RATE_LIMITED = "analyzer_rate_limited"
    REFUSED = "analyzer_refused"
    INCOMPLETE = "analyzer_incomplete"
    INVALID_OUTPUT = "analyzer_invalid_output"


class AnalyzerFailure(RuntimeError):
    """A safe failure raised through the analyzer port."""

    def __init__(self, code: AnalyzerFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class LanguageAnalyzer(Protocol):
    """Propose untrusted learning candidates for selected cues."""

    async def analyze(self, analysis_input: AnalysisInput) -> AnalyzerOutput: ...
