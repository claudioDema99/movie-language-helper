"""Contract tests for the bounded pysubs2 SRT adapter."""

import hashlib
from types import SimpleNamespace

import pytest

from movie_language_helper.adapters.outbound.srt import (
    MalformedCuePolicy,
    Pysubs2SrtParser,
    SrtParserConfig,
)
from movie_language_helper.domain.errors import (
    ResourceLimitError,
    SubtitleParseError,
    UnsupportedSubtitleError,
)
from movie_language_helper.domain.subtitle import (
    CueFlag,
    TranscriptLimits,
    TranscriptSourceKind,
    TranscriptWarningCode,
)
from movie_language_helper.ports.subtitle import SubtitlePayload


def payload(content: bytes, filename: str = "synthetic.srt") -> SubtitlePayload:
    """Build a synthetic upload payload."""
    return SubtitlePayload(
        content=content,
        source_kind=TranscriptSourceKind.SYNTHETIC,
        filename=filename,
        declared_format="srt",
        content_type="application/x-subrip",
    )


def test_parses_utf8_bom_crlf_multiline_markup_and_overlaps() -> None:
    content = (
        b"\xef\xbb\xbf2\r\n00:00:02,000 --> 00:00:04,000\r\n"
        b"<i>Second</i> line\r\ncontinues\r\n\r\n"
        b"1\r\n00:00:01,000 --> 00:00:03,000\r\nFirst\r\n"
    )

    result = Pysubs2SrtParser().parse(payload(content))

    assert tuple(cue.source_index for cue in result.cues) == (1, 2)
    assert result.cues[1].source_text == "Second line\ncontinues"
    assert result.cues[1].analysis_text == "Second line continues"
    assert CueFlag.MARKUP_REMOVED in result.cues[1].flags
    assert result.content_digest == hashlib.sha256(content).hexdigest()


def test_duplicate_source_indices_are_warning_not_identity() -> None:
    content = (
        b"1\n00:00:00,000 --> 00:00:01,000\nOne\n\n"
        b"1\n00:00:01,000 --> 00:00:02,000\nTwo\n"
    )

    result = Pysubs2SrtParser().parse(payload(content))

    assert tuple(cue.id for cue in result.cues) == ("cue-1", "cue-2")
    assert result.warnings[0].code is TranscriptWarningCode.DUPLICATE_SOURCE_INDEX


def test_cp1252_fallback_is_explicit_warning() -> None:
    content = "1\n00:00:00,000 --> 00:00:01,000\nCaf\xe9\n".encode("cp1252")

    result = Pysubs2SrtParser().parse(payload(content))

    assert result.cues[0].source_text == "Caf\xe9"
    assert result.warnings[0].code is TranscriptWarningCode.ENCODING_FALLBACK


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"1\nnot a timestamp\nBroken\n",
        b"1\n00:00:01,000 --> 00:00:01,000\nZero\n",
    ],
)
def test_rejects_empty_malformed_and_zero_duration_srt(content: bytes) -> None:
    with pytest.raises(SubtitleParseError):
        Pysubs2SrtParser().parse(payload(content))


def test_optional_malformed_drop_policy_is_typed_warning() -> None:
    content = b"1\n00:00:00,000 --> 00:00:01,000\nValid\n\nbroken\nblock\n"
    parser = Pysubs2SrtParser(
        SrtParserConfig(malformed_cue_policy=MalformedCuePolicy.DROP_WITH_WARNING)
    )

    result = parser.parse(payload(content))

    assert len(result.cues) == 1
    assert result.warnings[0].code is TranscriptWarningCode.MALFORMED_CUE_DROPPED


def test_input_byte_limit_accepts_boundary_and_rejects_one_byte_over() -> None:
    content = b"1\n00:00:00,000 --> 00:00:01,000\nOne\n"
    parser = Pysubs2SrtParser(SrtParserConfig(max_input_bytes=len(content)))

    assert parser.parse(payload(content)).cues[0].source_text == "One"
    with pytest.raises(ResourceLimitError):
        parser.parse(payload(content + b" "))


