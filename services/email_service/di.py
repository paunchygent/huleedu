"""Dependency injection providers for Email Service.

This module provides Dishka container configuration with proper scoping
following established patterns for APP and REQUEST scopes.
"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol, RedisClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.email_service.config import Settings
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
    def provide_session_maker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """Provide SQLAlchemy session maker."""
        return async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )


class ImplementationProvider(Provider):
    """Implementation providers for protocol contracts."""
    
    @provide(scope=Scope.REQUEST)
    def provide_email_repository(
        self, 
        session_maker: async_sessionmaker[AsyncSession],
    ) -> EmailRepository:
        """Provide email repository implementation."""
        from services.email_service.implementations.repository_impl import (
            EmailRepositoryImpl,
        )
        
        return EmailRepositoryImpl(session_maker)
    
    @provide(scope=Scope.APP)
    def provide_template_renderer(self, settings: Settings) -> TemplateRenderer:
        """Provide template renderer implementation."""
        from services.email_service.implementations.template_renderer_impl import (
            Jinja2TemplateRenderer,
        )
        
        return Jinja2TemplateRenderer(settings)
    
    @provide(scope=Scope.APP)
    def provide_email_provider(self, settings: Settings) -> EmailProvider:
        """Provide email provider implementation based on configuration."""
        if settings.EMAIL_PROVIDER == "mock":
            from services.email_service.implementations.provider_mock_impl import (
                MockEmailProvider,
            )
            return MockEmailProvider(settings)
        elif settings.EMAIL_PROVIDER == "sendgrid":
            from services.email_service.implementations.provider_sendgrid_impl import (
                SendGridEmailProvider,
            )
            return SendGridEmailProvider(settings)
        elif settings.EMAIL_PROVIDER == "ses":
            from services.email_service.implementations.provider_ses_impl import (
                SESEmailProvider,
            )
            return SESEmailProvider(settings)
        else:
            raise ValueError(f"Unknown email provider: {settings.EMAIL_PROVIDER}")


class ServiceProvider(Provider):
    """Service-specific providers for business logic components."""
    
    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ):
        """Provide outbox manager for transactional event publishing."""
        from services.email_service.implementations.outbox_manager import OutboxManager
        
        return OutboxManager(outbox_repository, redis_client, settings)
    
    @provide(scope=Scope.REQUEST)
    def provide_event_processor(
        self,
        email_repository: EmailRepository,
        template_renderer: TemplateRenderer,
        email_provider: EmailProvider,
        outbox_manager,  # Provided by above method
        settings: Settings,
    ):
        """Provide email event processor."""
        from services.email_service.event_processor import EmailEventProcessor
        
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
        kafka_bus: KafkaBus,
        redis_client: RedisClient,
        settings: Settings,
    ):
        """Provide Kafka consumer for email processing."""
        from services.email_service.kafka_consumer import EmailKafkaConsumer
        
        return EmailKafkaConsumer(
            kafka_bus=kafka_bus,
            redis_client=redis_client,
            settings=settings,
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