"""Dependency injection providers for Email Service.

This module provides Dishka container configuration with proper scoping
following established patterns for APP and REQUEST scopes.
"""

from __future__ import annotations

from datetime import timedelta

from aiokafka.errors import KafkaError
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol, RedisClient
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.email_service.config import Settings
from services.email_service.event_processor import EmailEventProcessor
from services.email_service.implementations.outbox_manager import OutboxManager
from services.email_service.kafka_consumer import EmailKafkaConsumer
from services.email_service.metrics import setup_email_service_database_monitoring
from services.email_service.protocols import EmailProvider, EmailRepository, TemplateRenderer


class CoreProvider(Provider):
    """Core infrastructure providers with proper scoping."""

    scope = Scope.APP

    @provide
    def provide_settings(self) -> Settings:
        """Provide service settings as singleton."""
        return Settings()

    @provide
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for outbox and metrics."""
        return settings.SERVICE_NAME

    @provide
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide Prometheus metrics registry."""
        return REGISTRY

    @provide
    def provide_database_metrics(self, engine: AsyncEngine, settings: Settings) -> DatabaseMetrics:
        """Provide database metrics monitoring for Email Service."""
        return setup_email_service_database_monitoring(engine=engine, service_name="email_service")

    @provide
    def provide_circuit_breaker_registry(self, settings: Settings) -> CircuitBreakerRegistry:
        """Provide centralized circuit breaker registry."""
        registry = CircuitBreakerRegistry()

        # Only register circuit breakers if enabled
        if settings.CIRCUIT_BREAKER_ENABLED:
            # Future: Add more circuit breakers here as needed
            pass

        return registry

    @provide
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        """Provide Redis client for idempotency and caching."""
        client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await client.start()
        return client

    @provide
    async def provide_kafka_publisher(
        self,
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> KafkaPublisherProtocol:
        """Provide Kafka publisher for event publishing with optional circuit breaker protection."""
        # Create base KafkaBus instance
        base_kafka_bus = KafkaBus(
            client_id=settings.PRODUCER_CLIENT_ID_EMAIL,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )

        # Wrap with circuit breaker protection if enabled
        kafka_publisher: KafkaPublisherProtocol
        if settings.CIRCUIT_BREAKER_ENABLED:
            kafka_circuit_breaker = CircuitBreaker(
                name=f"{settings.SERVICE_NAME}.kafka_producer",
                failure_threshold=settings.KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                recovery_timeout=timedelta(seconds=settings.KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT),
                success_threshold=settings.KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
                expected_exception=KafkaError,
            )
            circuit_breaker_registry.register("kafka_producer", kafka_circuit_breaker)

            # Create resilient wrapper using composition
            kafka_publisher = ResilientKafkaPublisher(
                delegate=base_kafka_bus,
                circuit_breaker=kafka_circuit_breaker,
                retry_interval=30,
            )
        else:
            # Use base KafkaBus without circuit breaker
            kafka_publisher = base_kafka_bus

        await kafka_publisher.start()
        return kafka_publisher

    @provide
    def provide_session_maker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """Provide SQLAlchemy session maker."""
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )


class ImplementationProvider(Provider):
    """Implementation providers for protocol contracts."""

    @provide(scope=Scope.APP)
    def provide_email_repository(
        self,
        engine: AsyncEngine,
        database_metrics: DatabaseMetrics,
    ) -> EmailRepository:
        """Provide email repository implementation."""
        from services.email_service.implementations.repository_impl import (
            PostgreSQLEmailRepository,
        )

        return PostgreSQLEmailRepository(engine, database_metrics)

    @provide(scope=Scope.APP)
    def provide_template_renderer(self, settings: Settings) -> TemplateRenderer:
        """Provide template renderer implementation."""
        from services.email_service.implementations.template_renderer_impl import (
            JinjaTemplateRenderer,
        )

        return JinjaTemplateRenderer(settings.TEMPLATE_PATH)

    @provide(scope=Scope.APP)
    def provide_email_provider(self, settings: Settings) -> EmailProvider:
        """Provide email provider implementation based on configuration."""
        if settings.EMAIL_PROVIDER == "mock":
            from services.email_service.implementations.provider_mock_impl import (
                MockEmailProvider,
            )

            return MockEmailProvider(settings)

        elif settings.EMAIL_PROVIDER == "smtp":
            # Validate SMTP configuration before creating provider
            if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
                raise ValueError(
                    "SMTP provider requires EMAIL_SMTP_USERNAME and EMAIL_SMTP_PASSWORD "
                    "environment variables to be set"
                )

            from services.email_service.implementations.provider_smtp_impl import (
                SMTPEmailProvider,
            )

            return SMTPEmailProvider(settings)

        else:
            # Other providers not yet implemented
            raise ValueError(
                f"Email provider '{settings.EMAIL_PROVIDER}' is not yet implemented. "
                f"Available providers: 'mock', 'smtp'"
            )


class ServiceProvider(Provider):
    """Service-specific providers for business logic components."""

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide outbox manager for transactional event publishing."""
        return OutboxManager(outbox_repository, redis_client, settings)

    @provide(scope=Scope.APP)
    def provide_event_processor(
        self,
        email_repository: EmailRepository,
        template_renderer: TemplateRenderer,
        email_provider: EmailProvider,
        outbox_manager: OutboxManager,  # Provided by above method
        settings: Settings,
    ) -> EmailEventProcessor:
        """Provide email event processor."""
        return EmailEventProcessor(
            repository=email_repository,
            template_renderer=template_renderer,
            email_provider=email_provider,
            outbox_manager=outbox_manager,
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def provide_kafka_consumer(
        self,
        settings: Settings,
        event_processor: EmailEventProcessor,
        redis_client: AtomicRedisClientProtocol,
    ) -> EmailKafkaConsumer:
        """Provide Kafka consumer for email processing."""
        return EmailKafkaConsumer(
            settings=settings,
            event_processor=event_processor,
            redis_client=redis_client,
        )


class EmailServiceProvider(Provider):
    """Main provider combining all email service dependencies."""

    def __init__(self, engine: AsyncEngine):
        super().__init__()
        self.engine = engine

    @provide(scope=Scope.APP)
    def provide_engine(self) -> AsyncEngine:
        """Provide database engine from app initialization."""
        return self.engine
