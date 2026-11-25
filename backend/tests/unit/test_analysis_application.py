"""Interval-analysis orchestration and failure taxonomy tests."""

import asyncio
from decimal import Decimal

import pytest

from movie_language_helper.adapters.outbound.fake_analyzer import FakeLanguageAnalyzer
from movie_language_helper.adapters.outbound.memory_session_store import (
    InMemoryTranscriptSessionStore,
)
from movie_language_helper.application.analysis import (
    AnalyzeInterval,
    AnalyzeIntervalRequest,
)
from movie_language_helper.application.errors import ApplicationError
from movie_language_helper.domain.analysis import (
    AnalyzerCandidate,
    AnalyzerMetadata,
    AnalyzerOutput,
    CefrLevel,
    LearnerProfile,
    LearningItemType,
)
from movie_language_helper.domain.extraction import ContextPolicy
from movie_language_helper.domain.time import SyncOffset, TimeRange, Timestamp
from movie_language_helper.ports.analyzer import AnalyzerFailureCode
from tests.factories import cue, session
from tests.fakes import MutableClock


def analyzer_output(*, expression: str = "call it a day") -> AnalyzerOutput:
    return AnalyzerOutput(
        (
            AnalyzerCandidate(
                expression=expression,
                normalized_form=expression,
                type=LearningItemType.IDIOM,
                general_meaning="stop an activity",
                contextual_meaning="stop now",
                cue_ids=("cue-2",),
                estimated_cefr=CefrLevel.B2,
                confidence=Decimal("0.9"),
            ),
        ),
        AnalyzerMetadata("fake", "local", "prompt-v1", "schema-v1", 4, 10, 5),
    )


def request(**changes: object) -> AnalyzeIntervalRequest:
    values: dict[str, object] = {
        "transcript_session_id": "session-test",
        "playback_range": TimeRange(Timestamp(1000), Timestamp(2000)),
        "sync_offset": SyncOffset(),
        "learner": LearnerProfile(CefrLevel.B1),
        "item_limit": 5,
    }
    values.update(changes)
    return AnalyzeIntervalRequest(**values)  # type: ignore[arg-type]


async def configured_use_case(
    analyzer: object,
    *,
    timeout_seconds: float = 1,
) -> tuple[AnalyzeInterval, InMemoryTranscriptSessionStore]:
    clock = MutableClock()
    store = InMemoryTranscriptSessionStore(clock, 2)
    await store.put(
        session(
            cue("cue-1", 0, 1000, "Some earlier context."),
            cue("cue-2", 1000, 2000, "Let's call it a day."),
            cue("cue-3", 2000, 3000, "Later context."),
            created_at=clock.now(),
        )
    )
    return (
        AnalyzeInterval(
            store,
            analyzer,  # type: ignore[arg-type]
            clock,
            max_interval_ms=2000,
            max_abs_offset_ms=500,
            max_item_limit=10,
            context_policy=ContextPolicy(1, 5000),
            timeout_seconds=timeout_seconds,
        ),
        store,
    )


def test_analysis_calls_once_with_bounded_context_and_versions_result() -> None:
    async def scenario() -> None:
        analyzer = FakeLanguageAnalyzer(analyzer_output())
        use_case, _store = await configured_use_case(analyzer)
        result = await use_case.execute(request())
        assert len(analyzer.calls) == 1
        assert [cue.context_only for cue in analyzer.calls[0].cues] == [
            True,
            False,
            True,
        ]
        assert result.id.startswith("analysis-")
        assert result.items[0].expression == "call it a day"
        assert result.items[0].occurrences[0].cue_id == "cue-2"
        assert result.provenance.grounding_version == "grounding-v1"
        assert result.provenance.input_tokens == 10

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        (
            {"playback_range": TimeRange(Timestamp(0), Timestamp(2001))},
            "invalid_range",
        ),
        ({"sync_offset": SyncOffset(501)}, "invalid_sync_offset"),
        ({"item_limit": 0}, "invalid_item_limit"),
        ({"item_limit": 11}, "invalid_item_limit"),
    ],
)
def test_invalid_requests_never_call_analyzer(
    changes: dict[str, object], code: str
) -> None:
    async def scenario() -> None:
        analyzer = FakeLanguageAnalyzer(analyzer_output())
        use_case, _store = await configured_use_case(analyzer)
        with pytest.raises(ApplicationError) as caught:
            await use_case.execute(request(**changes))
        assert caught.value.code == code
        assert analyzer.calls == []

    asyncio.run(scenario())


def test_empty_interval_and_missing_session_never_call_analyzer() -> None:
    async def scenario() -> None:
        analyzer = FakeLanguageAnalyzer(analyzer_output())
        use_case, _store = await configured_use_case(analyzer)
        with pytest.raises(ApplicationError) as empty:
            await use_case.execute(
                request(playback_range=TimeRange(Timestamp(4000), Timestamp(5000)))
            )
        assert empty.value.code == "empty_interval"
        with pytest.raises(ApplicationError) as missing:
            await use_case.execute(request(transcript_session_id="missing"))
        assert missing.value.code == "session_not_found"
        assert analyzer.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("failure", "retryable"),
    [
        (AnalyzerFailureCode.UNAVAILABLE, True),
        (AnalyzerFailureCode.RATE_LIMITED, True),
        (AnalyzerFailureCode.REFUSED, False),
        (AnalyzerFailureCode.INCOMPLETE, False),
        (AnalyzerFailureCode.INVALID_OUTPUT, False),
    ],
)
def test_analyzer_failures_are_safely_mapped(
    failure: AnalyzerFailureCode, retryable: bool
) -> None:
    async def scenario() -> None:
        analyzer = FakeLanguageAnalyzer(failure=failure)
        use_case, _store = await configured_use_case(analyzer)
        with pytest.raises(ApplicationError) as caught:
            await use_case.execute(request())
        assert caught.value.code == failure.value
        assert caught.value.retryable is retryable
        assert "synthetic provider detail" not in caught.value.message

    asyncio.run(scenario())


def test_unexpected_and_invalid_outputs_are_safely_mapped() -> None:
    async def scenario() -> None:
        unexpected = FakeLanguageAnalyzer(unexpected_failure=True)
        use_case, _store = await configured_use_case(unexpected)
        with pytest.raises(ApplicationError) as unavailable:
            await use_case.execute(request())
        assert unavailable.value.code == "analyzer_unavailable"

        invalid = FakeLanguageAnalyzer(analyzer_output(expression="not present"))
        use_case, _store = await configured_use_case(invalid)
        with pytest.raises(ApplicationError) as rejected:
            await use_case.execute(request())
        assert rejected.value.code == "analyzer_invalid_output"

    asyncio.run(scenario())


def test_analyzer_timeout_is_retryable() -> None:
    class SlowAnalyzer:
        async def analyze(self, _analysis_input: object) -> AnalyzerOutput:
            await asyncio.sleep(0.05)
            return analyzer_output()

    async def scenario() -> None:
        use_case, _store = await configured_use_case(
            SlowAnalyzer(), timeout_seconds=0.001
        )
        with pytest.raises(ApplicationError) as caught:
            await use_case.execute(request())
        assert caught.value.code == "analyzer_unavailable"
        assert caught.value.retryable
        assert caught.value.message == "Language analysis timed out."

    asyncio.run(scenario())
