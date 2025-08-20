"""
E2E CJ Assessment Pipeline Workflows

Consolidated test suite for CJ Assessment pipeline validation, extracted and modernized from Step 5.
Tests complete CJ Assessment processing workflow from multiple essay uploads through ranking results

Uses modern utility patterns (ServiceTestManager + KafkaTestManager) throughout - NO direct calls.
Preserves all CJ assessment business logic:
real student essays, ranking validation, multi-essay coordination.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from huleedu_service_libs.logging_utils import create_service_logger

from tests.functional.pipeline_test_harness import PipelineTestHarness
from tests.utils.auth_manager import AuthTestManager
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager

logger = create_service_logger("test.e2e_cj_assessment")


class TestE2ECJAssessmentWorkflows:
    """Test CJ Assessment pipeline workflows using modern utility patterns exclusively."""

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_content_service_health_prerequisite(self):
        """Validate Content Service is healthy before CJ Assessment tests."""
        service_manager = ServiceTestManager()
        endpoints = await service_manager.get_validated_endpoints()

        if "content_service" not in endpoints:
            pytest.skip("Content Service not available for CJ Assessment testing")

        # Health validation is built into get_validated_endpoints()
        assert endpoints["content_service"]["status"] == "healthy"

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_cj_assessment_service_health_prerequisite(self):
        """Validate CJ Assessment Service metrics before pipeline tests."""
        service_manager = ServiceTestManager()

        # Use utility to get metrics instead of direct HTTP call
        metrics_text = await service_manager.get_service_metrics("cj_assessment_service", 9095)

        if metrics_text is None:
            pytest.skip("CJ Assessment Service metrics not available")

        # Validate Prometheus metrics format
        assert "http_requests_total" in metrics_text  # Basic Prometheus metric

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    @pytest.mark.timeout(300)  # 5 minute timeout for complete CJ pipeline
    async def test_complete_cj_assessment_processing_pipeline(self):
        """
        Test CJ pipeline end-to-end using the PipelineTestHarness (guest flow):
        1) Register batch and upload essays via File Service
        2) Publish client pipeline request for 'cj_assessment'
        3) Wait for CJ thin completion event (ELS)
        4) Validate rich AssessmentResult event (RAS)
        """
        # Managers and harness
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_mgr = KafkaTestManager()
        harness = PipelineTestHarness(service_manager, kafka_mgr, auth_manager)

        # Use real student essays (guest flow)
        essay_files = [
            Path("test_uploads/real_test_batch/MHHXGMXL 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMXE 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMUX 50 (SA24D ENG 5 WRITING 2025).txt"),
            Path("test_uploads/real_test_batch/MHHXGMUU 50 (SA24D ENG 5 WRITING 2025).txt"),
        ]

        try:
            # Setup guest batch and run CJ pipeline
            batch_id, corr = await harness.setup_guest_batch(essay_files)

            result = await harness.execute_pipeline(
                pipeline_name="cj_assessment",
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="cj_assessment.completed",
                validate_phase_pruning=False,
                timeout_seconds=240,
            )

            assert result.all_steps_completed, "CJ pipeline did not complete"
            assert "cj_assessment" in result.executed_steps

            # Validate RAS result from pipeline execution
            assert result.ras_result_event is not None, (
                "RAS BatchResultsReadyV1 event was not received"
            )

            # Extract and validate the BatchResultsReadyV1 summary data
            # This is a thin event with summary info, not detailed results
            ras_event_data = result.ras_result_event["data"]

            # Validate the summary fields from BatchResultsReadyV1
            assert ras_event_data["batch_id"] == batch_id
            assert ras_event_data["total_essays"] == len(essay_files)
            assert ras_event_data["completed_essays"] == len(essay_files)

            # Validate phase results are present
            assert "phase_results" in ras_event_data
            phase_results = ras_event_data["phase_results"]

            # Should have results for spellcheck and cj_assessment phases
            assert "spellcheck" in phase_results
            assert "cj_assessment" in phase_results

            # Validate overall batch status (use correct enum values)
            assert ras_event_data["overall_status"] in [
                "completed_successfully",
                "completed_with_failures",
            ]
            assert ras_event_data["processing_duration_seconds"] > 0

            # Now query the RAS API to get detailed results
            # This validates that downstream services can fetch detailed data after receiving the thin event
            # Note: RAS uses internal authentication, so we need to make a direct request with proper headers
            import json

            import aiohttp

            async with aiohttp.ClientSession() as session:
                headers = {
                    "X-Internal-API-Key": "internal_dev_key_7f3e9a2b5d1c4f8g",
                    "X-Service-ID": "api-gateway-service",
                    "X-Correlation-ID": corr,
                }

                async with session.get(
                    f"http://localhost:4003/internal/v1/batches/{batch_id}/status",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    assert response.status == 200, f"Failed to get batch status: {response.status}"
                    detailed_results = await response.json()

            # Log the RAS API response for debugging
            logger.info("📊 RAS API Response for batch %s:", batch_id)
            logger.info("Overall Status: %s", detailed_results.get("overall_status"))
            logger.info("Essay Count: %s", detailed_results.get("essay_count"))
            logger.info("Completed Essays: %s", detailed_results.get("completed_essay_count"))

            # Validate the detailed results from RAS API
            assert detailed_results["batch_id"] == batch_id
            assert detailed_results["overall_status"] in [
                "completed_successfully",
                "completed_with_failures",
            ]

            # Check that we have essay results with CJ assessment data
            assert "essays" in detailed_results
            essay_results = detailed_results["essays"]
            assert len(essay_results) >= len(essay_files)

            # Log CJ Assessment data from RAS
            logger.info("📈 CJ Assessment Results from RAS:")
            for i, essay_result in enumerate(essay_results):
                logger.info("  Essay %d:", i + 1)
                logger.info("    - Essay ID: %s", essay_result.get("essay_id"))
                logger.info("    - CJ Status: %s", essay_result.get("cj_assessment_status"))
                logger.info("    - CJ Rank: %s", essay_result.get("cj_rank"))
                logger.info("    - CJ Score: %s", essay_result.get("cj_score"))
                logger.info("    - Spellcheck Status: %s", essay_result.get("spellcheck_status"))
                logger.info(
                    "    - Spellcheck Corrections: %s",
                    essay_result.get("spellcheck_correction_count"),
                )

            # Pretty print a sample essay result for detailed inspection
            if essay_results:
                logger.info("📝 Sample Essay Result (full structure):")
                logger.info(json.dumps(essay_results[0], indent=2, default=str))

            # Validate each essay has CJ assessment results
            for essay_result in essay_results:
                assert "essay_id" in essay_result
                assert "cj_assessment_status" in essay_result  # Should have CJ assessment status

                # If CJ assessment was successful, validate the scores
                if essay_result["cj_assessment_status"] == "completed":
                    assert "cj_rank" in essay_result
                    assert "cj_score" in essay_result

        finally:
            await harness.cleanup()
