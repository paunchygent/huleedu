

from dishka import make_async_container
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Quart
from quart_dishka import QuartDishka

from services.class_management_service.config import Settings
from services.class_management_service.di import (
    DatabaseProvider,
    RepositoryProvider,
    ServiceProvider,
)

logger = create_service_logger("cms.startup")


async def initialize_services(app: Quart, settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, and other services."""
    try:
        container = make_async_container(
            DatabaseProvider(),
            RepositoryProvider(),
            ServiceProvider(),
        )
        QuartDishka(app=app, container=container)

        # In a real application, you would initialize the DB schema here
        # async with container() as request_container:
        #     engine = await request_container.get(Engine)
        #     async with engine.begin() as conn:
        #         await conn.run_sync(Base.metadata.create_all)

        logger.info("Class Management Service startup completed successfully")
    except Exception as e:
        logger.critical(f"Failed to start Class Management Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown all services."""
    logger.info("Class Management Service shutdown completed")
