from __future__ import annotations

from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.quart_app import HuleEduApp
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import create_async_engine

import services.class_management_service.startup_setup as startup_setup
from services.class_management_service.api.class_routes import class_bp
from services.class_management_service.api.health_routes import health_bp
from services.class_management_service.api.student_routes import student_bp
from services.class_management_service.config import settings
from services.class_management_service.di import create_container

# Configure logging first
configure_service_logging("class-management-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("cms.app")


def create_app() -> HuleEduApp:
    """Create and configure the Class Management Service app with guaranteed infrastructure."""
    app = HuleEduApp(__name__)

    # IMMEDIATE initialization - satisfies non-optional contract
    app.container = create_container()

    # Set database engine immediately to satisfy non-optional contract
    if not settings.DATABASE_URL:
        raise ValueError("DATABASE_URL is required but not configured")

    app.database_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
    )

    # Integrate DI with Quart (must be done before registering blueprints)
    QuartDishka(app=app, container=app.container)

    # Register Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(class_bp, url_prefix="/v1/classes")
    app.register_blueprint(student_bp, url_prefix="/v1/classes")

    return app


# Create the app instance
app = create_app()


@app.before_serving
async def startup() -> None:
    """Initialize database schema before the app starts serving."""
    await startup_setup.initialize_database_schema(app)


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown services."""
    await startup_setup.shutdown_services()
    await app.container.close()


if __name__ == "__main__":
    app.run(host=settings.HOST, port=settings.PORT)
