from __future__ import annotations

from typing import AsyncGenerator

# Local application imports
from config import Settings, settings

# Standard library imports
# Third-party imports
from dishka import Provider, Scope, provide
from huleedu_service_libs.kafka_client import KafkaBus
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from services.class_management_service.implementations.class_management_service_impl import (
    ClassManagementServiceImpl,
)
from services.class_management_service.implementations.class_repository_mock_impl import (
    MockClassRepositoryImpl,
)
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.implementations.event_publisher_impl import (
    DefaultClassEventPublisherImpl,
)
from services.class_management_service.models_db import Student, UserClass
from services.class_management_service.protocols import (
    ClassEventPublisherProtocol,
    ClassManagementServiceProtocol,
    ClassRepositoryProtocol,
)


class DatabaseProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_engine(self, settings: Settings) -> AsyncEngine:
        return create_async_engine(settings.DATABASE_URL)

    @provide(scope=Scope.APP)
    def provide_sessionmaker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(engine, expire_on_commit=False)

    @provide(scope=Scope.REQUEST)
    async def provide_session(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> AsyncGenerator[AsyncSession, None]:
        async with sessionmaker() as session:
            yield session


class RepositoryProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_class_repository(
        self, settings: Settings, session: AsyncSession
    ) -> ClassRepositoryProtocol[UserClass, Student]:
        if settings.ENVIRONMENT == "test" or settings.USE_MOCK_REPOSITORY:
            return MockClassRepositoryImpl[UserClass, Student]()
        return PostgreSQLClassRepositoryImpl[UserClass, Student](session)


class ServiceProvider(Provider):
    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        return settings

    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaBus:
        kafka_bus = KafkaBus(
            client_id=f"{settings.SERVICE_NAME}-producer",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        )
        await kafka_bus.start()
        return kafka_bus

    @provide(scope=Scope.APP)
    def provide_event_publisher(
        self, kafka_bus: KafkaBus
    ) -> ClassEventPublisherProtocol:
        return DefaultClassEventPublisherImpl(kafka_bus)

    @provide(scope=Scope.REQUEST)
    def provide_class_management_service(
        self,
        repo: ClassRepositoryProtocol[UserClass, Student],
        publisher: ClassEventPublisherProtocol,
    ) -> ClassManagementServiceProtocol[UserClass, Student]:
        return ClassManagementServiceImpl[UserClass, Student](
            repo=repo,
            event_publisher=publisher,
            user_class_type=UserClass,
            student_type=Student,
        )
