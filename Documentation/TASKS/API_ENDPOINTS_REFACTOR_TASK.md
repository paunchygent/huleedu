# Ticket For Refactoring API Endpoints to Use Blueprints in Existing Services

This is a task ticket for refactoring the existing Quart-based services to use Blueprints for API route organization. This will standardize the approach across your services and help maintain compliance with SRP, SoC, and file size limits.

## Task Ticket: Refactor API Routes to Use Quart Blueprints in Existing Services

**Goal**:
Refactor the `app.py` files in `batch_orchestrator_service`, `content_service`, and `essay_lifecycle_service` to use Quart Blueprints for API route definitions. This will improve code organization, maintainability, and adherence to file size limits by separating route logic from application setup.

**Context/Background**:
As discussed, to prevent `app.py` files from becoming bloated and to better enforce Single Responsibility Principle (SRP) and Separation of Concerns (SoC), we are adopting Quart Blueprints for organizing API endpoints. This ticket applies this pattern to existing services for consistency before further development.

**Affected Services**:

1. `services/batch_orchestrator_service`
2. `services/content_service`
3. `services/essay_lifecycle_service`

---

## Required Preconditions

Before starting this task, ensure the following are met:

- You have found and read all the affected services' `app.py` files.
- Using view_file or similar tools, you have verified the current app.py structures for each affected service.
- No truncated app.py files are present in your context.
- You have listed all rules in the `.cursor/rules/` directory and activated and read the ones that relate to the current task.

**What is considered "met"?**

- You have found and read all the affected services' `app.py` files.
- Using view_file or similar tools, you have verified the current app.py structures for each affected service.
- No truncated app.py files are present in your context.
- You have listed all rules in the `.cursor/rules/` directory and selected the ones that relate to the current task.
- You have marked this step as completed in the task ticket.

## Implementation Steps for Each Affected Service

For each service (`batch_orchestrator_service`, `content_service`, `essay_lifecycle_service`):

1. **Create an `api` Directory**:
    * Inside the service's root directory (e.g., `services/batch_orchestrator_service/`), create a new subdirectory named `api`.
    * Add an `__init__.py` file to the new `api/` directory to make it a package.

        ```
        services/<service_name>/
        ├── api/
        │   ├── __init__.py
        │   └── ... (blueprint modules will go here)
        ├── app.py
        └── ...
        ```

    * This structure aligns with project standards for organizing service-specific code.

2. **Identify and Group Existing Routes**:
    * Review the existing `app.py` file for that service.
    * Identify all `@app.route(...)` definitions.
    * Group related routes. For example:
        * Health and metrics routes (`/healthz`, `/metrics`) can go into a `health_routes.py` module.
        * Service-specific functional routes (e.g., batch operations, content operations, essay status queries) can go into modules like `batch_routes.py`, `content_routes.py`, `essay_routes.py`.

3. **Create Blueprint Modules in the `api/` Directory**:
    * For each group of routes identified, create a new Python file in the `api/` directory (e.g., `services/batch_orchestrator_service/api/batch_routes.py`, `services/batch_orchestrator_service/api/health_routes.py`).

4. **Implement Blueprints and Move Route Logic**:
    * In each new Blueprint module (e.g., `batch_routes.py`):
        * Import `Blueprint` from `quart`.
        * Create a Blueprint instance: `example_bp = Blueprint('example_routes', __name__, url_prefix='/v1/example')`. Adjust `url_prefix` as needed to match existing route prefixes.
        * Move the corresponding route handler functions from `app.py` to this module.
        * Change `@app.route(...)` decorators to `@example_bp.route(...)`.
        * Ensure all necessary imports (Pydantic models, protocols, DI tools like `@inject` and `FromDishka`, `common_core` types, service config, etc.) are present at the top of the Blueprint module.
        * Instantiate a module-specific logger using `create_service_logger("servicename.api.blueprintname")` for logging within these route handlers.
        * **Dishka DI**: The `@inject` decorator and `FromDishka[DependencyType]` will continue to work as expected on routes defined within Blueprints, provided QuartDishka is initialized on the main app.

    * **Example for `services/batch_orchestrator_service/api/batch_routes.py`**:

        ```python
        from quart import Blueprint, jsonify, Response # etc.
        from quart_dishka import inject
        from dishka import FromDishka
        # ... other necessary imports like protocols, config, common_core models
        from huleedu_service_libs.logging_utils import create_service_logger

        logger = create_service_logger("bos.api.batch_routes") # Specific logger
        batch_bp = Blueprint('batch_routes', __name__, url_prefix='/v1/batches')

        @batch_bp.route("/trigger-spellcheck-test", methods=["POST"])
        @inject
        async def trigger_spellcheck_test_endpoint(
            # ... dependencies ...
        ) -> Response | tuple[Response, int]:
            logger.info("Handling /trigger-spellcheck-test request via blueprint")
            # ... (logic from original app.py) ...
            return jsonify({"message": "Triggered via blueprint"}), 202
        
        # Add other batch-related routes here...
        ```

