"""Short-lived transcript session entity."""

from dataclasses import dataclass
from datetime import UTC, datetime

from movie_language_helper.domain.errors import InvalidValueError
from movie_language_helper.domain.subtitle import Transcript


def _is_aware_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(value)


@dataclass(frozen=True, slots=True)
class TranscriptSession:
    """A capability-addressed, expiring transcript held only in memory."""

    id: str
    transcript: Transcript
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidValueError("session ID must not be blank")
        if not _is_aware_utc(self.created_at) or not _is_aware_utc(self.expires_at):
            raise InvalidValueError("session timestamps must be aware UTC datetimes")
        if self.expires_at <= self.created_at:
            raise InvalidValueError("session expiry must be later than creation")
