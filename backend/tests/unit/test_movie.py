"""Tests for provider-scoped movie identity."""

import pytest

from movie_language_helper.domain.errors import InvalidValueError
from movie_language_helper.domain.movie import (
    ExternalId,
    MediaType,
    MovieMatch,
    SubtitleCandidate,
)


def test_external_id_equality_includes_provider_and_media_type() -> None:
    subdl = ExternalId("subdl", MediaType.MOVIE, "42")
    other = ExternalId("other", MediaType.MOVIE, "42")

    assert subdl != other
    assert subdl == ExternalId("subdl", MediaType.MOVIE, "42")


@pytest.mark.parametrize(("provider", "value"), [("", "42"), ("subdl", " ")])
def test_external_id_rejects_blank_components(provider: str, value: str) -> None:
    with pytest.raises(InvalidValueError):
        ExternalId(provider, MediaType.MOVIE, value)


def test_movie_and_subtitle_metadata_are_provider_neutral() -> None:
    movie_id = ExternalId("subdl", MediaType.MOVIE, "42")
    movie = MovieMatch(movie_id, "Synthetic Movie", 2020)
    subtitle = SubtitleCandidate(
        "subdl", "7", movie_id, "Synthetic.Release", "en", False, "srt", 24
    )
    assert movie.year == 2020
    assert subtitle.fps == 24


@pytest.mark.parametrize(
    "factory",
    [
        lambda: MovieMatch(ExternalId("p", MediaType.MOVIE, "1"), ""),
        lambda: MovieMatch(ExternalId("p", MediaType.MOVIE, "1"), "Title", 1700),
        lambda: SubtitleCandidate(
            "", "1", ExternalId("p", MediaType.MOVIE, "1"), "release", "en"
        ),
        lambda: SubtitleCandidate(
            "p", "1", ExternalId("p", MediaType.MOVIE, "1"), "release", "fr"
        ),
        lambda: SubtitleCandidate(
            "p", "1", ExternalId("p", MediaType.MOVIE, "1"), "release", "en", fps=0
        ),
    ],
)
def test_movie_and_subtitle_metadata_reject_invalid_values(factory: object) -> None:
    with pytest.raises(InvalidValueError):
        factory()  # type: ignore[operator]
