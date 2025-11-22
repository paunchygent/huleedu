from __future__ import annotations

from pathlib import Path

import pytest

from scripts.prompt_cache_benchmark.fixtures import BenchmarkFixture
from scripts.prompt_cache_benchmark.limiter import DualBucketRateLimiter
from scripts.prompt_cache_benchmark.loader import load_fixture_from_json
from scripts.prompt_cache_benchmark.runner import (
    BenchmarkRequest,
    BenchmarkRunner,
    LLMCallResult,
    LLMClientProtocol,
)
from services.cj_assessment_service.models_api import EssayForComparison


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeLLMClient(LLMClientProtocol):
    def __init__(self) -> None:
        self.calls = 0

    async def send(self, *, request: BenchmarkRequest) -> LLMCallResult:  # type: ignore[override]
        self.calls += 1
        if self.calls == 1:
            return LLMCallResult(
                request=request,
                status="success",
                latency_ms=5.0,
                cache_read_tokens=0,
                cache_write_tokens=1200,
                total_prompt_tokens=1300,
                prompt_hash="seed",
            )

        return LLMCallResult(
            request=request,
            status="success",
            latency_ms=4.0,
            cache_read_tokens=1000,
            cache_write_tokens=0,
            total_prompt_tokens=1100,
            prompt_hash="hit",
        )


def _mini_fixture() -> BenchmarkFixture:
    anchors = [EssayForComparison(id="anchor-1", text_content="anchor text")]
    essays = [
        EssayForComparison(id="essay-1", text_content="essay one"),
        EssayForComparison(id="essay-2", text_content="essay two"),
    ]
    return BenchmarkFixture(
        name="mini",
        assignment_id="mini-assignment",
        assessment_context={
            "student_prompt_text": "prompt",
            "assessment_instructions": "instructions",
            "judge_rubric_text": "rubric",
        },
        anchors=anchors,
        essays=essays,
    )


@pytest.mark.asyncio
async def test_dual_bucket_rate_limiter_respects_request_budget() -> None:
    clock = FakeClock()
    limiter = DualBucketRateLimiter(
        requests_per_minute=2,
        tokens_per_minute=0,
        time_fn=clock.time,
        sleep_func=clock.sleep,
    )

    await limiter.acquire()
    await limiter.acquire()
    assert clock.now == 0.0

    await limiter.acquire()
    assert clock.now >= 30.0  # third request waits for refill


@pytest.mark.asyncio
async def test_runner_counts_hits_and_misses() -> None:
    fixture = _mini_fixture()
    client = FakeLLMClient()
    runner = BenchmarkRunner(
        fixture=fixture,
        llm_client=client,
        jitter_range_ms=(0, 0),
        concurrency=1,
    )

    result = await runner.run(prom_client=None, session=None)

    assert result.seeds == 1
    assert result.hits == 1
    assert result.misses == 1
    assert result.post_seed_miss_rate == 0.0
    assert result.tokens_read == 1000
    assert result.tokens_written == 1200
    assert client.calls == 2


def test_load_fixture_from_json(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        """
{
  "name": "custom",
  "assignment_id": "assign-1",
  "assessment_context": {
    "student_prompt_text": "prompt",
    "assessment_instructions": "assess",
    "judge_rubric_text": "rubric"
  },
  "anchors": [{"id": "a1", "text": "anchor text"}],
  "students": [{"id": "s1", "text": "student text"}]
}
""",
        encoding="utf-8",
    )

    fixture = load_fixture_from_json(fixture_path)

    assert fixture.assignment_id == "assign-1"
    assert fixture.assessment_context["student_prompt_text"] == "prompt"
    assert fixture.anchors[0].id == "a1"
    assert fixture.essays[0].id == "s1"
