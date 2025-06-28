"""Startup setup utilities for Result Aggregator Service."""
from prometheus_client import start_http_server
from quart import Quart

from huleedu_service_libs.logging_utils import create_service_logger

from .config import Settings


logger = create_service_logger("result_aggregator.startup")


def setup_metrics_endpoint(app: Quart) -> None:
    """Setup Prometheus metrics endpoint on separate port."""
    
    @app.before_serving
    async def start_metrics_server():
        """Start metrics server before serving."""
        # Get settings from app config or use defaults
        settings = Settings()
        
        # Start Prometheus metrics server
        start_http_server(settings.METRICS_PORT)
        logger.info(f"Metrics server started on port {settings.METRICS_PORT}")


def setup_signal_handlers(app: Quart) -> None:
    """Setup graceful shutdown signal handlers."""
    import signal
    
    async def graceful_shutdown():
        """Perform graceful shutdown."""
        logger.info("Initiating graceful shutdown...")
        
        # Close container resources
        if hasattr(app, 'container'):
            await app.container.close()
            
        logger.info("Graceful shutdown complete")
    
    def signal_handler(signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        app.shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)