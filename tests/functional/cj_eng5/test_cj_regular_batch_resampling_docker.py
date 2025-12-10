"""Design skeleton for a regular-batch CJ RESAMPLING docker test.

This module intentionally sketches (but does not yet execute) a docker-backed
scenario for a larger CJ batch (e.g. 20+ essays) that reuses the existing
LOWER5 small-net continuation harness helpers. The goal is to exercise future
generalised RESAMPLING semantics for non-small-net batches once
`MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` and related orchestration paths are
implemented.

Current status (2025-12-06):
- The ENG5 LOWER5 small-net docker harness in
  `test_cj_small_net_continuation_docker.py` has been validated and pins
  PR-2/PR-7 small-net semantics, including coverage metadata and
  `MAX_RESAMPLING_PASSES_FOR_SMALL_NET` behaviour.
- Generalised RESAMPLING semantics for non-small nets have been wired into
  `workflow_decision` / `workflow_continuation` behind
  `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH`, but this docker test remains
  skipped while the new path is being exercised via unit tests and tuned
  against ENG5/CJ traces.
"""

from __future__ import annotations

from typing import Any

import pytest
from common_core.domain_enums import CourseCode
from common_core.status_enums import CJBatchStateEnum
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from services.cj_assessment_service.config import Settings as CJSettings
from services.cj_assessment_service.tests.helpers.positional_fairness import (
    get_pair_orientation_counts_for_batch,
    get_positional_counts_for_batch,
)
from tests.functional.cj_eng5.test_cj_small_net_continuation_docker import (
    _ensure_sufficient_credits,
    _get_lps_mock_mode,
    _request_cj_pipeline_execution,
    _wait_for_batch_ready_via_kafka,
    _wait_for_cj_batch_final_state,
)
from tests.utils.auth_manager import AuthTestUser
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.metrics_helpers import fetch_and_parse_metrics, find_metric_values_in_map
from tests.utils.service_test_manager import ServiceTestManager


