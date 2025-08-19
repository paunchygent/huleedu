from __future__ import annotations

import asyncio

from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from huleedu_service_libs.outbox import EventRelayWorker
from huleedu_service_libs.quart_app import HuleEduApp
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import create_async_engine

import services.class_management_service.startup_setup as startup_setup
from services.class_management_service.api.batch_routes import batch_bp
from services.class_management_service.api.class_routes import class_bp
from services.class_management_service.api.health_routes import health_bp
from services.class_management_service.api.internal_routes import bp as internal_bp
from services.class_management_service.api.student_routes import student_bp
from services.class_management_service.config import settings
from services.class_management_service.di import create_container
from services.class_management_service.implementations.association_timeout_monitor import (
    AssociationTimeoutMonitor,
)
from services.class_management_service.kafka_consumer import ClassManagementKafkaConsumer


# Extended app type for type safety
class ClassManagementApp(HuleEduApp):
    """Extended HuleEdu app with Class Management specific attributes."""

    timeout_monitor: AssociationTimeoutMonitor | None = None


# Configure logging first
configure_service_logging("class-management-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("cms.app")


def create_app() -> ClassManagementApp:
    """Create and configure the Class Management Service app with guaranteed infrastructure."""
    app = ClassManagementApp(__name__)

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

    # Initialize tracing early, before blueprint registration
    tracer = init_tracing("class_management_service")
    app.extensions = {"tracer": tracer}
    setup_tracing_middleware(app, tracer)

    # Integrate DI with Quart (must be done before registering blueprints)
    QuartDishka(app=app, container=app.container)

    # Optional service-specific attributes for Kafka consumer and outbox relay
    app.consumer_task = None
    app.kafka_consumer = None
    app.relay_worker = None
    app.relay_task = None
    app.timeout_monitor = None

    # Register Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(class_bp, url_prefix="/v1/classes")
    app.register_blueprint(student_bp, url_prefix="/v1/classes")
    app.register_blueprint(batch_bp, url_prefix="/v1/batches")
    app.register_blueprint(internal_bp)  # Internal routes include /internal/v1 prefix

    return app


# Create the app instance
app = create_app()


@app.before_serving
async def startup() -> None:
    """Application startup tasks including Kafka consumer."""
    try:
        # Initialize database schema
        await startup_setup.initialize_database_schema(app)

        # Setup metrics middleware
        setup_standard_service_metrics_middleware(app, "class_management")

        # Get Kafka consumer, relay worker, and timeout monitor from DI container
        async with app.container() as request_container:
            app.kafka_consumer = await request_container.get(ClassManagementKafkaConsumer)
            app.relay_worker = await request_container.get(EventRelayWorker)
            app.timeout_monitor = await request_container.get(AssociationTimeoutMonitor)

        # Start consumer as background task
        assert app.kafka_consumer is not None, "Kafka consumer must be initialized"
        app.consumer_task = asyncio.create_task(app.kafka_consumer.start_consumer())

        # Start outbox relay worker
        assert app.relay_worker is not None, "Outbox relay worker must be initialized"
        app.relay_task = asyncio.create_task(app.relay_worker.start())

        # Start timeout monitor
        assert app.timeout_monitor is not None, "Timeout monitor must be initialized"
        await app.timeout_monitor.start()

        logger.info("Class Management Service started successfully")
        logger.info("Health endpoint: /healthz")
        logger.info("Metrics endpoint: /metrics")
        logger.info("API endpoints: /v1/classes/, /v1/batches/")
        logger.info("Kafka consumer: running")
        logger.info("Outbox relay worker: running")
        logger.info("Timeout monitor: running")

    except Exception as e:
        logger.critical(f"Failed to start Class Management Service: {e}", exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Application cleanup tasks including Kafka consumer shutdown."""
    try:
        # Stop Kafka consumer
        if app.kafka_consumer:
            logger.info("Stopping Kafka consumer...")
            await app.kafka_consumer.stop_consumer()

        # Cancel consumer task
        if app.consumer_task and not app.consumer_task.done():
            app.consumer_task.cancel()
            try:
                await app.consumer_task
            except asyncio.CancelledError:
                logger.info("Consumer task cancelled successfully")

        # Stop outbox relay worker
        if app.relay_worker:
            logger.info("Stopping outbox relay worker...")
            await app.relay_worker.stop()

        # Cancel relay task
        if app.relay_task and not app.relay_task.done():
            app.relay_task.cancel()
            try:
                await app.relay_task
            except asyncio.CancelledError:
                logger.info("Relay task cancelled successfully")

        # Stop timeout monitor
        if app.timeout_monitor:
            logger.info("Stopping timeout monitor...")
            await app.timeout_monitor.stop()

        # Additional cleanup
        await startup_setup.shutdown_services()
        await app.container.close()

        logger.info("Class Management Service shutdown complete")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


if __name__ == "__main__":
    app.run(host=settings.HOST, port=settings.PORT)
