"""
Workflow Monitoring Utilities

Utility functions for monitoring pipeline resolution workflows and analyzing events
in E2E integration tests.
"""

from __future__ import annotations

import asyncio
from typing import Any


def is_related_to_batch(event_data: dict[str, Any], batch_id: str, correlation_id: str) -> bool:
    """Check if event is related to our test batch or correlation ID."""
    # Check data field for batch_id (supports both entity_id and batch_id fields)
    data = event_data.get("data", {})
    if isinstance(data, dict):
        if data.get("entity_id") == batch_id or data.get("batch_id") == batch_id:
            return True

    # Check correlation_id
    if event_data.get("correlation_id") == correlation_id:
        return True

    # Check if event mentions our batch in any field
    event_str = str(event_data).lower()
    if batch_id.lower() in event_str:
        return True

    return False


async def monitor_pipeline_resolution_workflow(
    consumer: Any,
    batch_id: str,
    correlation_id: str,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """
    Monitor the complete pipeline resolution workflow.

    Tracks events from ClientBatchPipelineRequestV1 → BOS → BCS → Pipeline Initiation.
    """
    start_time = asyncio.get_event_loop().time()
    end_time = start_time + timeout_seconds

    specialized_services_triggered: list[str] = []
    completion_events: list[dict[str, Any]] = []

    workflow_events: dict[str, Any] = {
        "client_request_processed": False,
        "bcs_resolution_completed": False,
        "pipeline_initiated": False,
        "specialized_services_triggered": specialized_services_triggered,
        "completion_events": completion_events,
    }

    print(f"🔍 Monitoring pipeline resolution workflow for batch {batch_id}")

    while asyncio.get_event_loop().time() <= end_time:
        try:
            # Wait up to 1s for the next message; continue if none arrives.
            message = await asyncio.wait_for(consumer.getone(), timeout=1.0)
        except TimeoutError:
            continue  # No message within 1s; loop until deadline

        try:
            # Parse message for event analysis
            if hasattr(message, "value"):
                import json

                event_data = json.loads(message.value.decode("utf-8"))

                # Check if event is related to our batch
                if not is_related_to_batch(event_data, batch_id, correlation_id):
                    continue

                event_type = event_data.get("event_type", "")
                print(f"📥 Received event: {event_type}")

                # Track pipeline resolution progress
                if "spellcheck.initiate.command" in event_type:
                    specialized_services_triggered.append("spellcheck")
                    print("✅ Spellcheck service triggered")

                elif "ai_feedback.initiate.command" in event_type:
                    specialized_services_triggered.append("ai_feedback")
                    print("✅ AI Feedback service triggered")

                elif "cj_assessment.initiate.command" in event_type:
                    specialized_services_triggered.append("cj_assessment")
                    print("✅ CJ Assessment service triggered")

                elif "batch_phase.outcome" in event_type:
                    completion_events.append(event_data)
                    print(f"📋 Phase outcome received: {event_type}")

                # Check if we have sufficient evidence of pipeline resolution
                if len(specialized_services_triggered) > 0 or len(completion_events) > 0:
                    workflow_events["pipeline_initiated"] = True
                    print("🎯 Pipeline resolution and initiation confirmed!")
                    break

        except Exception as e:
            print(f"⚠️ Error processing event: {e}")
            continue

    return workflow_events