5. **Refactor `app.py`**:
    * Remove all the route handler functions and `@app.route` definitions that were moved to Blueprint modules.
    * Import the Blueprint instances from your new `api` modules (e.g., `from .api.batch_routes import batch_bp`).
    * Register these Blueprints with the Quart `app` instance: `app.register_blueprint(batch_bp)`.
    * The `app.py` should now primarily contain:
        * Quart app initialization (`app = Quart(__name__)`).
        * `@app.before_serving` logic for DI setup (e.g., `QuartDishka(app=app, container=container)`).
        * Blueprint registrations.
        * Global error handlers (e.g., `@app.errorhandler(ValidationError)`), if not made Blueprint-specific.
        * Global `before_request` and `after_request` hooks (like those used for metrics), if these are intended to apply to all routes. Alternatively, these can also be applied per-Blueprint.
        * The main `if __name__ == "__main__":` block for local development runs (if applicable, though Hypercorn via PDM script is standard).

    * **Example snippet for `services/batch_orchestrator_service/app.py` after refactor**:

        ```python
        from quart import Quart
        from dishka import make_async_container
        from quart_dishka import QuartDishka
        
        from .config import settings
        from .di import BatchOrchestratorServiceProvider
        from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
        
        # Import Blueprints
        from .api.batch_routes import batch_bp 
        # from .api.health_routes import health_bp # Assuming health_bp handles /healthz, /metrics

        configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
        logger = create_service_logger("bos.app")

        app = Quart(__name__)

        @app.before_serving
        async def startup() -> None:
            container = make_async_container(BatchOrchestratorServiceProvider())
            QuartDishka(app=app, container=container)
            # Global metrics initialization might occur here or be tied to a health/metrics blueprint
            logger.info("BOS DI container & Quart-Dishka initialized.")

        # Register Blueprints
        app.register_blueprint(batch_bp)
        # app.register_blueprint(health_bp) 

        # Global error handlers and request hooks can remain here if desired
        # ...
        ```

6. **Metrics Endpoints (`/metrics`) and Request Hooks**:
    * The `/metrics` endpoint and associated Prometheus logic (e.g., `generate_latest`) should also be moved to a Blueprint, typically within `health_routes.py`.
    * The `before_request` and `after_request` hooks used for timing requests and incrementing counters can either remain global in `app.py` if they apply to all endpoints uniformly, or they can be made Blueprint-specific if finer-grained control is needed. For simplicity and consistency, keeping them global but in the lean `app.py` is acceptable.

---
**Specific Services and their Routes to Migrate:**

* **`services/batch_orchestrator_service/app.py`**:
  * `POST /v1/batches/trigger-spellcheck-test` → `api/batch_routes.py`
  * `GET /healthz` → `api/health_routes.py`
  * `GET /metrics` → `api/health_routes.py`

* **`services/content_service/app.py`**:
  * `POST /v1/content` → `api/content_routes.py`
  * `GET /v1/content/<string:content_id>` → `api/content_routes.py`
  * `GET /healthz` → `api/health_routes.py`
  * `GET /metrics` → `api/health_routes.py`

* **`services/essay_lifecycle_service/app.py`**:
  * `GET /healthz` → `api/health_routes.py`
  * `GET /metrics` → `api/health_routes.py`
  * `GET /<API_VERSION>/essays/<essay_id>/status` → `api/essay_routes.py`
  * `GET /<API_VERSION>/essays/<essay_id>/timeline` → `api/essay_routes.py`
  * `GET /<API_VERSION>/batches/<batch_id>/status` → `api/batch_routes.py` (or `essay_routes.py` if preferred for essay-related batch queries)

---
**Definition of Done**:

1. All API routes in the three specified services (`batch_orchestrator_service`, `content_service`, `essay_lifecycle_service`) are defined within Quart Blueprints residing in service-local `api/` subdirectories.
2. The main `app.py` file for each refactored service is significantly reduced in size, primarily handling application setup, DI initialization, and Blueprint registration.
3. All existing API functionality remains unchanged and operational.
4. All existing tests for these services pass after the refactoring. (This implies running `pdm run test-all` or service-specific tests).
5. The refactored code adheres to all project coding standards, including linting (`pdm run lint-all`), type checking (`pdm run typecheck-all`), and file size/line length limits.
6. Dishka dependency injection works correctly for all refactored routes.

**Priority**: High. This refactoring should ideally be completed before adding significant new API endpoints to these services to establish a clean and maintainable pattern.
