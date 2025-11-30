"""Dishka DI configuration for Identity Service."""

from __future__ import annotations

# TYPE_CHECKING imports for domain handlers (avoid circular imports)
from datetime import timedelta

from aiohttp import ClientSession
from dishka import Provider, Scope, provide
from huleedu_service_libs.database import DatabaseMetrics, setup_database_monitoring
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.outbox.manager import OutboxManager
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from services.identity_service.config import Settings, settings
from services.identity_service.domain_handlers.authentication_handler import (
    AuthenticationHandler,
)
from services.identity_service.domain_handlers.password_reset_handler import (
    PasswordResetHandler,
)
from services.identity_service.domain_handlers.profile_handler import UserProfileHandler
from services.identity_service.domain_handlers.registration_handler import RegistrationHandler
from services.identity_service.domain_handlers.session_management_handler import (
    SessionManagementHandler,
)
from services.identity_service.domain_handlers.verification_handler import VerificationHandler
from services.identity_service.implementations.audit_logger_impl import AuditLoggerImpl
from services.identity_service.implementations.event_publisher_impl import (
    DefaultIdentityEventPublisher,
)
from services.identity_service.implementations.jwks_store import JwksStore
from services.identity_service.implementations.password_hasher_impl import (
    Argon2idPasswordHasher,
)
from services.identity_service.implementations.rate_limiter_impl import RateLimiterImpl
from services.identity_service.implementations.token_issuer_impl import DevTokenIssuer
from services.identity_service.implementations.token_issuer_rs256_impl import (
    Rs256TokenIssuer,
)
from services.identity_service.implementations.user_profile_repository_sqlalchemy_impl import (
    PostgresUserProfileRepo,
)
from services.identity_service.implementations.user_repository_sqlalchemy_impl import (
    PostgresSessionRepo,
    PostgresUserRepo,
)
from services.identity_service.implementations.user_session_repository_impl import (
    UserSessionRepositoryImpl,
)
from services.identity_service.kafka_consumer import IdentityKafkaConsumer
from services.identity_service.notification_orchestrator import NotificationOrchestrator
from services.identity_service.protocols import (
    AuditLoggerProtocol,
    IdentityEventPublisherProtocol,
    PasswordHasher,
    RateLimiterProtocol,
    SessionRepo,
    TokenIssuer,
    UserProfileRepositoryProtocol,
    UserRepo,
    UserSessionRepositoryProtocol,
)


class CoreProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        return settings

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        return REGISTRY

    @provide(scope=Scope.APP)
    async def provide_http_session(self) -> ClientSession:
        return ClientSession()

    @provide(scope=Scope.APP)
    async def provide_redis_client(self, settings: Settings) -> AtomicRedisClientProtocol:
        client = RedisClient(
            client_id=f"{settings.SERVICE_NAME}-redis",
            redis_url=settings.REDIS_URL,
        )
        await client.start()
        return client

    @provide(scope=Scope.APP)
    async def provide_database_engine(self, settings: Settings) -> AsyncEngine:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        return engine

    @provide(scope=Scope.APP)
    def provide_database_metrics(self, engine: AsyncEngine, settings: Settings) -> DatabaseMetrics:
        """Provide database metrics monitoring for identity service."""
        return setup_database_monitoring(engine=engine, service_name=settings.SERVICE_NAME)

    @provide(scope=Scope.APP)
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for outbox configuration."""
        return settings.SERVICE_NAME

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaBus:
        """Provide Kafka bus for event publishing."""
        kafka_bus = KafkaBus(
            client_id=f"{settings.SERVICE_NAME}_producer",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )
        await kafka_bus.start()
        return kafka_bus

    @provide(scope=Scope.APP)
    def provide_circuit_breaker(self) -> CircuitBreaker:
        """Provide circuit breaker for resilient operations."""
        return CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=timedelta(seconds=30),
            name="kafka_publisher_circuit",
        )

    @provide(scope=Scope.APP)
    def provide_kafka_publisher(
        self, kafka_bus: KafkaBus, circuit_breaker: CircuitBreaker
    ) -> KafkaPublisherProtocol:
        """Provide resilient Kafka publisher with circuit breaker pattern."""
        return ResilientKafkaPublisher(
            delegate=kafka_bus,
            circuit_breaker=circuit_breaker,
            fallback_handler=None,
            retry_interval=30,
        )


class IdentityImplementationsProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_jwks_store(self) -> JwksStore:
        return JwksStore()

    @provide(scope=Scope.APP)
    def provide_password_hasher(self) -> PasswordHasher:
        return Argon2idPasswordHasher()

    @provide(scope=Scope.APP)
    def provide_token_issuer(self, settings: Settings, jwks_store: JwksStore) -> TokenIssuer:
        # Production: RS256 with JWKS exposure
        if settings.is_production() and settings.JWT_RS256_PRIVATE_KEY_PATH:
            return Rs256TokenIssuer(jwks_store)
        # Development fallback: HS256-like dev tokens
        return DevTokenIssuer()

    @provide(scope=Scope.APP)
    def provide_user_repo(self, engine: AsyncEngine) -> UserRepo:
        return PostgresUserRepo(engine)

    @provide(scope=Scope.APP)
    def provide_session_repo(self, engine: AsyncEngine) -> SessionRepo:
        return PostgresSessionRepo(engine)

    @provide(scope=Scope.APP)
    def provide_outbox_manager(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> OutboxManager:
        """Provide outbox manager for reliable event publishing."""
        return OutboxManager(
            outbox_repository=outbox_repository,
            redis_client=redis_client,
            service_name=settings.SERVICE_NAME,
        )

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self, outbox_manager: OutboxManager, settings: Settings
    ) -> IdentityEventPublisherProtocol:
        return DefaultIdentityEventPublisher(outbox_manager, settings.SERVICE_NAME)

    @provide(scope=Scope.APP)
    def provide_user_profile_repository(self, engine: AsyncEngine) -> UserProfileRepositoryProtocol:
        return PostgresUserProfileRepo(engine)

    @provide(scope=Scope.REQUEST)
    def provide_profile_handler(
        self, repository: UserProfileRepositoryProtocol
    ) -> UserProfileHandler:
        return UserProfileHandler(repository)

    @provide(scope=Scope.APP)
    def provide_session_factory(self, engine: AsyncEngine) -> async_sessionmaker:
        """Provide SQLAlchemy async session factory."""
        return async_sessionmaker(engine, expire_on_commit=False)

    @provide(scope=Scope.APP)
    def provide_rate_limiter(self, redis_client: AtomicRedisClientProtocol) -> RateLimiterProtocol:
        """Provide rate limiter for security."""
        return RateLimiterImpl(redis_client)

    @provide(scope=Scope.APP)
    def provide_audit_logger(self, session_factory: async_sessionmaker) -> AuditLoggerProtocol:
        """Provide audit logger for security events."""
        return AuditLoggerImpl(session_factory)

    @provide(scope=Scope.APP)
    def provide_user_session_repository(
        self, session_factory: async_sessionmaker
    ) -> UserSessionRepositoryProtocol:
        """Provide user session repository with device tracking."""
        return UserSessionRepositoryImpl(session_factory)

    @provide(scope=Scope.APP)
    def provide_notification_orchestrator(
        self, outbox_manager: OutboxManager
    ) -> NotificationOrchestrator:
        """Provide notification orchestrator for email service integration."""
        return NotificationOrchestrator(outbox_manager)

    @provide(scope=Scope.APP)
    def provide_kafka_consumer(
        self,
        settings: Settings,
        notification_orchestrator: NotificationOrchestrator,
        redis_client: AtomicRedisClientProtocol,
    ) -> IdentityKafkaConsumer:
        """Provide Kafka consumer for internal Identity Service event processing."""
        return IdentityKafkaConsumer(settings, notification_orchestrator, redis_client)


class DomainHandlerProvider(Provider):
    """Provider for domain handler dependencies with REQUEST scope.

    All handlers are scoped to REQUEST for proper session management
    and to ensure each request gets fresh handler instances.
    """

    @provide(scope=Scope.REQUEST)
    def provide_authentication_handler(
        self,
        user_repo: UserRepo,
        token_issuer: TokenIssuer,
        password_hasher: PasswordHasher,
        session_repo: SessionRepo,
        user_session_repo: UserSessionRepositoryProtocol,
        event_publisher: IdentityEventPublisherProtocol,
        rate_limiter: RateLimiterProtocol,
        audit_logger: AuditLoggerProtocol,
    ) -> "AuthenticationHandler":
        """Provide authentication handler for login/logout/refresh operations."""
        from services.identity_service.domain_handlers.authentication_handler import (
            AuthenticationHandler,
        )

        return AuthenticationHandler(
            user_repo=user_repo,
            token_issuer=token_issuer,
            password_hasher=password_hasher,
            session_repo=session_repo,
            user_session_repo=user_session_repo,
            event_publisher=event_publisher,
            rate_limiter=rate_limiter,
            audit_logger=audit_logger,
        )

    @provide(scope=Scope.REQUEST)
    def provide_registration_handler(
        self,
        user_repo: UserRepo,
        password_hasher: PasswordHasher,
        event_publisher: IdentityEventPublisherProtocol,
        verification_handler: VerificationHandler,
        profile_repository: UserProfileRepositoryProtocol,
    ) -> "RegistrationHandler":
        """Provide registration handler for user registration operations."""
        from services.identity_service.domain_handlers.registration_handler import (
            RegistrationHandler,
        )

        return RegistrationHandler(
            user_repo=user_repo,
            password_hasher=password_hasher,
            event_publisher=event_publisher,
            verification_handler=verification_handler,
            profile_repository=profile_repository,
        )

    @provide(scope=Scope.REQUEST)
    def provide_verification_handler(
        self,
        user_repo: UserRepo,
        event_publisher: IdentityEventPublisherProtocol,
    ) -> "VerificationHandler":
        """Provide verification handler for email verification operations."""
        from services.identity_service.domain_handlers.verification_handler import (
            VerificationHandler,
        )

        return VerificationHandler(
            user_repo=user_repo,
            event_publisher=event_publisher,
        )

    @provide(scope=Scope.REQUEST)
    def provide_password_reset_handler(
        self,
        user_repo: UserRepo,
        password_hasher: PasswordHasher,
        event_publisher: IdentityEventPublisherProtocol,
        audit_logger: AuditLoggerProtocol,
    ) -> "PasswordResetHandler":
        """Provide password reset handler for password reset operations."""
        from services.identity_service.domain_handlers.password_reset_handler import (
            PasswordResetHandler,
        )

        return PasswordResetHandler(
            user_repo=user_repo,
            password_hasher=password_hasher,
            event_publisher=event_publisher,
            audit_logger=audit_logger,
        )

    @provide(scope=Scope.REQUEST)
    def provide_session_management_handler(
        self,
        user_session_repo: UserSessionRepositoryProtocol,
        audit_logger: AuditLoggerProtocol,
    ) -> "SessionManagementHandler":
        """Provide session management handler for session operations."""
        from services.identity_service.domain_handlers.session_management_handler import (
            SessionManagementHandler,
        )

        return SessionManagementHandler(
            user_session_repo=user_session_repo,
            audit_logger=audit_logger,
        )
