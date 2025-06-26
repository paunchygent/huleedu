from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from quart import Quart

from dishka import FromDishka
from quart_dishka import QuartDishka, inject

import services.class_management_service.startup_setup as startup_setup
from services.class_management_service.api.class_routes import class_bp
from services.class_management_service.api.health_routes import health_bp
from services.class_management_service.config import Settings, settings
from services.class_management_service.di import create_container

# Configure logging first
configure_service_logging("class-management-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("cms.app")

# Create the Quart app
app = Quart(__name__)

# 1. Create the DI container
container = create_container()

# 2. Integrate DI with Quart (must be done before registering blueprints)
QuartDishka(app=app, container=container)

# 3. Register Blueprints
app.register_blueprint(health_bp)
app.register_blueprint(class_bp, url_prefix="/v1/classes")


@app.before_serving
async def startup() -> None:
    """Initialize database schema before the app starts serving."""
    await startup_setup.initialize_database_schema(settings)


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown services."""
    await startup_setup.shutdown_services()
    await container.close()


if __name__ == "__main__":
    app.run(host=settings.HOST, port=settings.PORT)
