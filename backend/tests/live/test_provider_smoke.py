"""Opt-in smoke checks; never enabled by credentials alone."""

import asyncio
import os

import httpx
import pytest
from openai import AsyncOpenAI

from movie_language_helper.adapters.outbound.openai_analyzer import (
    OpenAIResponsesAnalyzer,
)
from movie_language_helper.adapters.outbound.subdl import SubDLAdapter
from movie_language_helper.domain.analysis import (
    AnalysisCue,
    AnalysisInput,
    LearnerProfile,
)
from movie_language_helper.domain.time import TimeRange, Timestamp

pytestmark = pytest.mark.live
GATE_OPEN = os.getenv("MLH_LIVE_GATE_ACKNOWLEDGED") == "yes"


@pytest.mark.skipif(
    not GATE_OPEN or os.getenv("MLH_OPENAI_LIVE_SMOKE") != "1",
    reason="OpenAI live smoke requires explicit policy gate and opt-in",
)
def test_openai_live_structured_response() -> None:
    async def scenario() -> None:
        key = os.environ["MLH_OPENAI_API_KEY"]
        model = os.environ["MLH_OPENAI_MODEL"]
        client = AsyncOpenAI(api_key=key, max_retries=0)
        try:
            adapter = OpenAIResponsesAnalyzer(
                client, model=model, max_output_tokens=800, timeout_seconds=20
            )
            result = await adapter.analyze(
                AnalysisInput(
                    (
                        AnalysisCue(
                            "cue-1",
                            TimeRange(Timestamp(0), Timestamp(2_000)),
                            "That synthetic puzzle was a piece of cake.",
                            False,
                        ),
                    ),
                    LearnerProfile(),
                    3,
                )
            )
            assert result.metadata.model_identifier == model
        finally:
            await client.close()

    asyncio.run(scenario())


@pytest.mark.skipif(
    not GATE_OPEN or os.getenv("MLH_SUBDL_LIVE_SMOKE") != "1",
    reason="SubDL live smoke requires explicit policy gate and opt-in",
)
def test_subdl_live_search_list_and_download() -> None:
    async def scenario() -> None:
        key = os.environ["MLH_SUBDL_API_KEY"]
        movie_id = os.environ["MLH_SUBDL_SMOKE_MOVIE_ID"]
        subtitle_id = os.environ["MLH_SUBDL_SMOKE_SUBTITLE_ID"]
        client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {key}"},
            timeout=httpx.Timeout(10),
            follow_redirects=False,
        )
        try:
            adapter = SubDLAdapter(
                client,
                base_url="https://api.subdl.com",
                allowed_download_hosts=("api.subdl.com", "dl.subdl.com"),
                download_max_bytes=10 * 1024 * 1024,
                archive_max_members=100,
                archive_max_uncompressed_bytes=20 * 1024 * 1024,
                archive_max_ratio=100,
            )
            assert await adapter.search(os.environ["MLH_SUBDL_SMOKE_QUERY"], 5)
            assert await adapter.list_for_movie(movie_id, 5)
            payload = await adapter.fetch(subtitle_id)
            assert payload.content
        finally:
            await client.aclose()

    asyncio.run(scenario())
