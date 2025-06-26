from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from quart import Quart

import services.class_management_service.startup_setup as startup_setup
from services.class_management_service.api.class_routes import class_bp
from services.class_management_service.api.health_routes import health_bp
from services.class_management_service.config import settings

configure_service_logging("class-management-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("cms.app")

app = Quart(__name__)


@app.before_serving
async def startup() -> None:
    await startup_setup.initialize_services(app, settings)


@app.after_serving
async def shutdown() -> None:
    await startup_setup.shutdown_services()


app.register_blueprint(health_bp)
app.register_blueprint(class_bp, url_prefix="/v1/classes")


if __name__ == "__main__":
    app.run(host=settings.HOST, port=settings.PORT)
