"""Deterministic subtitle and analyzer text normalization."""

import html
import re
import unicodedata
from dataclasses import dataclass

from movie_language_helper.domain.subtitle import CueFlag

HTML_TAG = re.compile(r"<[^>]*>")
ASS_OVERRIDE = re.compile(r"\{[^}]*\}")
SPACE_RUN = re.compile(r"[ \t\f\v]+")
ALL_WHITESPACE = re.compile(r"\s+")
NON_DIALOGUE = re.compile(
    r"^(?:[\[(].+[\])]|[♪♫♬\s]+)$",
    flags=re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class NormalizedCueText:
    """Safe display text and collapsed analyzer text for one cue."""

    source_text: str
    analysis_text: str
    flags: frozenset[CueFlag]


def normalize_cue_text(value: str) -> NormalizedCueText:
    """Remove markup, normalize line endings/space, and classify non-dialogue."""
    normalized = value.replace("\\N", "\n").replace("\\n", "\n")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    without_ass = ASS_OVERRIDE.sub("", normalized)
    without_markup = HTML_TAG.sub("", without_ass)
    decoded = html.unescape(without_markup)
    lines = [SPACE_RUN.sub(" ", line).strip() for line in decoded.split("\n")]
    source_text = "\n".join(line for line in lines if line).strip()
    analysis_text = ALL_WHITESPACE.sub(" ", source_text).strip()

    flags: set[CueFlag] = set()
    if without_markup != normalized or without_ass != normalized:
        flags.add(CueFlag.MARKUP_REMOVED)
    if analysis_text and NON_DIALOGUE.fullmatch(analysis_text):
        flags.add(CueFlag.NON_DIALOGUE)
        analysis_text = ""

    return NormalizedCueText(source_text, analysis_text, frozenset(flags))


def normalize_for_matching(value: str) -> str:
    """Normalize Unicode, case, and whitespace for local grounding."""
    return ALL_WHITESPACE.sub(
        " ", unicodedata.normalize("NFKC", value).casefold()
    ).strip()
