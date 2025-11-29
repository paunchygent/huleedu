"""
Kafka consumer logic for CJ Assessment Service.

Handles CJ assessment request message processing using injected dependencies.
Follows clean architecture with DI pattern.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.event_processor import (
    # TODO: To be implemented by Agent Beta
    process_llm_result,  # type: ignore
    process_single_message,
)
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
    PairMatchingStrategyProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment.kafka.consumer")


class CJAssessmentKafkaConsumer:
    """Kafka consumer for handling CJ assessment request events."""

    def __init__(
        self,
        settings: Settings,
        session_provider: SessionProviderProtocol,
        batch_repository: CJBatchRepositoryProtocol,
        essay_repository: CJEssayRepositoryProtocol,
        comparison_repository: CJComparisonRepositoryProtocol,
        instruction_repository: AssessmentInstructionRepositoryProtocol,
        anchor_repository: AnchorRepositoryProtocol,
        content_client: ContentClientProtocol,
        event_publisher: CJEventPublisherProtocol,
        llm_interaction: LLMInteractionProtocol,
        matching_strategy: PairMatchingStrategyProtocol,
        redis_client: RedisClientProtocol,
        grade_projector: GradeProjector,
        tracer: "Tracer | None" = None,
    ) -> None:
        """Initialize with injected dependencies."""
        self.settings = settings
        self.session_provider = session_provider
        self.batch_repository = batch_repository
        self.essay_repository = essay_repository
        self.comparison_repository = comparison_repository
        self.instruction_repository = instruction_repository
        self.anchor_repository = anchor_repository
        self.content_client = content_client
        self.event_publisher = event_publisher
        self.llm_interaction = llm_interaction
        self.matching_strategy = matching_strategy
        self.redis_client = redis_client
        self.grade_projector = grade_projector
        self.tracer = tracer
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

        # Create idempotent message processors with v2 configuration for complex AI workflows
        config = IdempotencyConfig(
            service_name="cj-assessment-service",
            default_ttl=86400,  # 24 hours for complex AI processing
            enable_debug_logging=True,  # Enable for AI workflow monitoring
        )

        # Processor for assessment request messages
        @idempotent_consumer(redis_client=redis_client, config=config)
        async def process_assessment_request_idempotently(
            msg: Any, *, confirm_idempotency: Callable[[], Awaitable[None]]
        ) -> bool | None:
            result = await process_single_message(
                msg=msg,
                session_provider=self.session_provider,
                batch_repository=self.batch_repository,
                essay_repository=self.essay_repository,
                instruction_repository=self.instruction_repository,
                anchor_repository=self.anchor_repository,
                comparison_repository=self.comparison_repository,
                content_client=self.content_client,
                event_publisher=self.event_publisher,
                llm_interaction=self.llm_interaction,
                matching_strategy=self.matching_strategy,
                settings_obj=self.settings,
                grade_projector=self.grade_projector,
                tracer=self.tracer,
            )
            await confirm_idempotency()  # Confirm after successful processing
            return result

        # Processor for LLM callback messages
        @idempotent_consumer(redis_client=redis_client, config=config)
        async def process_llm_callback_idempotently(
            msg: Any, *, confirm_idempotency: Callable[[], Awaitable[None]]
        ) -> bool | None:
            result = await process_llm_result(
                msg=msg,
                session_provider=self.session_provider,
                batch_repository=self.batch_repository,
                essay_repository=self.essay_repository,
                comparison_repository=self.comparison_repository,
                event_publisher=self.event_publisher,
                content_client=self.content_client,
                llm_interaction=self.llm_interaction,
                matching_strategy=self.matching_strategy,
                settings_obj=self.settings,
                instruction_repository=self.instruction_repository,
                grade_projector=self.grade_projector,
                tracer=self.tracer,
            )
            await confirm_idempotency()  # Confirm after successful processing
            return result

        self._process_assessment_request_idempotently = process_assessment_request_idempotently
        self._process_llm_callback_idempotently = process_llm_callback_idempotently

    async def start_consumer(self) -> None:
        """Start the Kafka consumer and begin processing messages."""
        # Subscribe to BOTH topics
        topics = [
            self.settings.CJ_ASSESSMENT_REQUEST_TOPIC,  # Original requests
            self.settings.LLM_PROVIDER_CALLBACK_TOPIC,  # LLM callbacks
        ]

        # Create Kafka consumer
        self.consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.settings.CONSUMER_GROUP_ID_CJ,
            auto_offset_reset="latest",
            enable_auto_commit=False,
            max_poll_records=1,  # Process one at a time for consistency
            session_timeout_ms=45000,
        )

        try:
            await self.consumer.start()
            logger.info(
                "CJ Assessment Kafka consumer started",
                extra={
                    "topics": topics,
                    "group_id": self.settings.CONSUMER_GROUP_ID_CJ,
                },
            )

            # Start message processing loop
            await self._process_messages()

        except asyncio.CancelledError:
            logger.info("Kafka consumer task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in CJ Assessment Kafka consumer: {e}", exc_info=True)
            raise
        finally:
            await self.stop_consumer()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        self.should_stop = True
        if self.consumer:
            try:
                await self.consumer.stop()
                logger.info("CJ Assessment Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping CJ Assessment Kafka consumer: {e}")
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop."""
        if not self.consumer:
            return

        logger.info("Starting CJ Assessment message processing loop")

        while not self.should_stop:
            try:
                async for msg in self.consumer:
                    if self.should_stop:
                        break

                    try:
                        # Route message based on topic
                        if msg.topic == self.settings.CJ_ASSESSMENT_REQUEST_TOPIC:
                            result = await self._process_assessment_request_idempotently(msg)
                        elif msg.topic == self.settings.LLM_PROVIDER_CALLBACK_TOPIC:
                            result = await self._process_llm_callback_idempotently(msg)
                        else:
                            logger.warning(
                                f"Received message from unknown topic: {msg.topic}. "
                                f"Expected topics: {self.settings.CJ_ASSESSMENT_REQUEST_TOPIC}, "
                                f"{self.settings.LLM_PROVIDER_CALLBACK_TOPIC}"
                            )
                            # Skip unknown topic messages but still commit to avoid reprocessing
                            await self.consumer.commit()
                            continue

                        if result is not None:
                            # Only commit if not a skipped duplicate
                            if result:
                                await self.consumer.commit()
                                logger.debug(
                                    "Message committed: %s:%s:%s",
                                    msg.topic,
                                    msg.partition,
                                    msg.offset,
                                )
                            else:
                                logger.warning(
                                    f"Message processing failed, not committing: "
                                    f"{msg.topic}:{msg.partition}:{msg.offset}",
                                )
                        else:
                            # Message was a duplicate and skipped
                            logger.info(
                                f"Duplicate message skipped, not committing offset: "
                                f"{msg.topic}:{msg.partition}:{msg.offset}",
                            )

                    except Exception as e:
                        logger.error(f"Error processing message: {e}", exc_info=True)

            except KafkaConnectionError as kce:
                logger.error(f"Kafka connection error: {kce}", exc_info=True)
                if self.should_stop:
                    break
                await asyncio.sleep(5)  # Wait before retry
            except asyncio.CancelledError:
                logger.info("Message consumption cancelled")
                break
            except Exception as e:
                logger.error(f"Error in message processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

        logger.info("CJ Assessment message processing loop has finished")
