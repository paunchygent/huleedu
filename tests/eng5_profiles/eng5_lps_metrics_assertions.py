"""Shared Prometheus metrics assertions for ENG5 mock profile tests.

These helpers are used by CJ generic, ENG5 anchor, and ENG5 LOWER5 mock
parity tests to validate LPS serial-bundle and queue semantics without
duplicating assertion logic across large test files.
"""

from __future__ import annotations

from typing import Any, Dict

from services.llm_provider_service.config import Settings as LLMProviderSettings
from tests.utils.metrics_helpers import fetch_and_parse_metrics, find_metric_values_in_map


async def assert_lps_serial_bundle_metrics_for_mock_profile(
    validated_services: Dict[str, Any],
) -> None:
    """Assert LPS serial-bundle and queue metrics for the active mock profile.

    This helper is intentionally inequality-based and distribution-focused:
    it only checks for the presence of serial-bundle activity, reasonable
    bundle sizes, and sane queue wait-time behaviour under the ENG5 mock
    profiles used in heavy suites.
    """
    lps_endpoints = validated_services["llm_provider_service"]
    metrics_url = lps_endpoints.get("metrics_url")
    assert metrics_url, "LLM Provider Service metrics URL missing from validated services"

    metrics = await fetch_and_parse_metrics(metrics_url=metrics_url)

    provider_label = "mock"

    # Serial-bundle calls: ensure at least one call for the mock provider/model.
    bundle_samples = [
        (labels, value)
        for labels, value in metrics.get("llm_provider_serial_bundle_calls_total", [])
        if labels.get("provider") == provider_label
    ]
    assert bundle_samples, (
        "Expected llm_provider_serial_bundle_calls_total with provider='mock' "
        "after ENG5 mock profile run"
    )

    model_call_totals: dict[str, float] = {}
    for labels, value in bundle_samples:
        model_label = labels.get("model") or "unknown"
        previous = model_call_totals.get(model_label, 0.0)
        model_call_totals[model_label] = max(previous, float(value))

    profile_model = max(model_call_totals, key=lambda model: model_call_totals[model])
    calls_for_profile = [
        float(value) for labels, value in bundle_samples if labels.get("model") == profile_model
    ]
    assert calls_for_profile and max(calls_for_profile) >= 1.0

    # Histogram: llm_provider_serial_bundle_items_per_call
    items_count_values = find_metric_values_in_map(
        metrics,
        "llm_provider_serial_bundle_items_per_call_count",
        {"provider": provider_label, "model": profile_model},
    )
    assert items_count_values, (
        "Expected llm_provider_serial_bundle_items_per_call_count with "
        f"provider='{provider_label}', model='{profile_model}'"
    )
    total_calls = max(items_count_values)
    assert total_calls >= 1.0

    bucket_samples = [
        (labels, bucket_value)
        for labels, bucket_value in metrics.get(
            "llm_provider_serial_bundle_items_per_call_bucket",
            [],
        )
        if labels.get("provider") == provider_label and labels.get("model") == profile_model
    ]

    bucket_bounds: list[tuple[int, float]] = []
    for labels, bucket_value in bucket_samples:
        le = labels.get("le")
        if le is None or le == "+Inf":
            continue
        try:
            upper = int(le)
        except ValueError:
            continue
        bucket_bounds.append((upper, bucket_value))

    bucket_bounds.sort(key=lambda t: t[0])

    max_items_upper_bound: float | None = None
    for upper, count in bucket_bounds:
        if count >= total_calls:
            max_items_upper_bound = float(upper)
            break

    lps_settings = LLMProviderSettings()
    max_configured = float(lps_settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL)
    if max_items_upper_bound is None:
        max_items_upper_bound = max_configured

    assert max_items_upper_bound >= 1.0
    assert max_items_upper_bound <= max_configured

    # Queue wait-time metrics: ensure serial-bundle waits are recorded and reasonable.
    wait_count_values = find_metric_values_in_map(
        metrics,
        "llm_provider_queue_wait_time_seconds_count",
        {"queue_processing_mode": "serial_bundle"},
    )
    wait_sum_values = find_metric_values_in_map(
        metrics,
        "llm_provider_queue_wait_time_seconds_sum",
        {"queue_processing_mode": "serial_bundle"},
    )
    assert wait_count_values and wait_sum_values, (
        "Expected llm_provider_queue_wait_time_seconds_* metrics for "
        "queue_processing_mode='serial_bundle'"
    )

    total_wait_count = sum(wait_count_values)
    total_wait_sum = sum(wait_sum_values)
    assert total_wait_count > 0.0
    average_wait = total_wait_sum / total_wait_count
    assert average_wait >= 0.0
    # Guardrail only: typical waits should stay within a broad but bounded
    # range in heavy ENG5 runs. Allow up to 120 seconds to absorb
    # infrastructure jitter while still catching clearly broken behaviour.
    assert average_wait <= 120.0

    # Ensure at least one result label is present for serial-bundle queue waits.
    wait_count_samples = [
        labels
        for labels, _value in metrics.get("llm_provider_queue_wait_time_seconds_count", [])
        if labels.get("queue_processing_mode") == "serial_bundle"
    ]
    results_seen = {
        labels.get("result") for labels in wait_count_samples if labels.get("result") is not None
    }
    assert results_seen, (
        "Expected queue wait-time samples for at least one result under serial_bundle mode"
    )
    assert results_seen <= {"success", "failure", "expired"}

    # Comparison callbacks sanity: callbacks should be recorded for serial-bundle paths.
    callback_values = find_metric_values_in_map(
        metrics,
        "llm_provider_comparison_callbacks_total",
        {"queue_processing_mode": "serial_bundle"},
    )
    assert callback_values, (
        "Expected llm_provider_comparison_callbacks_total for queue_processing_mode='serial_bundle'"
    )
    assert max(callback_values) >= 1.0

    # Queue depth guardrail: avoid runaway queue growth during parity runs.
    depth_values_total = find_metric_values_in_map(
        metrics,
        "llm_provider_queue_depth",
        {"queue_type": "total"},
    )
    if depth_values_total:
        # Default QUEUE_MAX_SIZE is 1000; keep total depth comfortably below this.
        assert max(depth_values_total) <= 1000.0
