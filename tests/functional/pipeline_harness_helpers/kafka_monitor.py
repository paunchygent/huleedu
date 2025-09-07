"""Kafka monitoring helper for pipeline tests."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from tests.utils.kafka_test_manager import KafkaTestManager

from tests.functional.pipeline_harness_helpers.entitlements_monitor import (
    EntitlementsMonitorHelper,
)
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.kafka_monitor")


@dataclass
class PipelineExecutionTracker:
    """Tracks events during pipeline execution."""

    initiated_phases: Set[str] = field(default_factory=set)
    completed_phases: Set[str] = field(default_factory=set)
    storage_ids: Dict[str, str] = field(default_factory=dict)
    pruned_phases: List[str] = field(default_factory=list)
    reused_storage_ids: Dict[str, str] = field(default_factory=dict)
    ras_result_event: Optional[Dict[str, Any]] = None  # Store BatchResultsReadyV1 event
    entitlements_events: Dict[str, bool] = field(
        default_factory=lambda: {"balance_changed": False, "usage_recorded": False}
    )  # Track Entitlements events


class KafkaMonitorHelper:
    """Helper class for monitoring Kafka events during pipeline execution."""

    @staticmethod
    async def start_consumer(
        kafka_manager: "KafkaTestManager",
        pipeline_topics: Dict[str, str],
    ) -> Any:
        """
        Start a Kafka consumer for monitoring events.

        Args:
            kafka_manager: Kafka test manager instance
            pipeline_topics: Dictionary of pipeline topics to monitor

        Returns:
            Consumer instance and context (should be closed with cleanup_consumer)
        """
        # Phase 2 specific topics (student matching)
        phase2_topics = [
            "huleedu.batch.student.matching.initiate.command.v1",
            "huleedu.batch.student.matching.requested.v1",
            "huleedu.batch.author.matches.suggested.v1",
            "huleedu.class.student.associations.confirmed.v1",
            "huleedu.els.batch.essays.ready.v1",
        ]

        # Entitlements topics for credit tracking
        entitlements_topics = [
            "huleedu.entitlements.credit.balance.changed.v1",
            "huleedu.entitlements.usage.recorded.v1",
        ]

        all_topics = list(pipeline_topics.values()) + phase2_topics + entitlements_topics

        # Create consumer context
        consumer_context = kafka_manager.consumer("pipeline_test_harness", all_topics)
        consumer = await consumer_context.__aenter__()
        # Consumer uses default auto_offset_reset="latest" which seeks to end
        # This is correct since we want to see events published AFTER consumer creation
        logger.info("📡 Kafka consumer started for pipeline monitoring")
        return consumer, consumer_context

    @staticmethod
    async def cleanup_consumer(consumer_context: Any) -> None:
        """
        Cleanup Kafka consumer.

        Args:
            consumer_context: Consumer context to cleanup
        """
        if consumer_context:
            await consumer_context.__aexit__(None, None, None)
            logger.info("📡 Kafka consumer cleaned up")

    @staticmethod
    async def monitor_pipeline_execution(
        consumer: Any,
        request_correlation_id: str,
        batch_correlation_id: Optional[str],
        expected_steps: List[str],
        expected_completion_event: str,
        tracker: PipelineExecutionTracker,
        timeout_seconds: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Monitor pipeline execution and track phases.

        Args:
            consumer: Kafka consumer instance
            request_correlation_id: Correlation ID for the pipeline request
            batch_correlation_id: Original batch correlation ID (for CJ completion)
            expected_steps: List of expected pipeline steps
            expected_completion_event: Event that signals pipeline completion
            tracker: Tracker for monitoring execution state
            timeout_seconds: Timeout for monitoring

        Returns:
            The completion event envelope if successful, None otherwise
        """
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + timeout_seconds

        while asyncio.get_event_loop().time() < end_time:
            try:
                if not consumer:
                    raise RuntimeError("Consumer not initialized")
                msg_batch = await consumer.getmany(timeout_ms=1000, max_records=10)

                for topic_partition, messages in msg_batch.items():
                    for message in messages:
                        try:
                            # Parse message
                            if isinstance(message.value, bytes):
                                raw_message = message.value.decode("utf-8")
                            else:
                                raw_message = message.value

                            envelope_data: Dict[str, Any] = json.loads(raw_message)
                            event_correlation_id = envelope_data.get("correlation_id")
                            event_type = envelope_data.get("event_type", "")
                            event_data = envelope_data.get("data", {})

                            # Filter by correlation ID - STRICT filtering for THIS pipeline request
                            # Special-case: CJ completion events may be published with the original
                            # batch registration correlation_id instead of the pipeline request ID.
                            if event_correlation_id != request_correlation_id:
                                is_cj_completion = (
                                    expected_completion_event in event_type
                                    and "cj_assessment.completed" in event_type
                                )
                                if not (
                                    is_cj_completion
                                    and batch_correlation_id
                                    and event_correlation_id == batch_correlation_id
                                ):
                                    continue

                            # Debug log ALL events with our correlation ID
                            logger.debug(
                                f"📡 Event received: type={event_type}, "
                                f"phase={event_data.get('phase_name', 'N/A')}, "
                                f"correlation={event_correlation_id[:8]}..."
                            )

                            # Track phase initiations - these determine what's actually executing
                            if "initiate.command" in event_type:
                                if "spellcheck" in event_type:
                                    tracker.initiated_phases.add("spellcheck")
                                    logger.info("📨 Spellcheck phase initiated")
                                elif "nlp" in event_type and "student.matching" not in event_type:
                                    tracker.initiated_phases.add("nlp")
                                    logger.info("📨 NLP analysis phase initiated")
                                elif "cj_assessment" in event_type or "cj.assessment" in event_type:
                                    tracker.initiated_phases.add("cj_assessment")
                                    logger.info("📨 CJ Assessment phase initiated")
                                elif "ai_feedback" in event_type or "ai.feedback" in event_type:
                                    tracker.initiated_phases.add("ai_feedback")
                                    logger.info("📨 AI Feedback phase initiated")

                            # Track phase completions - ONLY count as executed if initiated
                            elif "phase.outcome" in event_type:
                                phase_name = event_data.get("phase_name")
                                phase_status = event_data.get("phase_status")
                                storage_id = event_data.get("storage_id")

                                if phase_status in [
                                    "completed_successfully",
                                    "completed_with_failures",
                                ]:
                                    # CRITICAL: Only add to completed if initiated in THIS execution
                                    if phase_name in tracker.initiated_phases:
                                        tracker.completed_phases.add(phase_name)
                                        if storage_id:
                                            tracker.storage_ids[phase_name] = storage_id
                                        logger.info(f"✅ Phase {phase_name} completed")
                                    else:
                                        logger.debug(
                                            f"⚠️ Ignoring phase completion for {phase_name} - "
                                            f"not initiated in this pipeline execution"
                                        )

                            # Check for phase skipped/pruned events
                            elif "phase.skipped" in event_type:
                                phase_name = event_data.get("phase_name")
                                storage_id = event_data.get("storage_id")
                                skip_reason = event_data.get("skip_reason", "already_completed")

                                tracker.pruned_phases.append(phase_name)
                                if storage_id:
                                    tracker.reused_storage_ids[phase_name] = storage_id
                                logger.info(f"⏭️ Phase {phase_name} SKIPPED (reason: {skip_reason})")

                            # Legacy phase reuse detection (remove once phase.skipped events work)
                            elif "phase.reused" in event_type:
                                phase_name = event_data.get("phase_name")
                                storage_id = event_data.get("storage_id")
                                tracker.pruned_phases.append(phase_name)
                                if storage_id:
                                    tracker.reused_storage_ids[phase_name] = storage_id
                                logger.info(
                                    f"⏭️ Phase {phase_name} pruned (reusing existing results)"
                                )

                            # Check for specific completion events - indicate pipeline completion
                            # but should NOT add phases to executed list
                            if expected_completion_event in event_type:
                                # Extract phase from completion event type for special handling
                                if "spellcheck.completed" in event_type:
                                    # Individual essay completions - don't track as phase completion
                                    pass
                                elif "nlp.analysis.completed" in event_type:
                                    # Only mark nlp as completed if it was initiated
                                    if "nlp" in tracker.initiated_phases:
                                        tracker.completed_phases.add("nlp")
                                        logger.info(
                                            "✅ Phase nlp completed (from analysis completion)"
                                        )
                                    # For NLP pipelines, treat analysis completion as terminal
                                    logger.info(
                                        f"🎯 Pipeline completed: {expected_completion_event}"
                                    )
                                    return envelope_data
                                elif "cj_assessment.completed" in event_type:
                                    # Only mark cj_assessment as completed if it was initiated
                                    if "cj_assessment" in tracker.initiated_phases:
                                        tracker.completed_phases.add("cj_assessment")
                                        logger.info(
                                            "✅ Phase cj_assessment completed "
                                            "(from assessment completion)"
                                        )
                                    # For CJ assessment pipelines, we need to wait for RAS results
                                    # Continue monitoring instead of returning
                                    logger.info(
                                        "📊 CJ Assessment completed, waiting for "
                                        "RAS BatchResultsReadyV1..."
                                    )
                                    continue  # Don't return yet for CJ pipelines
                                else:
                                    # For non-CJ pipelines, return immediately
                                    logger.info(
                                        f"🎯 Pipeline completed: {expected_completion_event}"
                                    )
                                    return envelope_data

                            # Check for BatchResultsReadyV1 event from RAS
                            # This is the true completion event for CJ assessment pipelines
                            if "batch.results.ready" in event_type:
                                # Store the RAS result event for validation
                                tracker.ras_result_event = envelope_data
                                logger.info("📊 BatchResultsReadyV1 received from RAS")

                                # If we're waiting for CJ completion and have received RAS results,
                                # the pipeline is truly complete
                                if "cj_assessment" in tracker.completed_phases:
                                    logger.info("🎯 Pipeline fully completed with RAS results")
                                    return envelope_data

                            # Track Entitlements events (credit consumption is part of pipeline)
                            if EntitlementsMonitorHelper.is_entitlements_event(message.topic):
                                EntitlementsMonitorHelper.process_entitlements_event(
                                    message.topic,
                                    envelope_data,
                                    tracker.entitlements_events,
                                )

                        except Exception as e:
                            logger.warning(f"Error parsing message: {e}")
                            continue

            except asyncio.TimeoutError:
                continue

        logger.error(f"Pipeline did not complete within {timeout_seconds} seconds")
        logger.error(f"Initiated phases: {tracker.initiated_phases}")
        logger.error(f"Completed phases: {tracker.completed_phases}")
        return None
