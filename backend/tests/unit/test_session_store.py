"""TTL and capacity behavior for the in-memory session adapter."""

import asyncio
from datetime import timedelta

import pytest

from movie_language_helper.adapters.outbound.memory_session_store import (
    InMemoryTranscriptSessionStore,
)
from movie_language_helper.ports.session import SessionLookupStatus
from tests.factories import cue, session
from tests.fakes import MutableClock


def test_store_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError, match="capacity"):
        InMemoryTranscriptSessionStore(MutableClock(), 0)


def test_store_distinguishes_missing_expired_and_found() -> None:
    async def scenario() -> None:
        clock = MutableClock()
        store = InMemoryTranscriptSessionStore(clock, 2)
        current = session(cue("cue-1", 0, 1000, "Hello"), created_at=clock.now())
        assert (await store.get("unknown")).status is SessionLookupStatus.MISSING
        assert (await store.put(current)).evicted_session_ids == ()
        found = await store.get(current.id)
        assert found.status is SessionLookupStatus.FOUND
        assert found.session is current
        clock.advance(timedelta(minutes=30))
        assert (await store.get(current.id)).status is SessionLookupStatus.EXPIRED
        assert (await store.get(current.id)).status is SessionLookupStatus.MISSING

    asyncio.run(scenario())


def test_store_evicts_oldest_replaces_and_cleans_up() -> None:
    async def scenario() -> None:
        clock = MutableClock()
        store = InMemoryTranscriptSessionStore(clock, 2)
        synthetic_cue = cue("cue-1", 0, 1, "text")
        first = session(synthetic_cue, session_id="first", created_at=clock.now())
        second = session(synthetic_cue, session_id="second", created_at=clock.now())
        third = session(synthetic_cue, session_id="third", created_at=clock.now())
        await store.put(first)
        await store.put(second)
        assert (await store.put(second)).evicted_session_ids == ()
        assert (await store.put(third)).evicted_session_ids == ("first",)
        assert not await store.delete("missing")
        assert await store.delete("second")
        expired = session(
            synthetic_cue,
            session_id="expired",
            created_at=clock.now(),
            ttl=timedelta(seconds=1),
        )
        await store.put(expired)
        clock.advance(timedelta(seconds=1))
        assert await store.cleanup_expired() == ("expired",)

    asyncio.run(scenario())
