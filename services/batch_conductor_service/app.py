"""
HuleEdu Batch Conductor Service Application.

This module implements the Batch Conductor Service internal HTTP API using Quart framework.
The service provides pipeline dependency resolution and batch state analysis for BOS.
"""

from __future__ import annotations

import asyncio

from quart_dishka import QuartDishka

from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from huleedu_service_libs.metrics_middleware import setup_metrics_middleware
from huleedu_service_libs.quart_app import HuleEduApp
from services.batch_conductor_service.api.health_routes import health_bp
from services.batch_conductor_service.api.pipeline_routes import pipeline_bp
from services.batch_conductor_service.config import settings
from services.batch_conductor_service.startup_setup import (
    create_container,
    initialize_metrics,
    shutdown_services,
)

# Configure structured logging for the service
configure_service_logging("batch-conductor-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("bcs.app")


async def _start_kafka_consumer_with_monitoring(app) -> None:
    """Start Kafka consumer with automatic restart monitoring."""

    async def start_consumer_task():
        """Start the consumer task with proper error handling."""
        try:
            await app.kafka_consumer.start_consuming()
        except Exception as e:
            logger.error(f"Kafka consumer task failed: {e}", exc_info=True)
            # Don't re-raise - let the monitor handle restart

    # Start the initial consumer task
    app.consumer_task = asyncio.create_task(start_consumer_task())

    # Start the monitor task
    app.consumer_monitor_task = asyncio.create_task(_monitor_kafka_consumer(app))


async def _monitor_kafka_consumer(app) -> None:
    """Monitor Kafka consumer and restart if it fails."""
    restart_lock = asyncio.Lock()
    restart_count = 0
    max_restart_attempts = 20  # Allow many restarts over time
    restart_delay = 10.0  # Start with 10 seconds between restarts
    max_restart_delay = 300.0  # Max 5 minutes between restarts

    logger.info("BCS Kafka consumer monitor started")

    while not getattr(app, "_consumer_shutdown_requested", False):
        try:
            # Wait a bit before checking
            await asyncio.sleep(5.0)

            # Check if shutdown was requested
            if getattr(app, "_consumer_shutdown_requested", False):
                break

            # Check if consumer task is done or failed
            if app.consumer_task.done():
                # Get any exception from the task
                try:
                    app.consumer_task.result()  # This will raise if task failed
                    logger.info("Kafka consumer task completed normally")
                except Exception as e:
                    restart_count += 1
                    logger.error(
                        f"Kafka consumer task failed (restart #{restart_count}): {e}", exc_info=True
                    )

                    if restart_count <= max_restart_attempts:
                        logger.info(f"Restarting Kafka consumer in {restart_delay:.1f}s...")
                        await asyncio.sleep(restart_delay)

                        # Don't restart if shutdown was requested during sleep
                        if getattr(app, "_consumer_shutdown_requested", False):
                            break

                        try:
                            async with restart_lock:
                                # Create new consumer task
                                async def start_consumer_task():
                                    try:
                                        await app.kafka_consumer.start_consuming()
                                    except Exception as e:
                                        logger.error(
                                            f"Kafka consumer task failed: {e}", exc_info=True
                                        )

                                app.consumer_task = asyncio.create_task(start_consumer_task())
                                logger.info(f"Kafka consumer restarted (attempt #{restart_count})")

                                # Increase restart delay for next time (exponential backoff)
                                restart_delay = min(restart_delay * 1.2, max_restart_delay)

                        except Exception as restart_error:
                            logger.error(
                                f"Failed to restart Kafka consumer: {restart_error}", exc_info=True
                            )
                    else:
                        logger.error(
                            f"Kafka consumer failed {max_restart_attempts} times. "
                            "Giving up on automatic restart."
                        )
                        break

                # Normal completion, reset restart count
                if restart_count > 0:
                    logger.info("Kafka consumer stabilized, resetting restart count")
                    restart_count = 0
                    restart_delay = 10.0  # Reset delay

            # Check consumer health
            elif hasattr(app.kafka_consumer, "is_healthy"):
                try:
                    is_healthy = await app.kafka_consumer.is_healthy()
                    if not is_healthy:
                        logger.warning("Kafka consumer reports unhealthy status")
                except Exception as e:
                    logger.warning(f"Failed to check consumer health: {e}")

        except asyncio.CancelledError:
            logger.info("Kafka consumer monitor cancelled")
            break
        except Exception as e:
            logger.error(f"Error in Kafka consumer monitor: {e}", exc_info=True)
            await asyncio.sleep(10.0)  # Wait before retrying monitor

    logger.info("BCS Kafka consumer monitor stopped")


app = HuleEduApp(__name__)

# Initialize service-specific attributes (following established patterns)
app.kafka_consumer = None
app.consumer_task = None

# --- Dependency Injection (must be wired before blueprint registration) ---
container = create_container()
QuartDishka(app=app, container=container)


@app.before_serving
async def startup() -> None:
    """Initialize middleware, metrics, and Kafka consumer."""
    try:
        # Metrics rely on the DI container which is already wired
        await initialize_metrics(app, container)
        setup_metrics_middleware(
            app,
            request_count_metric_name="http_requests_total",
            request_duration_metric_name="http_request_duration_seconds",
            status_label_name="status_code",
            logger_name="bcs.metrics",
        )

        # Get reference to Kafka event publisher for shutdown handling
        # Note: The publisher is already started in DI provider (APP scope)
        try:
            from huleedu_service_libs.protocols import KafkaPublisherProtocol

            async with container() as request_container:
                event_publisher = await request_container.get(KafkaPublisherProtocol)
                app.event_publisher = event_publisher

            logger.info("BCS Kafka event publisher reference obtained (already started in DI)")
        except Exception as e:
            logger.error(f"Failed to get Kafka event publisher reference: {e}", exc_info=True)

        # Start Kafka consumer for phase completion tracking with monitoring
        try:
            from services.batch_conductor_service.protocols import KafkaEventConsumerProtocol

            async with container() as request_container:
                kafka_consumer = await request_container.get(KafkaEventConsumerProtocol)

            # Store consumer as app attribute
            app.kafka_consumer = kafka_consumer
            app.consumer_task = None
            app.consumer_monitor_task = None
            app._consumer_shutdown_requested = False

            # Start consumer with monitoring
            await _start_kafka_consumer_with_monitoring(app)

            logger.info(
                "BCS Kafka consumer started with monitoring for phase completion tracking",
                extra={
                    "topics": [
                        "huleedu.essay.spellcheck.completed.v1",
                        "huleedu.cj_assessment.completed.v1",
                        "huleedu.els.batch.phase.outcome.v1",
                        "huleedu.batch.pipeline.completed.v1",
                    ]
                },
            )
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}", exc_info=True)
            # Don't raise - let the HTTP API still work even if Kafka consumer fails

        logger.info("Batch Conductor Service startup completed successfully")
    except Exception as e:
        logger.critical("Failed to start Batch Conductor Service: %s", e, exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services including Kafka consumer."""
    try:
        # Stop consumer monitoring and Kafka consumer
        if hasattr(app, "_consumer_shutdown_requested"):
            app._consumer_shutdown_requested = True

        # Stop consumer monitor task
        if (
            hasattr(app, "consumer_monitor_task")
            and app.consumer_monitor_task
            and not app.consumer_monitor_task.done()
        ):
            app.consumer_monitor_task.cancel()
            try:
                await app.consumer_monitor_task
            except asyncio.CancelledError:
                pass  # Expected when cancelling

        # Stop Kafka event publisher if running
        if hasattr(app, "event_publisher") and app.event_publisher:
            logger.info("Stopping BCS Kafka event publisher...")
            await app.event_publisher.stop()

        # Stop Kafka consumer if running
        if hasattr(app, "kafka_consumer") and app.kafka_consumer:
            logger.info("Stopping BCS Kafka consumer...")
            await app.kafka_consumer.stop_consuming()

        # Cancel consumer task if running
        if hasattr(app, "consumer_task") and app.consumer_task and not app.consumer_task.done():
            app.consumer_task.cancel()
            try:
                await app.consumer_task
            except asyncio.CancelledError:
                pass  # Expected when cancelling

        await shutdown_services()
        logger.info("Batch Conductor Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)


# Add consumer health check endpoint
@app.route("/internal/consumer/health", methods=["GET"])
async def consumer_health() -> tuple[dict, int]:
    """Check Kafka consumer health status."""
    try:
        if not hasattr(app, "kafka_consumer") or not app.kafka_consumer:
            return {"status": "error", "message": "Consumer not initialized"}, 503

        is_consuming = await app.kafka_consumer.is_consuming()
        is_healthy = (
            await app.kafka_consumer.is_healthy()
            if hasattr(app.kafka_consumer, "is_healthy")
            else is_consuming
        )

        task_status = "unknown"
        if hasattr(app, "consumer_task") and app.consumer_task:
            if app.consumer_task.done():
                try:
                    app.consumer_task.result()
                    task_status = "completed"
                except Exception:
                    task_status = "failed"
            else:
                task_status = "running"

        status = (
            "healthy" if (is_consuming and is_healthy and task_status == "running") else "unhealthy"
        )
        status_code = 200 if status == "healthy" else 503

        return {
            "status": status,
            "is_consuming": is_consuming,
            "is_healthy": is_healthy,
            "task_status": task_status,
        }, status_code

    except Exception as e:
        logger.error(f"Error checking consumer health: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, 503


# Register Blueprints
app.register_blueprint(health_bp)
app.register_blueprint(pipeline_bp)


if __name__ == "__main__":
    import asyncio

    import hypercorn.asyncio
    from hypercorn import Config

    # Create hypercorn config with our settings
    config = Config()
    config.bind = [f"{settings.HTTP_HOST}:{settings.HTTP_PORT}"]
    config.worker_class = "asyncio"
    config.loglevel = settings.LOG_LEVEL.lower()
    config.graceful_timeout = 30
    config.keep_alive_timeout = 60

    asyncio.run(hypercorn.asyncio.serve(app, config))
