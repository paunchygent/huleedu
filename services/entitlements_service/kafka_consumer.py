"""Kafka consumer for Entitlements Service.

Consumes resource consumption events and debits credits accordingly, using
idempotent processing and manual offset commits for reliability.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiokafka import AIOKafkaConsumer
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.resource_consumption_events import ResourceConsumptionV1
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol

from services.entitlements_service.protocols import CreditManagerProtocol

logger = create_service_logger("entitlements.kafka.consumer")


class EntitlementsKafkaConsumer:
    """Kafka consumer handling ResourceConsumptionV1 events."""

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        consumer_group: str,
        credit_manager: CreditManagerProtocol,
        redis_client: AtomicRedisClientProtocol,
    ) -> None:
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.consumer_group = consumer_group
        self.credit_manager = credit_manager
        self.redis_client = redis_client
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

    async def start_consumer(self) -> None:
        """Start the Kafka consumer and begin processing messages."""
        topic = topic_name(ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED)
        self.consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.kafka_bootstrap_servers,
            group_id=self.consumer_group,
            client_id="entitlements-resource-consumer",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )

        try:
            await self.consumer.start()
            logger.info(
                "Entitlements Kafka consumer started",
                extra={"group_id": self.consumer_group, "topic": topic},
            )
            await self._process_messages()
        except Exception as e:
            logger.error(f"Error starting Entitlements Kafka consumer: {e}")
            raise
        finally:
            await self.stop_consumer()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        self.should_stop = True
        if self.consumer:
            try:
                await self.consumer.stop()
                logger.info("Entitlements Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping Entitlements Kafka consumer: {e}")
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop with idempotency and manual commits."""
        if not self.consumer:
            return

        logger.info("Starting Entitlements message processing loop with idempotency")

        idem_config = IdempotencyConfig(
            service_name="entitlements-service",
            enable_debug_logging=True,
        )

        @idempotent_consumer(redis_client=self.redis_client, config=idem_config)
        async def handle_message_idempotently(
            msg: Any, *, confirm_idempotency: Callable[[], Awaitable[None]]
        ) -> bool:
            await self._handle_message(msg)
            await confirm_idempotency()
            return True

        try:
            async for msg in self.consumer:
                if self.should_stop:
                    logger.info("Shutdown requested, stopping Entitlements processing loop")
                    break

                try:
                    result = await handle_message_idempotently(msg)
                    if result:
                        await self.consumer.commit()
                        logger.debug(
                            "Processed and committed Entitlements message",
                            extra={
                                "topic": msg.topic,
                                "partition": msg.partition,
                                "offset": msg.offset,
                            },
                        )
                    else:
                        logger.info(
                            "Duplicate message skipped; not committing offset",
                            extra={
                                "topic": msg.topic,
                                "partition": msg.partition,
                                "offset": msg.offset,
                            },
                        )
                except Exception as e:
                    logger.error(
                        "Error processing Entitlements message",
                        extra={
                            "error": str(e),
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                    )
        except Exception as e:
            logger.error(f"Error in Entitlements message processing loop: {e}")
            raise

    async def _handle_message(self, msg: Any) -> None:
        """Handle a single ResourceConsumptionV1 message."""
        try:
            envelope = EventEnvelope[ResourceConsumptionV1].model_validate_json(msg.value)
            event = ResourceConsumptionV1.model_validate(envelope.data)

            # Delegate to credit manager
            result = await self.credit_manager.consume_credits(
                user_id=event.user_id,
                org_id=event.org_id,
                metric=event.resource_type,
                amount=event.quantity,
                batch_id=envelope.data.entity_id or None,
                correlation_id=str(envelope.correlation_id),
            )

            logger.info(
                "Processed ResourceConsumptionV1",
                extra={
                    "success": result.success,
                    "user_id": event.user_id,
                    "org_id": event.org_id,
                    "metric": event.resource_type,
                    "quantity": event.quantity,
                },
            )
        except Exception as e:
            logger.error(f"Error handling ResourceConsumptionV1 event: {e}", exc_info=True)
            raise
