"""Main application entry point for Result Aggregator Service."""

from __future__ import annotations

import asyncio

import dotenv
from dishka import make_async_container
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from huleedu_service_libs.quart_app import HuleEduApp
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import AsyncEngine

# Load environment variables before importing anything else
dotenv.load_dotenv()

# Import after environment is loaded

from services.result_aggregator_service.api.health_routes import health_bp
from services.result_aggregator_service.api.query_routes import query_bp
from services.result_aggregator_service.config import Settings, settings
from services.result_aggregator_service.di import (
    CoreInfrastructureProvider,
    DatabaseProvider,
    ServiceProvider,
)
from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer
from services.result_aggregator_service.startup_setup import initialize_tracing

# Configure centralized structured logging before creating logger
configure_service_logging("result_aggregator_service", log_level=settings.LOG_LEVEL)

logger = create_service_logger("result_aggregator.app")


def create_app() -> HuleEduApp:
    """Create and configure the Quart application."""
    app = HuleEduApp(__name__)

    # Initialize relay worker attributes
    app.relay_worker = None
    app.relay_task = None

    # CORS is handled by API Gateway - internal services don't need it

    # IMMEDIATE container initialization - satisfies non-optional contract
    app.container = make_async_container(
        CoreInfrastructureProvider(), DatabaseProvider(), ServiceProvider(), OutboxProvider()
    )

    # IMMEDIATE database engine initialization - satisfies non-optional contract
    # We need to get the engine from the container immediately
    import asyncio

    loop = asyncio.get_event_loop()

    async def get_engine() -> AsyncEngine:
        async with app.container() as request_container:
            return await request_container.get(AsyncEngine)

    app.database_engine = loop.run_until_complete(get_engine())

    # Use guaranteed container
    QuartDishka(app=app, container=app.container)

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(query_bp)

    return app


app = create_app()


@app.before_serving
async def startup() -> None:
    """Initialize services on startup."""
    try:
        # Initialize tracing
        await initialize_tracing(app)

        # Setup Kafka consumer
        async with app.container() as request_container:
            settings = await request_container.get(Settings)

            # Get Kafka consumer and relay worker
            consumer = await request_container.get(ResultAggregatorKafkaConsumer)
            app.relay_worker = await request_container.get(EventRelayWorker)

        # Start consumer in background
        app.consumer_task = asyncio.create_task(consumer.start())

        # Start outbox relay worker
        assert app.relay_worker is not None, "Outbox relay worker must be initialized"
        app.relay_task = asyncio.create_task(app.relay_worker.start())
        logger.info("Outbox relay worker: running")

        logger.info(
            "Result Aggregator Service started",
            host=settings.HOST,
            port=settings.PORT,
        )
        logger.info("Kafka consumer: running")
    except Exception as e:
        logger.critical("Failed to start services", error=str(e), exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown services."""
    try:
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

        # Stop Kafka consumer
        if app.consumer_task is not None:
            logger.info("Stopping Kafka consumer...")
            async with app.container() as request_container:
                consumer = await request_container.get(ResultAggregatorKafkaConsumer)
            await consumer.stop()
            await app.consumer_task

        logger.info("Result Aggregator Service shutdown complete")
    except Exception as e:
        logger.error("Error during shutdown", error=str(e), exc_info=True)


if __name__ == "__main__":
    # Get settings from container
    settings = Settings()
    app.run(debug=False, host=settings.HOST, port=settings.PORT)
