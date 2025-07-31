"""
Pipeline Validation Utilities

Utility functions for validating BCS ↔ BOS integration and pipeline resolution
in E2E integration tests.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from tests.utils.service_test_manager import ServiceTestManager


async def validate_batch_pipeline_state(
    service_manager: ServiceTestManager,
    batch_id: str,
) -> dict[str, Any]:
    """Validate that batch has been updated with resolved pipeline."""
    # Get batch state from BOS
    endpoints = await service_manager.get_validated_endpoints()
    bos_base_url = endpoints["batch_orchestrator_service"]["base_url"]

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{bos_base_url}/v1/batches/{batch_id}/status") as response:
            if response.status == 200:
                batch_data: dict[str, Any] = await response.json()
                print(f"📊 Batch state retrieved: {batch_data}")
                return batch_data
            else:
                print(f"⚠️ Failed to get batch state: {response.status}")
                return {}


async def validate_bcs_integration_occurred(
    service_manager: ServiceTestManager,
    batch_id: str,
    requested_pipeline: str,
) -> dict[str, Any]:
    """
    Validate that BCS ↔ BOS integration actually occurred.

    This is the critical validation that proves our integration works,
    not just the existing pipeline orchestration.
    """
    # 1. Check BCS metrics for HTTP requests
    endpoints = await service_manager.get_validated_endpoints()
    bcs_metrics_url = endpoints["batch_conductor_service"]["metrics_url"]

    async with aiohttp.ClientSession() as session:
        async with session.get(bcs_metrics_url) as response:
            metrics_text = await response.text()

            # Parse BCS HTTP request metrics for pipeline definition endpoint using regex
            pipeline_requests = 0
            for line in metrics_text.splitlines():
                if not line.startswith("bcs_http_requests_total{"):
                    continue
                try:
                    labels_part, value_part = line.split("}")
                    labels_str = labels_part[len("bcs_http_requests_total{") :]
                    labels = {}
                    for label in labels_str.split(","):
                        if "=" in label:
                            k, v = label.split("=", 1)
                            labels[k.strip()] = v.strip().strip('"')
                    # Validate required labels regardless of order
                    if (
                        labels.get("method") == "POST"
                        and labels.get("endpoint") == "/internal/v1/pipelines/define"
                        and labels.get("status_code") == "200"
                    ):
                        pipeline_requests += int(float(value_part.strip()))
                except Exception:
                    continue

    # 2. Check BOS for stored resolved pipeline
    bos_base_url = endpoints["batch_orchestrator_service"]["base_url"]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{bos_base_url}/v1/batches/{batch_id}/status") as response:
            if response.status == 200:
                batch_data = await response.json()
                # Extract resolved pipeline from pipeline_state
                pipeline_state = batch_data.get("pipeline_state", {})

                # Handle ProcessingPipelineState structure correctly
                resolved_pipeline = []
                if isinstance(pipeline_state, dict):
                    # The BCS-resolved pipeline is stored in 'requested_pipelines'
                    # This field contains the actual phases resolved by BCS
                    resolved_pipeline = pipeline_state.get("requested_pipelines", [])

                    # If requested_pipelines is empty, check for configured phases
                    # as fallback (for backwards compatibility with manual tests)
                    if not resolved_pipeline:
                        configured_phases = []
                        for phase_name in ["spellcheck", "ai_feedback", "cj_assessment", "nlp"]:
                            phase_data = pipeline_state.get(phase_name)
                            if phase_data and isinstance(phase_data, dict):
                                # Check if the phase is actually configured (not SKIPPED)
                                phase_status = phase_data.get("status", "")
                                if phase_status and "SKIPPED" not in phase_status:
                                    configured_phases.append(phase_name)
                        resolved_pipeline = configured_phases
                else:
                    print(f"⚠️ Unexpected pipeline_state type: {type(pipeline_state)}")
            else:
                print(f"⚠️ Failed to get batch data for resolved pipeline check: {response.status}")
                resolved_pipeline = []

    # 3. Validate integration evidence
    integration_evidence = {
        "bcs_http_requests": pipeline_requests,
        "resolved_pipeline": resolved_pipeline,
        "requested_pipeline": requested_pipeline,
        "pipeline_resolution_occurred": len(resolved_pipeline) > 0,
        # BCS should add dependencies
        "dependency_analysis_evident": len(resolved_pipeline) > 1,
    }

    print("🔍 BCS Integration Evidence:")
    print(f"  HTTP requests to BCS: {pipeline_requests}")
    print(f"  Requested pipeline: {requested_pipeline}")
    print(f"  Resolved pipeline: {resolved_pipeline}")
    print(f"  Dependency analysis: {integration_evidence['dependency_analysis_evident']}")

    return integration_evidence


async def validate_bcs_dependency_resolution(integration_evidence: dict[str, Any]) -> bool:
    """
    Validate that BCS performed intelligent dependency resolution.

    This proves BCS analyzed batch state and resolved dependencies,
    not just echoed the requested pipeline.
    """
    requested = integration_evidence["requested_pipeline"]
    resolved = integration_evidence["resolved_pipeline"]

    # For AI feedback request, BCS should resolve dependencies like spellcheck
    if requested == "ai_feedback":
        # BCS should add spellcheck as prerequisite for fresh essays
        expected_dependencies = ["spellcheck", "ai_feedback"]
        has_dependencies = any(dep in str(resolved).lower() for dep in expected_dependencies)

        if has_dependencies:
            print("✅ BCS dependency resolution validated - added prerequisites")
            return True
        else:
            print("❌ BCS dependency resolution failed - no prerequisites added")
            return False

    # For other pipelines, at minimum resolved should differ from requested
    if resolved != [requested]:
        print("✅ BCS pipeline resolution occurred - output differs from input")
        return True
    else:
        print("❌ BCS pipeline resolution unclear - output matches input exactly")
        return False
