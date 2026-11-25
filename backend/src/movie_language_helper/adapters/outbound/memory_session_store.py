"""Bounded single-process transcript session store."""

import asyncio
from collections import OrderedDict

from movie_language_helper.domain.session import TranscriptSession
from movie_language_helper.ports.runtime import Clock
from movie_language_helper.ports.session import (
    SessionLookup,
    SessionLookupStatus,
    SessionPutResult,
    TranscriptSessionStore,
)


class InMemoryTranscriptSessionStore(TranscriptSessionStore):
    """Lock-protected TTL storage with deterministic oldest-first eviction."""

    def __init__(self, clock: Clock, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("session capacity must be positive")
        self._clock = clock
        self._capacity = capacity
        self._sessions: OrderedDict[str, TranscriptSession] = OrderedDict()
        self._lock = asyncio.Lock()

    async def put(self, session: TranscriptSession) -> SessionPutResult:
        async with self._lock:
            self._remove_expired()
            self._sessions.pop(session.id, None)
            self._sessions[session.id] = session
            evicted: list[str] = []
            while len(self._sessions) > self._capacity:
                session_id, _ = self._sessions.popitem(last=False)
                evicted.append(session_id)
            return SessionPutResult(tuple(evicted))

    async def get(self, session_id: str) -> SessionLookup:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return SessionLookup(SessionLookupStatus.MISSING)
            if session.expires_at <= self._clock.now():
                del self._sessions[session_id]
                return SessionLookup(SessionLookupStatus.EXPIRED)
            return SessionLookup(SessionLookupStatus.FOUND, session)

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None

    async def cleanup_expired(self) -> tuple[str, ...]:
        async with self._lock:
            return self._remove_expired()

    def _remove_expired(self) -> tuple[str, ...]:
        now = self._clock.now()
        expired = tuple(
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        )
        for session_id in expired:
            del self._sessions[session_id]
        return expired
