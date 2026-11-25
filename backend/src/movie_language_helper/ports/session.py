"""Transcript session storage port and explicit lookup/eviction outcomes."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from movie_language_helper.domain.session import TranscriptSession


class SessionLookupStatus(StrEnum):
    """Distinguish absent and observably expired sessions."""

    FOUND = "found"
    MISSING = "missing"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class SessionLookup:
    """A session lookup with explicit expiry semantics."""

    status: SessionLookupStatus
    session: TranscriptSession | None = None


@dataclass(frozen=True, slots=True)
class SessionPutResult:
    """Capacity evictions caused by storing a session."""

    evicted_session_ids: tuple[str, ...] = ()


class TranscriptSessionStore(Protocol):
    """Bounded transient transcript-session storage."""

    async def put(self, session: TranscriptSession) -> SessionPutResult: ...

    async def get(self, session_id: str) -> SessionLookup: ...

    async def delete(self, session_id: str) -> bool: ...

    async def cleanup_expired(self) -> tuple[str, ...]: ...
