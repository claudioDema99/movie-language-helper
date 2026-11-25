"""Subtitle normalization policy tests."""

from movie_language_helper.domain.normalization import (
    normalize_cue_text,
    normalize_for_matching,
)
from movie_language_helper.domain.subtitle import CueFlag


def test_normalization_removes_ass_html_decodes_and_collapses_space() -> None:
    result = normalize_cue_text(r"{\i1}<b>Tom &amp; Jerry</b>\N  Hello   there")
    assert result.source_text == "Tom & Jerry\nHello there"
    assert result.analysis_text == "Tom & Jerry Hello there"
    assert CueFlag.MARKUP_REMOVED in result.flags


def test_non_dialogue_is_retained_for_display_but_not_analysis() -> None:
    result = normalize_cue_text("[music]")
    assert result.source_text == "[music]"
    assert result.analysis_text == ""
    assert result.flags == frozenset({CueFlag.NON_DIALOGUE})


def test_matching_normalization_is_unicode_case_and_space_stable() -> None:
    assert normalize_for_matching("  ＣＡＦÉ\nDay ") == "café day"