def test_cue_and_total_text_limits_are_enforced() -> None:
    content = b"1\n00:00:00,000 --> 00:00:01,000\n12345\n"
    parser = Pysubs2SrtParser(
        SrtParserConfig(
            transcript_limits=TranscriptLimits(
                max_cues=1,
                max_characters_per_cue=4,
                max_total_characters=4,
            )
        )
    )

    with pytest.raises(ResourceLimitError):
        parser.parse(payload(content))


def test_rejects_non_srt_filename_and_declared_format() -> None:
    content = b"1\n00:00:00,000 --> 00:00:01,000\nOne\n"
    with pytest.raises(UnsupportedSubtitleError):
        Pysubs2SrtParser().parse(payload(content, "synthetic.vtt"))

    wrong_format = SubtitlePayload(
        content,
        TranscriptSourceKind.SYNTHETIC,
        "synthetic.srt",
        "vtt",
    )
    with pytest.raises(UnsupportedSubtitleError):
        Pysubs2SrtParser().parse(wrong_format)


@pytest.mark.parametrize(
    "values",
    [{"max_input_bytes": 0}, {"encodings": ()}],
)
def test_parser_configuration_requires_bounds(values: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        SrtParserConfig(**values)  # type: ignore[arg-type]


def test_rejects_unsupported_encoding_and_all_dropped_blocks() -> None:
    encoded = "1\n00:00:00,000 --> 00:00:01,000\nCafé\n".encode("cp1252")
    with pytest.raises(UnsupportedSubtitleError, match="encoding"):
        Pysubs2SrtParser(SrtParserConfig(encodings=("ascii",))).parse(payload(encoded))
    parser = Pysubs2SrtParser(
        SrtParserConfig(malformed_cue_policy=MalformedCuePolicy.DROP_WITH_WARNING)
    )
    with pytest.raises(SubtitleParseError, match="no valid"):
        parser.parse(payload(b"broken\nblock\n"))


def test_wraps_library_failure_and_rejects_event_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"1\n00:00:00,000 --> 00:00:01,000\nOne\n"

    def fail(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("library detail")

    monkeypatch.setattr("pysubs2.SSAFile.from_string", fail)
    with pytest.raises(SubtitleParseError, match="parsing failed"):
        Pysubs2SrtParser().parse(payload(content))

    monkeypatch.setattr(
        "pysubs2.SSAFile.from_string",
        lambda *_args, **_kwargs: SimpleNamespace(events=[]),
    )
    with pytest.raises(SubtitleParseError, match="unexpected cue count"):
        Pysubs2SrtParser().parse(payload(content))


def test_normalized_empty_total_text_and_cue_count_limits() -> None:
    empty_markup = b"1\n00:00:00,000 --> 00:00:01,000\n<i></i>\n"
    with pytest.raises(SubtitleParseError, match="normalization"):
        Pysubs2SrtParser().parse(payload(empty_markup))

    one = b"1\n00:00:00,000 --> 00:00:01,000\n12345\n"
    total_parser = Pysubs2SrtParser(
        SrtParserConfig(
            transcript_limits=TranscriptLimits(
                max_cues=2,
                max_characters_per_cue=10,
                max_total_characters=4,
            )
        )
    )
    with pytest.raises(ResourceLimitError, match="transcript text"):
        total_parser.parse(payload(one))

    two = one + b"\n2\n00:00:01,000 --> 00:00:02,000\nTwo\n"
    count_parser = Pysubs2SrtParser(
        SrtParserConfig(
            transcript_limits=TranscriptLimits(
                max_cues=1,
                max_characters_per_cue=10,
                max_total_characters=20,
            )
        )
    )
    with pytest.raises(ResourceLimitError, match="cue count"):
        count_parser.parse(payload(two))
