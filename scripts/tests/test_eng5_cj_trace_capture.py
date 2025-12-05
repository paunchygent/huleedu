from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from common_core.config_enums import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from common_core.error_enums import LLMErrorCode
from common_core.events.llm_provider_events import LLMComparisonResultV1, TokenUsage
from common_core.models.error_models import ErrorDetail

from scripts.llm_traces.eng5_cj_trace_capture import compute_llm_trace_summary


def _make_success_event(
    *,
    winner: EssayComparisonWinner,
    response_time_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
) -> LLMComparisonResultV1:
    now = datetime.utcnow()
    token_usage = TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    return LLMComparisonResultV1(
        request_id="req-success",
        correlation_id=uuid4(),
        winner=winner,
        justification="ok",
        confidence=4.5,
        error_detail=None,
        provider=LLMProviderType.OPENAI,
        model="gpt-5.1",
        response_time_ms=response_time_ms,
        token_usage=token_usage,
        cost_estimate=0.001,
        requested_at=now - timedelta(seconds=1),
        completed_at=now,
        trace_id=None,
        request_metadata={"bos_batch_id": "bos-test"},
    )


def _make_error_event(
    *,
    error_code: LLMErrorCode,
    response_time_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
) -> LLMComparisonResultV1:
    now = datetime.utcnow()
    token_usage = TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    error_detail = ErrorDetail(
        error_code=error_code,
        message="failure",
        correlation_id=uuid4(),
        timestamp=now,
        service="llm_provider_service",
        operation="comparison",
        details={},
    )
    return LLMComparisonResultV1(
        request_id="req-error",
        correlation_id=uuid4(),
        winner=None,
        justification=None,
        confidence=None,
        error_detail=error_detail,
        provider=LLMProviderType.OPENAI,
        model="gpt-5.1",
        response_time_ms=response_time_ms,
        token_usage=token_usage,
        cost_estimate=0.0,
        requested_at=now - timedelta(seconds=1),
        completed_at=now,
        trace_id=None,
        request_metadata={"bos_batch_id": "bos-test"},
    )


def test_compute_llm_trace_summary_basic_counts_and_stats() -> None:
    """Summarizer should aggregate winners, errors, latency, and tokens correctly."""

    callbacks = [
        _make_success_event(
            winner=EssayComparisonWinner.ESSAY_A,
            response_time_ms=100,
            prompt_tokens=50,
            completion_tokens=25,
        ),
        _make_success_event(
            winner=EssayComparisonWinner.ESSAY_A,
            response_time_ms=120,
            prompt_tokens=60,
            completion_tokens=30,
        ),
        _make_success_event(
            winner=EssayComparisonWinner.ESSAY_B,
            response_time_ms=140,
            prompt_tokens=55,
            completion_tokens=35,
        ),
        _make_error_event(
            error_code=LLMErrorCode.PROVIDER_TIMEOUT,
            response_time_ms=200,
            prompt_tokens=40,
            completion_tokens=0,
        ),
        _make_error_event(
            error_code=LLMErrorCode.PROVIDER_RATE_LIMIT,
            response_time_ms=220,
            prompt_tokens=45,
            completion_tokens=0,
        ),
    ]

    summary = compute_llm_trace_summary(callbacks, scenario_id="test_scenario")

    assert summary["scenario_id"] == "test_scenario"
    assert summary["total_events"] == 5
    assert summary["success_count"] == 3
    assert summary["error_count"] == 2

    winners = summary["winner_counts"]
    assert winners[EssayComparisonWinner.ESSAY_A.value] == 2
    assert winners[EssayComparisonWinner.ESSAY_B.value] == 1
    assert winners["error"] == 2

    error_codes = summary["error_code_counts"]
    assert error_codes[str(LLMErrorCode.PROVIDER_TIMEOUT)] == 1
    assert error_codes[str(LLMErrorCode.PROVIDER_RATE_LIMIT)] == 1

    rt_stats = summary["response_time_ms"]
    assert rt_stats["min_ms"] == 100.0
    assert rt_stats["mean_ms"] > 0.0  # sanity check

    token_stats = summary["token_usage"]
    # Sanity check that totals reflect all events
    assert token_stats["total_tokens"]["max"] >= token_stats["total_tokens"]["min"]

    # BT metadata placeholders are not populated by this harness
    assert summary["bt_se_summary"] is None
    assert summary["bt_quality_flags"] is None
