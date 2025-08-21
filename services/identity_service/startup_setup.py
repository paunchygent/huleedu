from __future__ import annotations

from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware,
)
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from quart import Quart
from quart_dishka import QuartDishka

from services.identity_service.config import Settings
from services.identity_service.di import (
    CoreProvider,
    DomainHandlerProvider,
    IdentityImplementationsProvider,
)

logger = create_service_logger("identity_service.startup")


async def initialize_services(app: Quart, settings: Settings) -> None:
    configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
    logger.info("Identity Service initializing")

    # DI container and quart integration
    container = make_async_container(
        CoreProvider(),
        IdentityImplementationsProvider(),
        DomainHandlerProvider(),
        OutboxProvider(),
    )
    QuartDishka(app=app, container=container)

    # Tracing
    tracer = init_tracing("identity_service")
    app.extensions = getattr(app, "extensions", {})
    app.extensions["tracer"] = tracer
    setup_tracing_middleware(app, tracer)

    # Start outbox relay worker
    async with container() as request_container:
        relay_worker = await request_container.get(EventRelayWorker)
        await relay_worker.start()
        app.extensions["relay_worker"] = relay_worker
        logger.info("EventRelayWorker started for outbox pattern")


async def shutdown_services(app: Quart | None = None) -> None:
    if app and hasattr(app, "extensions") and "relay_worker" in app.extensions:
        relay_worker = app.extensions["relay_worker"]
        await relay_worker.stop()
    logger.info("Identity Service shutdown complete")
