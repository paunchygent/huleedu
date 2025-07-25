"""
Dishka providers for the Transactional Outbox Pattern.

This module provides dependency injection providers for the outbox pattern
components, following HuleEdu's established DI patterns with Dishka.
"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine

from huleedu_service_libs.protocols import KafkaPublisherProtocol

from .protocols import EventTypeMapperProtocol, OutboxRepositoryProtocol
from .relay import EventRelayWorker, OutboxSettings
from .repository import PostgreSQLOutboxRepository


class OutboxProvider(Provider):
    """
    Dishka provider for Transactional Outbox Pattern components.

    This provider creates all necessary components for implementing the
    outbox pattern in a service. Services need to provide:
    - AsyncEngine: Database engine for outbox storage
    - KafkaPublisherProtocol: Kafka client for publishing events
    - OutboxSettings: Configuration for the relay worker
    - service_name (str): Name of the service for event metadata

    Example usage in service DI:
        from huleedu_service_libs.outbox import OutboxProvider

        container = make_async_container(
            CoreInfrastructureProvider(),
            ServiceImplementationsProvider(),
            OutboxProvider(),
        )
    """

    @provide(scope=Scope.APP)
    def provide_outbox_settings(self) -> OutboxSettings:
        """
        Provide default outbox settings.

        Services can override this provider to customize outbox behavior
        such as poll intervals, batch sizes, and retry settings.

        Returns:
            Default outbox configuration
        """
        return OutboxSettings(
            poll_interval_seconds=5.0,
            batch_size=100,
            max_retries=5,
            error_retry_interval_seconds=30.0,
            enable_metrics=True,
        )

    @provide(scope=Scope.APP)
    def provide_outbox_repository(
        self,
        engine: AsyncEngine,
        service_name: str,
        settings: OutboxSettings,
    ) -> OutboxRepositoryProtocol:
        """
        Provide PostgreSQL implementation of the outbox repository.

        Args:
            engine: SQLAlchemy async engine (provided by service)
            service_name: Name of the service for metric labels
            settings: Outbox settings including metrics enablement

        Returns:
            Outbox repository protocol implementation
        """
        return PostgreSQLOutboxRepository(
            engine=engine,
            service_name=service_name,
            enable_metrics=settings.enable_metrics,
        )

    @provide(scope=Scope.APP)
    def provide_event_type_mapper(self) -> EventTypeMapperProtocol | None:
        """
        Provide default event type mapper (None for direct topic usage).

        Services can override this to provide custom event type mapping.
        When None, the relay worker uses topics directly from outbox records.

        Returns:
            None (default - use topics directly)
        """
        return None

    @provide(scope=Scope.APP)
    def provide_event_relay_worker(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        kafka_bus: KafkaPublisherProtocol,
        settings: OutboxSettings,
        service_name: str,
        event_mapper: EventTypeMapperProtocol | None = None,
    ) -> EventRelayWorker:
        """
        Provide the event relay worker for processing outbox events.

        Args:
            outbox_repository: Repository for outbox operations
            kafka_bus: Kafka publisher for sending events
            settings: Worker configuration settings
            service_name: Name of the service (provided by service)
            event_mapper: Optional mapper for event type to topic mapping

        Returns:
            Configured event relay worker
        """
        return EventRelayWorker(
            outbox_repository=outbox_repository,
            kafka_bus=kafka_bus,
            settings=settings,
            service_name=service_name,
            event_mapper=event_mapper,
        )


class OutboxSettingsProvider(Provider):
    """
    Separate provider for services that need custom outbox settings.

    Services can create an instance of this provider with custom settings
    instead of overriding the default provider method.

    Example:
        custom_settings = OutboxSettings(
            poll_interval_seconds=2.0,
            batch_size=50,
            max_retries=10,
        )

        container = make_async_container(
            CoreInfrastructureProvider(),
            OutboxSettingsProvider(custom_settings),
            OutboxProvider(),
        )
    """

    def __init__(self, settings: OutboxSettings) -> None:
        """
        Initialize with custom outbox settings.

        Args:
            settings: Custom outbox configuration
        """
        super().__init__()
        self._settings = settings

    @provide(scope=Scope.APP)
    def provide_outbox_settings(self) -> OutboxSettings:
        """Provide the custom outbox settings."""
        return self._settings
