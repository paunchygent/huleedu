"""
Identity Service Application – HTTP service with authentication and user management.

Uses HuleEduApp base class for standardized service patterns.
"""

from __future__ import annotations

from huleedu_service_libs import HuleEduApp
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)

from services.identity_service.api.auth_routes import bp as auth_bp
from services.identity_service.api.health_routes import bp as health_bp
from services.identity_service.api.password_routes import bp as password_bp
from services.identity_service.api.profile_routes import bp as profile_bp
from services.identity_service.api.registration_routes import bp as registration_bp
from services.identity_service.api.session_routes import bp as session_bp
from services.identity_service.api.verification_routes import bp as verification_bp
from services.identity_service.api.well_known_routes import bp as well_known_bp
from services.identity_service.config import settings
from services.identity_service.startup_setup import initialize_services, shutdown_services

configure_service_logging("identity-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("identity_service.app")

app = HuleEduApp(__name__)


@app.before_serving
async def startup() -> None:
    await initialize_services(app, settings)
    logger.info("Identity Service startup completed successfully")


@app.after_serving
async def shutdown() -> None:
    await shutdown_services()


# Register blueprints
app.register_blueprint(health_bp)  # Health check must be first for monitoring
app.register_blueprint(auth_bp)  # Core auth: login, logout, refresh
app.register_blueprint(registration_bp)  # User registration
app.register_blueprint(verification_bp)  # Email verification
app.register_blueprint(password_bp)  # Password reset/change
app.register_blueprint(session_bp)  # Session management
app.register_blueprint(profile_bp)  # User profiles
app.register_blueprint(well_known_bp)  # OpenID Connect
