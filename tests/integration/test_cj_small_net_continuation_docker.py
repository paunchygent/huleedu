"""Docker-backed CJ small-net continuation tests for ENG5 LOWER5.

These tests validate that a LOWER5-shaped ENG5 batch (5 essays) reaches a
completed-successful state under the ``eng5_lower5_gpt51_low`` mock profile
and that CJBatchState/processing_metadata reflect small-net coverage and
continuation semantics consistent with PR-2 / PR-7.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import aiohttp
import pytest
from common_core.domain_enums import CourseCode
from common_core.pipeline_models import PhaseName
from common_core.status_enums import CJBatchStateEnum
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from services.cj_assessment_service.cj_core_logic.workflow_context import build_small_net_context
from services.cj_assessment_service.config import Settings as CJSettings
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload
from tests.utils.auth_manager import AuthTestUser
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


async def _get_lps_mock_mode(validated_services: dict) -> dict[str, Any]:
    """Query LPS /admin/mock-mode to determine active mock configuration."""
    if "llm_provider_service" not in validated_services:
        pytest.skip("llm_provider_service not available for integration testing")

    base_url = validated_services["llm_provider_service"]["base_url"]
    admin_url = f"{base_url}/admin/mock-mode"

    async with aiohttp.ClientSession() as session:
        async with session.get(
            admin_url,
            timeout=aiohttp.ClientTimeout(total=5.0),
        ) as resp:
            if resp.status != 200:
                pytest.skip(
                    "/admin/mock-mode not available on LPS; ensure dev config exposes this endpoint"
                )
            data = await resp.json()
            return cast(dict[str, Any], data)


def _expected_max_pairs(essay_count: int) -> int:
    """Compute n-choose-2 pairs for a net size."""
    if essay_count <= 1:
        return 0
    return (essay_count * (essay_count - 1)) // 2


async def _request_cj_pipeline_execution(
    service_manager: ServiceTestManager,
    *,
    bos_batch_id: str,
    correlation_id: str,
    user: AuthTestUser | None = None,
) -> None:
    """Request CJ pipeline execution for a batch via API Gateway.

    This mirrors the production client pattern:
    POST /v1/batches/{batch_id}/pipelines with requested_pipeline=cj_assessment.
    """
    request_body = {
        "batch_id": bos_batch_id,
        "requested_pipeline": PhaseName.CJ_ASSESSMENT.value,
        "is_retry": False,
    }

    # Use ServiceTestManager to handle auth + correlation ID headers.
    await service_manager.make_request(
        method="POST",
        service="api_gateway_service",
        path=f"/v1/batches/{bos_batch_id}/pipelines",
        json=request_body,
        user=user,
        correlation_id=correlation_id,
    )


async def _ensure_sufficient_credits(
    service_manager: ServiceTestManager,
    *,
    user: AuthTestUser,
    required_credits: int = 20,
) -> None:
    """Ensure the test user or org has enough credits for CJ pipeline.

    Uses the Entitlements admin endpoint; skips the test if the endpoint
    is not available or credit system is not operational.
    """
    subject_type: str
    subject_id: str

    if user.organization_id:
        subject_type = "org"
        subject_id = user.organization_id
    else:
        subject_type = "user"
        subject_id = user.user_id

    try:
        await service_manager.make_request(
            method="POST",
            service="entitlements_service",
            path="/v1/admin/credits/set",
            json={
                "subject_type": subject_type,
                "subject_id": subject_id,
                "balance": required_credits,
            },
        )
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"Credit admin endpoint not available or entitlements not operational: {exc}")


async def _wait_for_batch_ready_via_kafka(
    kafka_manager: KafkaTestManager,
    *,
    bos_batch_id: str,
    correlation_id: str,
    timeout_seconds: float = 60.0,
) -> None:
    """Wait for BatchContentProvisioningCompleted event indicating batch readiness.

    This aligns with existing functional credit tests to ensure BOS has
    transitioned the batch to READY_FOR_PIPELINE_EXECUTION before requesting CJ.
    """
    callback_topic = "huleedu.batch.content.provisioning.completed.v1"

    async with kafka_manager.consumer(
        "cj_small_net_continuation_ready",
        topics=[callback_topic],
        auto_offset_reset="earliest",
    ) as consumer:
        try:
            async with asyncio.timeout(timeout_seconds):
                async for message in consumer:
                    raw = (
                        message.value.decode("utf-8")
                        if isinstance(message.value, bytes)
                        else message.value
                    )
                    import json

                    envelope = json.loads(raw)
                    if (
                        envelope.get("correlation_id") == correlation_id
                        and envelope.get("data", {}).get("batch_id") == bos_batch_id
                    ):
                        return
        except TimeoutError:
            pytest.fail(
                "Timeout waiting for BatchContentProvisioningCompleted event for "
                f"batch {bos_batch_id} (correlation_id={correlation_id})"
            )


async def _wait_for_cj_batch_final_state(
    bos_batch_id: str,
    *,
    expected_essay_count: int,
    timeout_seconds: float = 60.0,
    poll_interval_seconds: float = 2.0,
) -> CJBatchState:
    """Poll CJ database until the batch for bos_batch_id reaches a final state.

    This helper is intentionally net-size agnostic and can be reused for
    regular (non-small-net) batches by varying expected_essay_count.
    """
    settings = CJSettings()
    engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    deadline = asyncio.get_event_loop().time() + timeout_seconds
    last_state: CJBatchState | None = None

    try:
        while True:
            async with session_factory() as session:
                result = await session.execute(
                    select(CJBatchState)
                    .join(CJBatchUpload, CJBatchState.batch_id == CJBatchUpload.id)
                    .where(CJBatchUpload.bos_batch_id == bos_batch_id)
                )
                state = result.scalars().first()
                last_state = state

                if state is not None:
                    upload = state.batch_upload
                    if upload is not None:
                        assert upload.expected_essay_count == expected_essay_count, (
                            f"Expected {expected_essay_count} essays, "
                            f"got {upload.expected_essay_count}"
                        )

                    callbacks_received = (state.completed_comparisons or 0) + (
                        state.failed_comparisons or 0
                    )

                    if (
                        state.state
                        in {
                            CJBatchStateEnum.COMPLETED,
                            CJBatchStateEnum.FAILED,
                            CJBatchStateEnum.CANCELLED,
                        }
                        and callbacks_received > 0
                    ):
                        return state

            if asyncio.get_event_loop().time() >= deadline:
                if last_state is None:
                    raise AssertionError(
                        f"Timed out waiting for CJ batch for BOS batch {bos_batch_id}: "
                        "no CJBatchState row found"
                    )

                raise AssertionError(
                    "Timed out waiting for CJ batch for BOS batch "
                    f"{bos_batch_id}: "
                    f"state={last_state.state}, "
                    f"submitted={last_state.submitted_comparisons}, "
                    f"completed={last_state.completed_comparisons}, "
                    f"failed={last_state.failed_comparisons}"
                )

            await asyncio.sleep(poll_interval_seconds)
    finally:
        await engine.dispose()


class TestCJSmallNetContinuation:
    """Docker-backed CJ small-net continuation tests for ENG5 LOWER5."""

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
    @pytest.mark.asyncio
    async def test_cj_small_net_continuation_metadata_completed_successful(
        self,
        service_manager: ServiceTestManager,
        validated_services: dict,
    ) -> None:
        """
        Validate that an ENG5 LOWER5 small-net batch reaches COMPLETED state
        and that CJBatchState/processing_metadata reflect full small-net
        coverage and continuation semantics.
        """
        # Use an explicit test user so we can provision credits deterministically.
        test_user = service_manager.create_test_user()
        kafka_manager = KafkaTestManager()

        mode_info = await _get_lps_mock_mode(validated_services)

        if not mode_info.get("use_mock_llm", False):
            pytest.skip(
                "LPS reports USE_MOCK_LLM = false; enable mock mode before running this test"
            )

        if mode_info.get("mock_mode") != "eng5_lower5_gpt51_low":
            pytest.skip(
                "LPS mock_mode is not 'eng5_lower5_gpt51_low'; restart "
                "llm_provider_service with this profile before running "
                "ENG5 LOWER5 CJ continuation tests."
            )

        expected_essay_count = 5

        # 1. Create ENG5 batch via API Gateway with expected_essay_count=5
        bos_batch_id, correlation_id = await service_manager.create_batch_via_agw(
            expected_essay_count=expected_essay_count,
            course_code=CourseCode.ENG5,
            user=test_user,
        )

        # 2. Upload five ENG5 LOWER5-shaped essays via AGW/File Service
        files = [
            {
                "name": f"eng5-lower5-essay-{i + 1}.txt",
                "content": (
                    f"ENG5 LOWER5 essay content for student {i + 1}. "
                    "This text is intentionally simple for docker tests."
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

        # 3. Wait for BOS/ELS content provisioning to complete so the batch
        #    reaches READY_FOR_PIPELINE_EXECUTION before requesting CJ.
        await _wait_for_batch_ready_via_kafka(
            kafka_manager,
            bos_batch_id=bos_batch_id,
            correlation_id=correlation_id,
        )

        # 4. Ensure entitlements allow CJ execution for this user/org.
        await _ensure_sufficient_credits(service_manager, user=test_user)

        # 5. Request CJ pipeline execution for this batch so CJ assessment runs.
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
        # CJ continuation and finalization can take several iterations in the
        # docker ENG5 LOWER5 profile, so allow a generous timeout here.
        batch_state = await _wait_for_cj_batch_final_state(
            bos_batch_id=bos_batch_id,
            expected_essay_count=expected_essay_count,
            timeout_seconds=360.0,
        )

        # Final state should be COMPLETED, not FAILED/CANCELLED.
        assert batch_state.state == CJBatchStateEnum.COMPLETED, (
            f"Expected COMPLETED, got {batch_state.state}"
        )

        # Completion invariants and callback accounting (PR-2/PR-7).
        total_comparisons = batch_state.total_comparisons
        submitted = batch_state.submitted_comparisons
        completed = batch_state.completed_comparisons
        failed = batch_state.failed_comparisons
        callbacks_received = completed + failed

        assert failed == 0
        assert callbacks_received > 0
        denominator = batch_state.completion_denominator()
        assert denominator > 0
        # completion_denominator now reflects total_budget semantics; for ENG5
        # LOWER5 we only require that callbacks stay within the allowed budget.
        assert callbacks_received <= denominator

        assert total_comparisons == submitted == completed
        if batch_state.total_budget is not None:
            assert total_comparisons <= batch_state.total_budget

        # 4. Coverage and small-net metadata on CJBatchState.processing_metadata
        processing = batch_state.processing_metadata or {}

        max_possible_pairs = processing.get("max_possible_pairs")
        successful_pairs_count = processing.get("successful_pairs_count")
        unique_coverage_complete = processing.get("unique_coverage_complete")
        resampling_pass_count = processing.get("resampling_pass_count", 0)

        expected_max_pairs = _expected_max_pairs(expected_essay_count)

        assert isinstance(max_possible_pairs, int)
        assert isinstance(successful_pairs_count, int)
        assert isinstance(unique_coverage_complete, bool)
        assert isinstance(resampling_pass_count, int)

        assert max_possible_pairs == expected_max_pairs
        assert successful_pairs_count == expected_max_pairs
        assert unique_coverage_complete is True
        assert resampling_pass_count >= 0

        # 5. BT metadata presence and shape
        bt_se_summary = processing.get("bt_se_summary")
        bt_quality_flags = processing.get("bt_quality_flags")

        assert isinstance(bt_se_summary, dict), "bt_se_summary should be a dict"
        for key in ("mean_se", "max_se", "mean_comparisons_per_item", "isolated_items"):
            assert key in bt_se_summary, f"bt_se_summary missing key '{key}'"

        assert isinstance(bt_quality_flags, dict), "bt_quality_flags should be a dict"
        expected_flag_keys = {
            "bt_se_inflated",
            "comparison_coverage_sparse",
            "has_isolated_items",
        }
        assert expected_flag_keys.issubset(set(bt_quality_flags.keys())), (
            f"bt_quality_flags keys {set(bt_quality_flags.keys())} "
            f"missing expected {expected_flag_keys}"
        )

        # 6. Decision-level consistency: success rate and budget sanity.
        success_rate = completed / callbacks_received
        assert success_rate == pytest.approx(1.0, rel=0.0, abs=1e-6)

        comparison_budget = processing.get("comparison_budget") or {}
        max_pairs_cap = comparison_budget.get("max_pairs_requested")
        if not isinstance(max_pairs_cap, int):
            # Fallback to recorded budget or total comparisons.
            max_pairs_cap = batch_state.total_budget or total_comparisons

        if isinstance(max_pairs_cap, int):
            assert total_comparisons <= max_pairs_cap

        # Compute small-net flags from the same helper used in orchestration.
        settings = CJSettings()
        (
            _normalized_expected_essay_count,
            is_small_net,
            small_net_max_pairs,
            small_net_successful_pairs,
            small_net_unique_complete,
            small_net_resampling_pass_count,
            small_net_resampling_cap,
            small_net_cap_reached,
        ) = build_small_net_context(
            expected_essay_count=batch_state.batch_upload.expected_essay_count,
            max_possible_pairs=max_possible_pairs or 0,
            successful_pairs_count=successful_pairs_count or 0,
            unique_coverage_complete=bool(unique_coverage_complete),
            resampling_pass_count=int(resampling_pass_count),
            min_resampling_net_size=settings.MIN_RESAMPLING_NET_SIZE,
            max_resampling_passes_for_small_net=settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET,
            coverage_metrics=None,
        )

        assert small_net_max_pairs == expected_max_pairs
        assert small_net_successful_pairs == expected_max_pairs
        assert small_net_unique_complete is True
        assert small_net_resampling_pass_count == resampling_pass_count
        assert small_net_resampling_cap >= 0

        # No failure reason should be recorded for a successful batch.
        assert "failed_reason" not in processing
