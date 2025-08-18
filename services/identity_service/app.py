"""
Identity Service Application (Quart) – HTTP-only scaffold.

Registers minimal auth routes and sets up service middleware.
"""

from __future__ import annotations

from quart import Quart

from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)

from services.identity_service.api.auth_routes import bp as auth_bp
from services.identity_service.api.well_known_routes import bp as well_known_bp
from services.identity_service.config import settings
from services.identity_service.startup_setup import initialize_services, shutdown_services

configure_service_logging("identity-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("identity_service.app")

app = Quart(__name__)


@app.before_serving
async def startup() -> None:
    await initialize_services(app, settings)
    logger.info("Identity Service startup completed successfully")


@app.after_serving
async def shutdown() -> None:
    await shutdown_services()


# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(well_known_bp)
