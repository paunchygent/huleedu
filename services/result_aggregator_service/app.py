"""Main application entry point for Result Aggregator Service."""

from __future__ import annotations

import asyncio
from typing import Optional

import dotenv
from dishka import AsyncContainer, make_async_container
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Quart
from quart_dishka import QuartDishka

# Load environment variables before importing anything else
dotenv.load_dotenv()

# Import after environment is loaded
from services.result_aggregator_service.api.health_routes import health_bp
from services.result_aggregator_service.api.query_routes import query_bp
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.di import (
    CoreInfrastructureProvider,
    DatabaseProvider,
    ServiceProvider,
)
from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer
from services.result_aggregator_service.protocols import BatchRepositoryProtocol
from services.result_aggregator_service.startup_setup import setup_metrics_endpoint

logger = create_service_logger("result_aggregator.app")


class ResultAggregatorApp(Quart):
    """Custom Quart app with typed application-specific attributes."""

    container: AsyncContainer
    consumer_task: Optional[asyncio.Task[None]]


def create_app() -> ResultAggregatorApp:
    """Create and configure the Quart application."""
    app = ResultAggregatorApp(__name__)

    # CORS is handled by API Gateway - internal services don't need it

    # Create DI container
    container = make_async_container(
        CoreInfrastructureProvider(), DatabaseProvider(), ServiceProvider()
    )

    # Setup Dishka integration
    QuartDishka(app=app, container=container)

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(query_bp)

    # Store container reference
    app.container = container

    # Setup metrics endpoint
    setup_metrics_endpoint(app)

    return app


app = create_app()


@app.before_serving
async def startup() -> None:
    """Initialize services on startup."""
    try:
        # Initialize database schema
        async with app.container() as request_container:
            settings = await request_container.get(Settings)
            batch_repository = await request_container.get(BatchRepositoryProtocol)
            await batch_repository.initialize_schema()
            logger.info("Database schema initialized")

            # Get Kafka consumer
            consumer = await request_container.get(ResultAggregatorKafkaConsumer)

        # Start consumer in background
        app.consumer_task = asyncio.create_task(consumer.start())

        logger.info(
            "Result Aggregator Service started",
            host=settings.HOST,
            port=settings.PORT,
            metrics_port=settings.METRICS_PORT,
        )
    except Exception as e:
        logger.critical("Failed to start services", error=str(e), exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown services."""
    try:
        # Stop Kafka consumer
        if hasattr(app, "consumer_task") and app.consumer_task is not None:
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
