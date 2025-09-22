"""Batch NLP analysis handler for NLP Service Phase 2.

This handler processes batch NLP initiate commands during Phase 2 pipeline processing
to perform text analysis and grammar checking on essays.

Implements dual event pattern:
- Rich events (EssayNlpCompletedV1) → RAS for business data
- Thin event (BatchNlpAnalysisCompletedV1) → ELS for state management
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer

import aiohttp
from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import BatchNlpProcessingRequestedV2
from common_core.events.spellcheck_models import SpellcheckMetricsV1
from huleedu_nlp_shared.feature_pipeline import FeaturePipelineProtocol
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_external_service_error,
    raise_processing_error,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger, log_event_processing
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from pydantic import ValidationError

from services.nlp_service.protocols import (
    CommandHandlerProtocol,
    ContentClientProtocol,
    NlpEventPublisherProtocol,
)

logger = create_service_logger("nlp_service.command_handlers.batch_nlp_analysis")


class BatchNlpAnalysisHandler(CommandHandlerProtocol):
    """Handler for Phase 2 NLP analysis commands."""

    def __init__(
        self,
        content_client: ContentClientProtocol,
        event_publisher: NlpEventPublisherProtocol,
        outbox_repository: OutboxRepositoryProtocol,
        feature_pipeline: FeaturePipelineProtocol,
        tracer: "Tracer | None" = None,
    ) -> None:
        """Initialize with NLP analysis dependencies.

        Args:
            content_client: Client for fetching essay content
            event_publisher: Publisher for NLP analysis results (uses outbox internally)
            outbox_repository: Outbox repository for transactional publishing
            feature_pipeline: Shared feature pipeline orchestrating analysis
            tracer: Optional tracer for distributed tracing

        Note: No kafka_bus parameter - all event publishing uses outbox pattern
        """
        self.content_client = content_client
        self.event_publisher = event_publisher
        self.outbox_repository = outbox_repository
        self.feature_pipeline = feature_pipeline
        self.tracer = tracer

    async def can_handle(self, event_type: str) -> bool:
        """Check if this handler can process the given event type.

        Args:
            event_type: The event type string to check

        Returns:
            True if this handler can process Phase 2 batch NLP initiate commands
        """
        return event_type == topic_name(ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED_V2)

    async def handle(
        self,
        msg: ConsumerRecord,
        envelope: EventEnvelope,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        span: "Span | None" = None,
    ) -> bool:
        """Process NLP analysis batch.

        Args:
            msg: The Kafka message to process
            envelope: Already parsed event envelope
            http_session: HTTP session for external service calls
            correlation_id: Correlation ID for tracking
            span: Optional span for tracing

        Returns:
            True if at least one essay was successfully processed
        """
        try:
            # Parse and validate command data
            command_data = BatchNlpProcessingRequestedV2.model_validate(envelope.data)

            # Log event processing
            # Get batch_id from command_data
            batch_id = command_data.batch_id

            log_event_processing(
                logger=logger,
                message="Processing Phase 2 NLP analysis batch",
                envelope=envelope,
                current_processing_event="batch.nlp.analysis",
                batch_id=batch_id,
                essay_count=len(command_data.essays_to_process),
            )

            logger.info(
                f"Processing Phase 2 NLP analysis for batch {batch_id} "
                f"with {len(command_data.essays_to_process)} essays",
                extra={
                    "batch_id": batch_id,
                    "essay_count": len(command_data.essays_to_process),
                    "correlation_id": str(correlation_id),
                },
            )

            # Track batch processing start time
            batch_start_time = time.time()
            processed_count = 0
            failed_count = 0
            successful_essay_ids: list[str] = []
            failed_essay_ids: list[str] = []

            # Process each essay in the batch
            for essay_ref in command_data.essays_to_process:
                try:
                    logger.info(
                        f"Starting NLP analysis for essay {essay_ref.essay_id}",
                        extra={
                            "essay_id": essay_ref.essay_id,
                            "batch_id": batch_id,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Step 1: Fetch essay content
                    try:
                        essay_text = await self.content_client.fetch_content(
                            storage_id=essay_ref.text_storage_id,
                            http_session=http_session,
                            correlation_id=correlation_id,
                        )
                    except HuleEduError:
                        # Already structured error from content client
                        raise
                    except aiohttp.ClientError as e:
                        raise_external_service_error(
                            service="nlp_service",
                            operation="fetch_essay_content",
                            external_service="content_service",
                            message=(
                                f"Failed to fetch content for essay {essay_ref.essay_id}: {str(e)}"
                            ),
                            correlation_id=correlation_id,
                            essay_id=essay_ref.essay_id,
                            batch_id=batch_id,
                        )

                    if not essay_text:
                        logger.warning(
                            f"Empty content for essay {essay_ref.essay_id}, skipping",
                            extra={
                                "essay_id": essay_ref.essay_id,
                                "correlation_id": str(correlation_id),
                            },
                        )
                        continue

                    # Step 2: Run feature pipeline using normalized text and spell metrics
                    language = getattr(command_data, "language", "auto")

                    spellcheck_metrics = getattr(essay_ref, "spellcheck_metrics", None)
                    if spellcheck_metrics is None:
                        logger.warning(
                            "Spellcheck metrics missing for essay; defaulting to zero values",
                            extra={
                                "essay_id": essay_ref.essay_id,
                                "batch_id": batch_id,
                                "correlation_id": str(correlation_id),
                            },
                        )
                        approximate_word_count = len(essay_text.split())
                        spellcheck_metrics = SpellcheckMetricsV1(
                            total_corrections=0,
                            l2_dictionary_corrections=0,
                            spellchecker_corrections=0,
                            word_count=approximate_word_count,
                            correction_density=0.0,
                        )

                    try:
                        pipeline_result = await self.feature_pipeline.extract_features(
                            normalized_text=essay_text,
                            spellcheck_metrics=spellcheck_metrics,
                            prompt_text=command_data.essay_instructions,
                            essay_id=essay_ref.essay_id,
                            batch_id=batch_id,
                            language=language,
                            http_session=http_session,
                            correlation_id=correlation_id,
                        )
                    except HuleEduError:
                        raise
                    except aiohttp.ClientError as e:
                        raise_external_service_error(
                            service="nlp_service",
                            operation="feature_pipeline",
                            external_service="language_tool_service",
                            message=(
                                f"Language Tool request failed for essay {essay_ref.essay_id}: {str(e)}"
                            ),
                            correlation_id=correlation_id,
                            essay_id=essay_ref.essay_id,
                            batch_id=batch_id,
                        )
                    except Exception as e:
                        raise_processing_error(
                            service="nlp_service",
                            operation="feature_pipeline",
                            stage="extract_features",
                            message=(
                                f"Unexpected error running feature pipeline for essay {essay_ref.essay_id}: {str(e)}"
                            ),
                            correlation_id=correlation_id,
                            essay_id=essay_ref.essay_id,
                            batch_id=batch_id,
                        )

                    context = pipeline_result.context
                    nlp_metrics = context.nlp_metrics
                    grammar_analysis = context.grammar_analysis

                    if nlp_metrics is None:
                        raise_processing_error(
                            service="nlp_service",
                            operation="feature_pipeline",
                            stage="nlp_metrics_missing",
                            message="Feature pipeline did not produce NLP metrics",
                            correlation_id=correlation_id,
                            essay_id=essay_ref.essay_id,
                            batch_id=batch_id,
                        )

                    if grammar_analysis is None:
                        raise_processing_error(
                            service="nlp_service",
                            operation="feature_pipeline",
                            stage="grammar_analysis_missing",
                            message="Feature pipeline did not produce grammar analysis",
                            correlation_id=correlation_id,
                            essay_id=essay_ref.essay_id,
                            batch_id=batch_id,
                        )

                    logger.debug(
                        f"Completed feature pipeline for essay {essay_ref.essay_id}",
                        extra={
                            "essay_id": essay_ref.essay_id,
                            "word_count": nlp_metrics.word_count,
                            "grammar_error_count": grammar_analysis.error_count,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Step 4: Publish NLP analysis results via outbox
                    await self.event_publisher.publish_essay_nlp_completed(
                        # Note: No kafka_bus parameter - publisher uses outbox internally
                        essay_id=essay_ref.essay_id,
                        text_storage_id=essay_ref.text_storage_id,
                        nlp_metrics=nlp_metrics,
                        grammar_analysis=grammar_analysis,
                        correlation_id=correlation_id,
                        feature_outputs=pipeline_result.features,
                        essay_instructions=command_data.essay_instructions,
                    )

                    processed_count += 1
                    successful_essay_ids.append(essay_ref.essay_id)
                    logger.info(
                        f"Successfully processed NLP analysis for essay {essay_ref.essay_id}",
                        extra={
                            "essay_id": essay_ref.essay_id,
                            "batch_id": batch_id,
                            "correlation_id": str(correlation_id),
                        },
                    )

                except HuleEduError as e:
                    # Already structured error - log and continue
                    failed_count += 1
                    failed_essay_ids.append(essay_ref.essay_id)
                    logger.error(
                        f"Structured error processing essay {essay_ref.essay_id}: {e}",
                        extra={
                            "essay_id": essay_ref.essay_id,
                            "batch_id": batch_id,
                            "correlation_id": str(correlation_id),
                            "error_type": type(e).__name__,
                        },
                    )
                    # Continue processing other essays
                    continue

                except Exception as e:
                    # Unexpected error - wrap in structured error
                    failed_count += 1
                    failed_essay_ids.append(essay_ref.essay_id)
                    try:
                        raise_processing_error(
                            service="nlp_service",
                            operation="analyze_essay",
                            stage="nlp_analysis",
                            message=(
                                f"Unexpected error analyzing essay {essay_ref.essay_id}: {str(e)}"
                            ),
                            correlation_id=correlation_id,
                            essay_id=essay_ref.essay_id,
                            batch_id=batch_id,
                        )
                    except HuleEduError as structured_error:
                        logger.error(
                            f"Processing error for essay {essay_ref.essay_id}: {structured_error}",
                            exc_info=True,
                            extra={
                                "essay_id": essay_ref.essay_id,
                                "batch_id": batch_id,
                                "correlation_id": str(correlation_id),
                            },
                        )
                    # Continue processing other essays
                    continue

            # Calculate batch processing time
            batch_processing_time = time.time() - batch_start_time

            # Log batch processing summary
            logger.info(
                f"Completed Phase 2 NLP analysis for batch {batch_id}: "
                f"{processed_count}/{len(command_data.essays_to_process)} essays processed "
                f"successfully",
                extra={
                    "batch_id": batch_id,
                    "processed_count": processed_count,
                    "failed_count": failed_count,
                    "total_count": len(command_data.essays_to_process),
                    "processing_time_seconds": batch_processing_time,
                    "correlation_id": str(correlation_id),
                },
            )

            # Publish batch completion event to ELS (thin event for state management)
            # This follows the dual event pattern: RAS gets rich data, ELS gets state updates
            try:
                await self.event_publisher.publish_batch_nlp_analysis_completed(
                    batch_id=batch_id,
                    total_essays=len(command_data.essays_to_process),
                    successful_count=processed_count,
                    failed_count=failed_count,
                    successful_essay_ids=successful_essay_ids,
                    failed_essay_ids=failed_essay_ids,
                    processing_time_seconds=batch_processing_time,
                    correlation_id=correlation_id,
                )

                logger.info(
                    f"Published batch completion event to ELS for batch {batch_id}",
                    extra={
                        "batch_id": batch_id,
                        "correlation_id": str(correlation_id),
                    },
                )
            except Exception as e:
                logger.error(
                    f"Failed to publish batch completion event: {e}",
                    exc_info=True,
                    extra={
                        "batch_id": batch_id,
                        "correlation_id": str(correlation_id),
                    },
                )
                # Don't fail the entire batch if we can't publish the completion event
                # The individual essay events to RAS are more important

            # Return True if at least one essay was processed
            return processed_count > 0

        except ValidationError as e:
            # Invalid command format
            raise_validation_error(
                service="nlp_service",
                operation="parse_nlp_command",
                field="envelope.data",
                message=f"Invalid NLP command format: {e.errors()}",
                correlation_id=correlation_id,
            )
        except HuleEduError:
            # Already structured error - re-raise
            raise
        except Exception as e:
            # Unexpected error at batch level
            raise_processing_error(
                service="nlp_service",
                operation="handle_nlp_command",
                stage="command_processing",
                message=f"Unexpected error processing NLP batch: {str(e)}",
                correlation_id=correlation_id,
            )
