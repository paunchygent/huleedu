"""Main application entry point for Result Aggregator Service."""
import asyncio
import signal
from contextlib import asynccontextmanager

import dotenv
from dishka import make_async_container
from dishka.integrations.quart import setup_dishka
from quart import Quart
from quart_cors import cors

from huleedu_service_libs.logging_utils import create_service_logger

# Load environment variables before importing anything else
dotenv.load_dotenv()

# Import after environment is loaded
from .api.health_routes import health_bp
from .api.query_routes import query_bp
from .config import Settings
from .di import (
    CoreInfrastructureProvider,
    DatabaseProvider,
    RepositoryProvider,
    ServiceProvider
)
from .kafka_consumer import ResultAggregatorKafkaConsumer
from .startup_setup import setup_metrics_endpoint


logger = create_service_logger("result_aggregator.app")


async def create_app() -> Quart:
    """Create and configure the Quart application."""
    app = Quart(__name__)
    
    # Enable CORS for internal services
    app = cors(app, allow_origin=["http://localhost:*"])
    
    # Create DI container
    container = make_async_container(
        CoreInfrastructureProvider(),
        DatabaseProvider(),
        RepositoryProvider(),
        ServiceProvider()
    )
    
    # Setup Dishka integration
    setup_dishka(container, app)
    
    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(query_bp)
    
    # Store container reference
    app.container = container
    
    # Setup metrics endpoint
    setup_metrics_endpoint(app)
    
    return app


@asynccontextmanager
async def managed_kafka_consumer(app: Quart):
    """Manage Kafka consumer lifecycle."""
    async with app.container() as request_container:
        consumer = await request_container.get(ResultAggregatorKafkaConsumer)
        
        # Start consumer in background
        consumer_task = asyncio.create_task(consumer.start())
        
        try:
            yield
        finally:
            # Stop consumer gracefully
            await consumer.stop()
            await consumer_task


async def main():
    """Main entry point for the service."""
    try:
        # Create app
        app = await create_app()
        
        # Get settings
        async with app.container() as request_container:
            settings = await request_container.get(Settings)
        
        # Setup signal handlers
        shutdown_event = asyncio.Event()
        
        def signal_handler(signum, _frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start services
        async with managed_kafka_consumer(app):
            # Run Quart app
            config = app.make_config()
            config.bind = [f"{settings.HOST}:{settings.PORT}"]
            
            logger.info(
                "Result Aggregator Service started",
                host=settings.HOST,
                port=settings.PORT,
                metrics_port=settings.METRICS_PORT
            )
            
            # Run until shutdown
            await app.run_task(config=config, shutdown_trigger=shutdown_event.wait)
            
    except Exception as e:
        logger.critical("Failed to start Result Aggregator Service", error=str(e), exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())