"""Stable provider-independent domain errors."""


class DomainError(ValueError):
    """Base class for violations of domain invariants or policies."""

    code = "domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidValueError(DomainError):
    """A value cannot form a valid domain object."""

    code = "invalid_value"


class ResourceLimitError(DomainError):
    """A configured bounded-resource policy was exceeded."""

    code = "resource_limit_exceeded"


class SubtitleParseError(DomainError):
    """A subtitle payload cannot produce a valid transcript."""

    code = "subtitle_parse_failed"


class UnsupportedSubtitleError(DomainError):
    """A subtitle payload uses an unsupported format or encoding."""

    code = "unsupported_subtitle"


class EmptyIntervalError(DomainError):
    """No dialogue cue overlaps an analysis interval."""

    code = "empty_interval"


class InvalidAnalyzerOutputError(DomainError):
    """Untrusted analyzer output failed local grounding or validation."""

    code = "analyzer_invalid_output"
