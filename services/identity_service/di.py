"""Dishka DI configuration for Identity Service."""

from __future__ import annotations

from aiohttp import ClientSession
from dishka import Provider, Scope, provide
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from prometheus_client import REGISTRY, CollectorRegistry
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.identity_service.config import Settings, settings
from services.identity_service.domain_handlers.profile_handler import UserProfileHandler
from services.identity_service.implementations.event_publisher_impl import (
    DefaultIdentityEventPublisher,
)
from services.identity_service.implementations.jwks_store import JwksStore
from services.identity_service.implementations.outbox_manager import OutboxManager
from services.identity_service.implementations.password_hasher_impl import (
    Argon2idPasswordHasher,
)
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
from services.identity_service.protocols import (
    IdentityEventPublisherProtocol,
    PasswordHasher,
    SessionRepo,
    TokenIssuer,
    UserProfileRepositoryProtocol,
    UserRepo,
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
        engine = create_async_engine(settings.database_url, echo=False)
        return engine

    @provide(scope=Scope.APP)
    def provide_service_name(self, settings: Settings) -> str:
        """Provide service name for outbox configuration."""
        return settings.SERVICE_NAME


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
        if str(settings.ENVIRONMENT) == "production" and settings.JWT_RS256_PRIVATE_KEY_PATH:
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
        """Provide outbox manager for TRUE OUTBOX PATTERN."""
        return OutboxManager(outbox_repository, redis_client, settings)

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
