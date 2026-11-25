"""Provider-neutral movie identity values."""

from dataclasses import dataclass
from enum import StrEnum

from movie_language_helper.domain.errors import InvalidValueError


class MediaType(StrEnum):
    """Media types understood by the MVP."""

    MOVIE = "movie"


@dataclass(frozen=True, slots=True)
class ExternalId:
    """An opaque identity scoped by provider and media type."""

    provider: str
    media_type: MediaType
    value: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise InvalidValueError("external ID provider must not be blank")
        if not self.value.strip():
            raise InvalidValueError("external ID value must not be blank")


@dataclass(frozen=True, slots=True)
class MovieMatch:
    """Provider-neutral movie search result without licensed artwork."""

    id: ExternalId
    title: str
    year: int | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise InvalidValueError("movie title must not be blank")
        if self.year is not None and not 1870 <= self.year <= 2200:
            raise InvalidValueError("movie year is outside the supported range")


@dataclass(frozen=True, slots=True)
class SubtitleCandidate:
    """English subtitle release metadata safe to show before downloading."""

    provider: str
    id: str
    movie_id: ExternalId
    release_name: str
    language: str
    hearing_impaired: bool | None = None
    format: str | None = None
    fps: float | None = None

    def __post_init__(self) -> None:
        required = (self.provider, self.id, self.release_name, self.language)
        if any(not value.strip() for value in required):
            raise InvalidValueError("subtitle candidate fields must not be blank")
        if self.language != "en":
            raise InvalidValueError("MVP subtitle candidates must be English")
        if self.fps is not None and not 1 <= self.fps <= 240:
            raise InvalidValueError("subtitle FPS is outside the supported range")
