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
from tests.integration.test_cj_small_net_continuation_docker import (
    _ensure_sufficient_credits,
    _get_lps_mock_mode,
    _request_cj_pipeline_execution,
    _wait_for_batch_ready_via_kafka,
    _wait_for_cj_batch_final_state,
)
from tests.utils.auth_manager import AuthTestUser
from tests.utils.kafka_test_manager import KafkaTestManager
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
                "regular-batch CJ RESAMPLING tests."
            )

        expected_essay_count = 24  # Regular batch size (> MIN_RESAMPLING_NET_SIZE).
        settings = CJSettings()

        # Verify this qualifies as a regular batch.
        assert expected_essay_count > settings.MIN_RESAMPLING_NET_SIZE, (
            f"Expected regular batch (>{settings.MIN_RESAMPLING_NET_SIZE} essays), "
            f"got {expected_essay_count}"
        )

        # 1. Create a regular ENG5 batch via AGW with expected_essay_count=24.
        bos_batch_id, correlation_id = await service_manager.create_batch_via_agw(
            expected_essay_count=expected_essay_count,
            course_code=CourseCode.ENG5,
            user=test_user,
        )

        # 2. Upload 24 ENG5-shaped essays via AGW/File Service.
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
                pair_orientation_counts = await get_pair_orientation_counts_for_batch(
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

            # --- Per-pair complement analysis ---
            # For pairs seen more than once, validate AB/BA complement enforcement.
            pairs_missing_complement: list[tuple[tuple[str, str], int, int]] = []
            resampled_pair_count = 0

            for pair_key, (ab_count, ba_count) in pair_orientation_counts.items():
                total_for_pair = ab_count + ba_count
                if total_for_pair > 1:
                    # This pair was resampled; expect both AB and BA.
                    resampled_pair_count += 1
                    if ab_count == 0 or ba_count == 0:
                        pairs_missing_complement.append((pair_key, ab_count, ba_count))

            # Diagnostic output for threshold calibration.
            # Per-essay breakdown for investigation
            per_essay_details = []
            for essay_id, counts in sorted(positional_counts.items()):
                a_count = counts["A"]
                b_count = counts["B"]
                total = a_count + b_count
                skew = abs(a_count - b_count) / total if total > 0 else 0.0
                per_essay_details.append(
                    f"{essay_id[-8:]}: A={a_count}, B={b_count}, total={total}, skew={skew:.3f}"
                )

            print("Per-essay positional breakdown:")
            for detail in per_essay_details:
                print(f"  {detail}")

            print(
                "Regular-batch positional fairness diagnostics:",
                {
                    "essay_count": len(positional_counts),
                    "total_comparisons": total_comparisons,
                    "resampling_pass_count": resampling_pass_count,
                    "max_observed_skew": round(max_observed_skew, 3),
                    "pair_count": len(pair_orientation_counts),
                    "resampled_pair_count": resampled_pair_count,
                    "pairs_missing_complement": len(pairs_missing_complement),
                },
            )

            # Assert no per-essay skew violations.
            assert len(skew_violations) == 0, (
                f"Positional skew exceeded MAX_ALLOWED_SKEW={MAX_ALLOWED_SKEW} "
                f"for essays: {skew_violations}"
            )

            # For regular batches, not all essays may appear in both positions
            # due to limited comparisons per essay. Check essays that participated.
            essays_in_both_positions = 0
            for essay_id, counts in positional_counts.items():
                if counts["A"] > 0 and counts["B"] > 0:
                    essays_in_both_positions += 1

            # At least half of essays should appear in both positions for fair distribution.
            min_expected_both = expected_essay_count // 2
            assert essays_in_both_positions >= min_expected_both, (
                f"Only {essays_in_both_positions}/{expected_essay_count} essays appeared "
                f"in both A and B positions (expected at least {min_expected_both})"
            )

            # Assert per-pair complement enforcement for resampled pairs.
            assert len(pairs_missing_complement) == 0, (
                f"Resampled pairs missing AB/BA complement: {pairs_missing_complement}"
            )

        finally:
            await engine.dispose()