class TestCJRegularBatchResamplingDocker:
    """Design-only skeleton for a regular-batch CJ RESAMPLING docker test.

    Notes:
    - This test is marked as a design sketch and unconditionally skipped so
      that it does not yet participate in CI while RESAMPLING semantics for
      regular nets are still under active design.
    - Once `MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH` and the generalised
      RESAMPLING branch are implemented in `workflow_continuation`, this
      skeleton should be completed and the early `pytest.skip` removed.
    """

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Service validation manager."""
        return ServiceTestManager()

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> dict:
        """Ensure core services required for CJ continuation are running."""
        endpoints = await service_manager.get_validated_endpoints()

        required = {"api_gateway_service", "cj_assessment_service", "llm_provider_service"}
        missing = required - set(endpoints.keys())
        if missing:
            pytest.skip(
                f"Required services not available for integration testing: {sorted(missing)}"
            )

        return endpoints

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.mock_profile("cj_generic_batch")
    @pytest.mark.asyncio
    async def test_cj_regular_batch_resampling_metadata_completed_successful(
        self,
        service_manager: ServiceTestManager,
        validated_services: dict[str, Any],
    ) -> None:
        """Validate regular-batch CJ RESAMPLING completes with PR-2/PR-7 invariants.

        This test drives a larger CJ batch (24 essays) via API Gateway under the
        cj_generic_batch mock profile, validating:
        - ContinuationContext.is_small_net is False (expected_essay_count > MIN_RESAMPLING_NET_SIZE)
        - RESAMPLING respects MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH cap
        - PR-2/PR-7 completion invariants (callbacks, budget, no failures)
        - Positional fairness: per-essay skew stays within acceptable bounds

        Run with: pdm run llm-mock-profile cj-generic
        """
        # Tightened threshold after validating positional fairness implementation.
        # Regular batch (24 essays) achieves ~0.17 max skew with participation cap.
        # Threshold of 0.2 allows ±2 positions variance (14/10 vs ideal 12/12).
        MAX_ALLOWED_SKEW = 0.2

        test_user: AuthTestUser = service_manager.create_test_user()
        kafka_manager = KafkaTestManager()

        # Gate on LPS /admin/mock-mode for cj_generic_batch profile.
        mode_info = await _get_lps_mock_mode(validated_services)

        if not mode_info.get("use_mock_llm", False):
            pytest.skip(
                "LPS reports USE_MOCK_LLM = false; enable mock mode before running this test"
            )

        if mode_info.get("mock_mode") != "cj_generic_batch":
            pytest.skip(
                "LPS mock_mode is not 'cj_generic_batch'; restart "
                "llm_provider_service with this profile before running "
                "regular-batch RESAMPLING tests."
            )

        settings = CJSettings()

        expected_essay_count = 24
        assert expected_essay_count > settings.MIN_RESAMPLING_NET_SIZE

        bos_batch_id, correlation_id = await service_manager.create_batch_via_agw(
            expected_essay_count=expected_essay_count,
            course_code=CourseCode.ENG5,
            user=test_user,
        )

        files = [
            {
                "name": f"eng5-regular-batch-essay-{i + 1}.txt",
                "content": (
                    f"ENG5 regular-batch essay content for student {i + 1}. "
                    "Text kept simple for docker tests."
                ),
            }
            for i in range(expected_essay_count)
        ]
        await service_manager.upload_files(
            batch_id=bos_batch_id,
            files=files,
            user=test_user,
            correlation_id=correlation_id,
        )

        # 3. Wait for BOS/ELS content provisioning to complete.
        await _wait_for_batch_ready_via_kafka(
            kafka_manager,
            bos_batch_id=bos_batch_id,
            correlation_id=correlation_id,
        )

        # 4. Ensure entitlements allow CJ execution for this user/org.
        # 24-essay batch needs C(24,2)=276 pairs minimum + resampling overhead.
        await _ensure_sufficient_credits(service_manager, user=test_user, required_credits=500)

        # 5. Request CJ pipeline execution for this batch.
        try:
            await _request_cj_pipeline_execution(
                service_manager,
                bos_batch_id=bos_batch_id,
                correlation_id=correlation_id,
                user=test_user,
            )
        except RuntimeError as exc:
            msg = str(exc)
            if "402" in msg and "insufficient_credits" in msg:
                pytest.skip(
                    "CJ pipeline request denied due to insufficient credits; "
                    "adjust entitlements or credit config before running this test"
                )
            raise

        # 6. Poll CJ until the batch reaches a final state.
        # Regular batches with 24 essays may take longer than LOWER5.
        batch_state = await _wait_for_cj_batch_final_state(
            bos_batch_id=bos_batch_id,
            expected_essay_count=expected_essay_count,
            timeout_seconds=600.0,  # 10 minutes for larger batch.
        )

        # 7. Assert final state is COMPLETED.
        assert batch_state.state == CJBatchStateEnum.COMPLETED, (
            f"Expected COMPLETED, got {batch_state.state}"
        )

        # 8. Completion invariants and callback accounting (PR-2/PR-7).
        total_comparisons = batch_state.total_comparisons
        submitted = batch_state.submitted_comparisons
        completed = batch_state.completed_comparisons
        failed = batch_state.failed_comparisons
        callbacks_received = completed + failed

        assert failed == 0, f"Expected no failures under mock profile, got {failed}"
        assert callbacks_received > 0
        denominator = batch_state.completion_denominator()
        assert denominator > 0
        assert callbacks_received <= denominator

        assert total_comparisons == submitted == completed

        if batch_state.total_budget is not None:
            assert total_comparisons <= batch_state.total_budget

        # 9. Regular-batch RESAMPLING metadata assertions.
        processing = batch_state.processing_metadata or {}
        resampling_pass_count = int(processing.get("resampling_pass_count", 0))
        max_regular_passes = settings.MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH

        # Verify resampling cap respected for regular batches.
        assert 0 <= resampling_pass_count <= max_regular_passes, (
            f"Resampling pass count {resampling_pass_count} exceeds "
            f"regular-batch cap {max_regular_passes}"
        )

        # Coverage metadata presence.
        max_possible_pairs = processing.get("max_possible_pairs")
        successful_pairs_count = processing.get("successful_pairs_count")

        assert isinstance(max_possible_pairs, int), "max_possible_pairs should be int"
        assert isinstance(successful_pairs_count, int), "successful_pairs_count should be int"

        # For 24 essays, max_possible_pairs = 24*23/2 = 276.
        expected_max_pairs = (expected_essay_count * (expected_essay_count - 1)) // 2
        assert max_possible_pairs == expected_max_pairs

        # 10. Positional fairness analysis.
        engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        try:
            async with session_factory() as session:
                positional_counts = await get_positional_counts_for_batch(
                    session=session,
                    cj_batch_id=batch_state.batch_id,
                )
                await get_pair_orientation_counts_for_batch(
                    session=session,
                    cj_batch_id=batch_state.batch_id,
                )

            # --- Per-essay skew analysis ---
            skew_violations: list[tuple[str, float]] = []
            max_observed_skew = 0.0

            for essay_id, counts in positional_counts.items():
                a_count = counts["A"]
                b_count = counts["B"]
                total = a_count + b_count

                if total == 0:
                    continue

                skew = abs(a_count - b_count) / total
                max_observed_skew = max(max_observed_skew, skew)
                if skew > MAX_ALLOWED_SKEW:
                    skew_violations.append((essay_id, skew))

            assert not skew_violations, (
                "Positional fairness skew exceeded threshold for essays: "
                f"{skew_violations} (max_observed_skew={max_observed_skew}, "
                f"MAX_ALLOWED_SKEW={MAX_ALLOWED_SKEW})"
            )

        finally:
            await engine.dispose()

        # 11. CJ ↔ LPS serial-bundle metrics assertions.

        cj_endpoints = validated_services.get("cj_assessment_service", {})
        lps_endpoints = validated_services.get("llm_provider_service", {})

        cj_metrics_url = cj_endpoints.get("metrics_url")
        lps_metrics_url = lps_endpoints.get("metrics_url")

        assert cj_metrics_url, "CJ Assessment metrics URL missing from validated services"
        assert lps_metrics_url, "LLM Provider Service metrics URL missing from validated services"

        cj_metrics = await fetch_and_parse_metrics(metrics_url=cj_metrics_url)
        lps_metrics = await fetch_and_parse_metrics(metrics_url=lps_metrics_url)

        # CJ metrics: ensure serial-bundle requests and batches were recorded.
        serial_bundle_labels = {"batching_mode": "serial_bundle"}

        cj_requests_values = find_metric_values_in_map(
            cj_metrics,
            "cj_llm_requests_total",
            serial_bundle_labels,
        )
        cj_batches_values = find_metric_values_in_map(
            cj_metrics,
            "cj_llm_batches_started_total",
            serial_bundle_labels,
        )

        assert cj_requests_values, (
            "Expected cj_llm_requests_total{batching_mode='serial_bundle'} "
            "to be present after regular-batch RESAMPLING run"
        )
        assert max(cj_requests_values) >= 1

        assert cj_batches_values, (
            "Expected cj_llm_batches_started_total{batching_mode='serial_bundle'} "
            "to be present after regular-batch RESAMPLING run"
        )
        assert max(cj_batches_values) >= 1

        # LPS metrics: verify serial-bundle calls and bundle size distribution.
        expected_model = settings.DEFAULT_LLM_MODEL
        expected_provider = str(mode_info.get("default_provider") or "mock")

        lps_calls_values = find_metric_values_in_map(
            lps_metrics,
            "llm_provider_serial_bundle_calls_total",
            {"provider": expected_provider, "model": expected_model},
        )
        assert lps_calls_values, (
            "Expected llm_provider_serial_bundle_calls_total with provider/model labels "
            f"provider='{expected_provider}', model='{expected_model}'"
        )
        assert max(lps_calls_values) >= 1

        items_count_values = find_metric_values_in_map(
            lps_metrics,
            "llm_provider_serial_bundle_items_per_call_count",
            {"provider": expected_provider, "model": expected_model},
        )
        assert items_count_values, (
            "Expected llm_provider_serial_bundle_items_per_call_count with "
            f"provider='{expected_provider}', model='{expected_model}'"
        )
        total_calls = max(items_count_values)
        assert total_calls >= 1

        bucket_samples = [
            (labels, bucket_value)
            for labels, bucket_value in lps_metrics.get(
                "llm_provider_serial_bundle_items_per_call_bucket", []
            )
            if labels.get("provider") == expected_provider and labels.get("model") == expected_model
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

        from services.llm_provider_service.config import Settings as LLMProviderSettings

        lps_settings = LLMProviderSettings()
        max_configured = float(lps_settings.SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL)

        if max_items_upper_bound is None:
            max_items_upper_bound = max_configured

        assert max_items_upper_bound >= 1
        assert max_items_upper_bound <= max_configured

        # LPS queue wait-time and callbacks guardrails for serial_bundle.
        wait_count_values = find_metric_values_in_map(
            lps_metrics,
            "llm_provider_queue_wait_time_seconds_count",
            {"queue_processing_mode": "serial_bundle"},
        )
        wait_sum_values = find_metric_values_in_map(
            lps_metrics,
            "llm_provider_queue_wait_time_seconds_sum",
            {"queue_processing_mode": "serial_bundle"},
        )
        assert wait_count_values and wait_sum_values, (
            "Expected llm_provider_queue_wait_time_seconds_* metrics for "
            "queue_processing_mode='serial_bundle'"
        )

        total_wait_count = sum(wait_count_values)
        total_wait_sum = sum(wait_sum_values)
        assert total_wait_count > 0.0, (
            "Expected at least one serial_bundle queue wait sample; "
            f"total_wait_count={total_wait_count}, "
            f"wait_count_values={wait_count_values}"
        )
        average_wait = total_wait_sum / total_wait_count
        assert average_wait >= 0.0, (
            "Expected non-negative average queue wait; "
            f"average_wait={average_wait}, "
            f"total_wait_sum={total_wait_sum}, "
            f"total_wait_count={total_wait_count}"
        )
        assert average_wait <= 120.0, (
            "Expected average serial_bundle queue wait <= 120s; "
            f"average_wait={average_wait}, "
            f"total_wait_sum={total_wait_sum}, "
            f"total_wait_count={total_wait_count}"
        )

        wait_count_samples = [
            labels
            for labels, _value in lps_metrics.get("llm_provider_queue_wait_time_seconds_count", [])
            if labels.get("queue_processing_mode") == "serial_bundle"
        ]
        results_seen = {
            labels.get("result")
            for labels in wait_count_samples
            if labels.get("result") is not None
        }
        assert results_seen, (
            "Expected queue wait-time samples for at least one result under serial_bundle mode; "
            f"observed_results={results_seen}"
        )
        assert results_seen <= {"success", "failure", "expired"}, (
            "Unexpected result labels in serial_bundle queue wait metrics; "
            f"observed_results={results_seen}"
        )

        callback_values = find_metric_values_in_map(
            lps_metrics,
            "llm_provider_comparison_callbacks_total",
            {"queue_processing_mode": "serial_bundle"},
        )
        assert callback_values, (
            "Expected llm_provider_comparison_callbacks_total for "
            "queue_processing_mode='serial_bundle'; "
            f"callback_values={callback_values}"
        )
        assert max(callback_values) >= 1.0, (
            "Expected at least one comparison callback recorded for serial_bundle; "
            f"max_callback_value={max(callback_values)}, "
            f"callback_values={callback_values}"
        )

        depth_values_total = find_metric_values_in_map(
            lps_metrics,
            "llm_provider_queue_depth",
            {"queue_type": "total"},
        )
        if depth_values_total:
            assert max(depth_values_total) <= 1000.0, (
                "Queue depth guardrail breached for serial_bundle; "
                f"max_depth_total={max(depth_values_total)}, "
                f"depth_values_total={depth_values_total}"
            )
