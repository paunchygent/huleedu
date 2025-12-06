"""LLM Provider Service - Quart Application Setup.

This is a lean entry point following HuleEdu patterns.
All setup logic is delegated to startup_setup.py.
"""

from quart import Quart

from services.llm_provider_service.api.admin_routes import admin_bp
from services.llm_provider_service.api.health_routes import health_bp
from services.llm_provider_service.api.llm_routes import llm_bp
from services.llm_provider_service.config import settings
from services.llm_provider_service.startup_setup import initialize_services, shutdown_services

# Create Quart app
app = Quart(__name__)


@app.before_serving
async def startup() -> None:
    """Initialize services on startup."""
    await initialize_services(app, settings)


@app.after_serving
async def shutdown() -> None:
    """Clean up services on shutdown."""
    await shutdown_services(app)


# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(llm_bp, url_prefix="/api/v1")

if __name__ == "__main__":
    import sys

    # For local development only
    if "--reload" in sys.argv:
        app.run(host="0.0.0.0", port=settings.PORT, debug=True)
    else:
        app.run(host="0.0.0.0", port=settings.PORT)
