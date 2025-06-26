
import startup_setup
from api.class_routes import class_bp
from api.health_routes import health_bp
from config import settings
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from quart import Quart

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
app.register_blueprint(class_bp)


if __name__ == "__main__":
    app.run(host=settings.HOST, port=settings.PORT)
