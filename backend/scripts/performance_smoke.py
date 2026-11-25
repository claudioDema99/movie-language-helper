"""Exercise parser and extraction at configured maximum cue count."""

import time

from movie_language_helper.adapters.outbound.srt import (
    Pysubs2SrtParser,
    SrtParserConfig,
)
from movie_language_helper.domain.extraction import ContextPolicy, extract_analysis_cues
from movie_language_helper.domain.subtitle import TranscriptLimits, TranscriptSourceKind
from movie_language_helper.domain.time import SyncOffset, TimeRange, Timestamp
from movie_language_helper.ports.subtitle import SubtitlePayload


def _maximum_srt(cues: int) -> bytes:
    blocks: list[str] = []
    for index in range(1, cues + 1):
        seconds = index % 60
        minutes = (index // 60) % 60
        hours = index // 3600
        blocks.append(
            f"{index}\n{hours:02}:{minutes:02}:{seconds:02},000 --> "
            f"{hours:02}:{minutes:02}:{seconds:02},500\nSynthetic cue {index}."
        )
    return ("\n\n".join(blocks) + "\n").encode()


def main() -> None:
    cue_limit = 20_000
    content = _maximum_srt(cue_limit)
    parser = Pysubs2SrtParser(
        SrtParserConfig(
            max_input_bytes=2 * 1024 * 1024,
            transcript_limits=TranscriptLimits(
                max_cues=cue_limit,
                max_characters_per_cue=10_000,
                max_total_characters=2_000_000,
            ),
        )
    )
    started = time.perf_counter()
    transcript = parser.parse(
        SubtitlePayload(content, TranscriptSourceKind.SYNTHETIC, "maximum.srt", "srt")
    )
    parse_seconds = time.perf_counter() - started
    started = time.perf_counter()
    extracted = extract_analysis_cues(
        transcript,
        TimeRange(Timestamp(60_000), Timestamp(660_000)),
        SyncOffset(),
        ContextPolicy(2, 30_000),
    )
    extraction_seconds = time.perf_counter() - started
    assert len(transcript.cues) == cue_limit
    assert extracted
    assert parse_seconds < 10
    assert extraction_seconds < 2
    print(
        f"parsed {cue_limit} cues in {parse_seconds:.3f}s; "
        f"extracted {len(extracted)} cues in {extraction_seconds:.3f}s"
    )


if __name__ == "__main__":
    main()
