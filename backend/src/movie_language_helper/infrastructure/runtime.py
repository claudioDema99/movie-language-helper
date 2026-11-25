"""Production clock and opaque capability ID adapters."""

import secrets
from datetime import UTC, datetime

from movie_language_helper.ports.runtime import Clock, IdGenerator


class SystemClock(Clock):
    """Return aware UTC wall-clock time."""

    def now(self) -> datetime:
        return datetime.now(tz=UTC)


class SecureIdGenerator(IdGenerator):
    """Generate cryptographically random URL-safe identifiers."""

    def new(self) -> str:
        return secrets.token_urlsafe(24)
