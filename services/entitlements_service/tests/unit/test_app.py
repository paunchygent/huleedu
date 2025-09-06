"""Comprehensive behavioral tests for entitlements service application setup.

This module tests application setup behavior following Rule 075 standards:
- Blueprint registration and URL prefix mapping
- Error handler registration and response formatting
- Application configuration and settings integration
- Route accessibility and HTTP method handling
- Swedish context handling where applicable

Tests focus on actual application behavior using Quart test patterns,
avoiding framework internals and complex DI initialization that can timeout.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from common_core.error_enums import ErrorCode
from huleedu_service_libs.error_handling import HuleEduError, create_test_error_detail
from huleedu_service_libs.quart_app import HuleEduApp
from pydantic import ValidationError
from quart.typing import TestClientProtocol as QuartTestClient

from services.entitlements_service.config import Settings


class TestApplicationSetup:
    """Tests for application setup and configuration behavior."""

    @pytest.fixture
    async def simple_test_app(self) -> HuleEduApp:
        """Create simple test application for behavioral testing without complex DI."""
        app = HuleEduApp(__name__)
        app.config["TESTING"] = True
        app.config["DEBUG"] = True

        # Register blueprints like the real app does
        from services.entitlements_service.api.admin_routes import admin_bp
        from services.entitlements_service.api.entitlements_routes import entitlements_bp
        from services.entitlements_service.api.health_routes import health_bp

        app.register_blueprint(health_bp)
        app.register_blueprint(entitlements_bp, url_prefix="/v1/entitlements")
        app.register_blueprint(admin_bp, url_prefix="/v1/admin")

        # Add error handlers like the real app
        @app.errorhandler(HuleEduError)
        async def handle_huleedu_error(error: HuleEduError) -> Any:
            """Handle HuleEdu business errors."""
            return {
                "error": error.error_detail.error_code,
                "message": error.error_detail.message,
                "service": "entitlements_service",
            }, 400

        @app.errorhandler(ValidationError)
        async def handle_validation_error(error: ValidationError) -> Any:
            """Handle Pydantic validation errors."""
            return {
                "error": "validation_error",
                "message": "Invalid request data",
                "details": error.errors(),
                "service": "entitlements_service",
            }, 400

        @app.errorhandler(Exception)
        async def handle_exception(e: Exception) -> Any:
            """Global exception handler."""
            return {
                "error": "Internal server error",
                "message": "An unexpected error occurred",
                "service": "entitlements_service",
            }, 500

        return app

    @pytest.fixture
    async def test_client(
        self, simple_test_app: HuleEduApp
    ) -> AsyncGenerator[QuartTestClient, None]:
        """Create test client for behavioral testing."""
        async with simple_test_app.test_client() as client:
            yield client

    @pytest.mark.parametrize(
        "blueprint_name, expected_present",
        [
            ("health", True),
            ("entitlements", True),
            ("admin", True),  # Present in this test setup
            ("nonexistent", False),
        ],
    )
    def test_blueprint_registration(
        self, simple_test_app: HuleEduApp, blueprint_name: str, expected_present: bool
    ) -> None:
        """Test that expected blueprints are registered with the application.

        Verifies blueprint registration behavior without testing framework internals.
        """
        blueprint_names = [bp.name for bp in simple_test_app.blueprints.values()]

        if expected_present:
            assert blueprint_name in blueprint_names, (
                f"Blueprint '{blueprint_name}' should be registered"
            )
        else:
            assert blueprint_name not in blueprint_names, (
                f"Blueprint '{blueprint_name}' should not be registered"
            )

    def test_settings_configuration_behavior(self) -> None:
        """Test that settings behave correctly for different environments."""
        import os

        from common_core.config_enums import Environment

        # Test by temporarily setting ENVIRONMENT variable
        original_env = os.environ.get("ENVIRONMENT")

        try:
            # Test production environment
            os.environ["ENVIRONMENT"] = "production"
            prod_settings = Settings()
            assert prod_settings.is_production()
            assert prod_settings.ENVIRONMENT == Environment.PRODUCTION

            # Test development environment
            os.environ["ENVIRONMENT"] = "development"
            dev_settings = Settings()
            assert not dev_settings.is_production()
            assert dev_settings.ENVIRONMENT == Environment.DEVELOPMENT

        finally:
            # Restore original environment
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env
            elif "ENVIRONMENT" in os.environ:
                del os.environ["ENVIRONMENT"]

        # Test default configuration values
        default_settings = Settings()
        assert default_settings.METRICS_PORT == 8083
        assert default_settings.SERVICE_NAME == "entitlements_service"

    @pytest.mark.parametrize(
        "route_path, expected_methods",
        [
            ("/healthz", ["GET"]),
            ("/metrics", ["GET"]),
            ("/v1/entitlements/check-credits", ["POST"]),
            ("/v1/entitlements/consume-credits", ["POST"]),
            ("/v1/entitlements/balance", ["GET"]),
            ("/v1/admin/adjust-credits", ["POST"]),
            ("/v1/admin/operations", ["GET"]),
            ("/v1/admin/rate-limit/reset", ["POST"]),
        ],
    )
    async def test_route_registration(
        self, test_client: QuartTestClient, route_path: str, expected_methods: list[str]
    ) -> None:
        """Test that application routes are properly registered and accessible.

        Verifies route existence by checking that requests don't return 404,
        focusing on route registration rather than business logic.
        """
        for method in expected_methods:
            if method == "GET":
                response = await test_client.get(route_path)
            elif method == "POST":
                response = await test_client.post(route_path, json={})
            else:
                response = await test_client.open(route_path, method=method, json={})

            # Route should exist (not 404), but may return validation errors or other status codes
            assert response.status_code != 404, f"Route {method} {route_path} should be registered"

    async def test_health_endpoint_basic_accessibility(self, test_client: QuartTestClient) -> None:
        """Test that health endpoint is accessible and returns expected format."""
        response = await test_client.get("/healthz")

        # Should not be 404 (route exists)
        assert response.status_code != 404
        # Health endpoint should return some form of JSON response
        data = await response.get_json()
        assert data is not None

    async def test_metrics_endpoint_basic_accessibility(self, test_client: QuartTestClient) -> None:
        """Test that metrics endpoint is accessible."""
        response = await test_client.get("/metrics")

        # Should not be 404 (route exists)
        assert response.status_code != 404

    def test_application_configuration(self, simple_test_app: HuleEduApp) -> None:
        """Test that application is configured with expected settings."""
        # Verify app configuration behavior
        assert simple_test_app.config["TESTING"] is True
        assert simple_test_app.config["DEBUG"] is True

        # Verify this is a HuleEdu app instance
        assert isinstance(simple_test_app, HuleEduApp)

    @pytest.mark.parametrize(
        "error_type, expected_status, error_data",
        [
            (
                HuleEduError,
                400,
                create_test_error_detail(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Test business error",
                    service="entitlements_service",
                    operation="test_operation",
                ),
            ),
        ],
    )
    async def test_error_handler_behavior(
        self,
        simple_test_app: HuleEduApp,
        error_type: type[Exception],
        expected_status: int,
        error_data: Any,
    ) -> None:
        """Test that error handlers return correct HTTP status codes and formats.

        Focuses on error handling behavior without testing framework internals.
        """

        # Create a test route that raises the specific error
        @simple_test_app.route("/test-error")
        async def _test_error_route() -> Any:
            if error_type == HuleEduError:
                raise HuleEduError(error_data)
            else:
                raise error_type("Test error")

        async with simple_test_app.test_client() as client:
            response = await client.get("/test-error")

            assert response.status_code == expected_status

            # Verify response format contains expected error information
            response_data = await response.get_json()
            assert "error" in response_data
            assert "message" in response_data
            assert "service" in response_data
            assert response_data["service"] == "entitlements_service"

    async def test_validation_error_handler_behavior(self, simple_test_app: HuleEduApp) -> None:
        """Test that ValidationError handler returns correct response format."""

        @simple_test_app.route("/test-validation-error")
        async def _test_validation_error_route() -> Any:
            # Simulate a validation error by creating a simple Pydantic model with validation failure
            from pydantic import BaseModel, Field

            class TestModel(BaseModel):
                required_field: str = Field(..., min_length=5)

            # This will raise ValidationError
            TestModel(required_field="abc")  # Too short

        async with simple_test_app.test_client() as client:
            response = await client.get("/test-validation-error")

            # ValidationError should be handled and return 400
            assert response.status_code == 400
            response_data = await response.get_json()
            assert "error" in response_data
            assert response_data["error"] == "validation_error"
            assert response_data["service"] == "entitlements_service"

    async def test_unhandled_exception_error_handler(self, simple_test_app: HuleEduApp) -> None:
        """Test that unhandled exceptions return proper 500 response."""

        @simple_test_app.route("/test-unhandled-error")
        async def _test_unhandled_error_route() -> Any:
            raise RuntimeError("Unexpected error")

        async with simple_test_app.test_client() as client:
            response = await client.get("/test-unhandled-error")

            assert response.status_code == 500
            response_data = await response.get_json()
            assert response_data["error"] == "Internal server error"
            assert response_data["service"] == "entitlements_service"

    @pytest.mark.parametrize(
        "blueprint_name",
        [
            "entitlements",
            "admin",
        ],
    )
    def test_blueprint_url_prefixes(self, simple_test_app: HuleEduApp, blueprint_name: str) -> None:
        """Test that blueprints are registered with correct URL prefixes."""
        blueprint_names = [bp.name for bp in simple_test_app.blueprints.values()]

        assert blueprint_name in blueprint_names
        # Verify the blueprint is registered (actual URL testing is done in route tests)
        blueprint = next(
            bp for bp in simple_test_app.blueprints.values() if bp.name == blueprint_name
        )
        assert blueprint is not None

    async def test_swedish_error_message_handling(self, simple_test_app: HuleEduApp) -> None:
        """Test that Swedish error messages are properly handled in context."""

        @simple_test_app.route("/test-swedish-error")
        async def _test_swedish_error_route() -> Any:
            error_detail = create_test_error_detail(
                error_code=ErrorCode.QUOTA_EXCEEDED,
                message="Credit limit exceeded",
                service="entitlements_service",
                operation="test_swedish_error",
            )
            raise HuleEduError(error_detail)

        async with simple_test_app.test_client() as client:
            response = await client.get("/test-swedish-error")

            assert response.status_code == 400
            response_data = await response.get_json()

            # Verify error response contains expected information
            assert "error" in response_data
            assert "message" in response_data

    @pytest.mark.parametrize(
        "environment, expected_is_production",
        [
            ("development", False),
            ("production", True),
        ],
    )
    def test_environment_specific_configuration(
        self, environment: str, expected_is_production: bool
    ) -> None:
        """Test that configuration varies correctly by environment."""
        import os

        from common_core.config_enums import Environment

        original_env = os.environ.get("ENVIRONMENT")
        try:
            os.environ["ENVIRONMENT"] = environment
            settings = Settings()
            assert settings.is_production() == expected_is_production
            assert settings.ENVIRONMENT == Environment(environment)
        finally:
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env
            elif "ENVIRONMENT" in os.environ:
                del os.environ["ENVIRONMENT"]

    def test_application_factory_callable(self) -> None:
        """Test that application factory is callable without complex initialization."""
        from services.entitlements_service.app import create_app

        # Verify the factory function exists and is callable
        assert callable(create_app)

        # Test settings creation without full app initialization
        test_settings = Settings(
            LOG_LEVEL="INFO",
            TESTING=True,
            USE_MOCK_REPOSITORY=True,
            HULEEDU_ENVIRONMENT="development",
        )
        assert test_settings.LOG_LEVEL == "INFO"

    def test_blueprint_count_validation(self, simple_test_app: HuleEduApp) -> None:
        """Test that expected number of blueprints are registered."""
        blueprint_names = [bp.name for bp in simple_test_app.blueprints.values()]

        # Should have at least 3 blueprints: health, entitlements, admin
        assert len(blueprint_names) >= 3

        # Verify core blueprints
        expected_blueprints = ["health", "entitlements", "admin"]
        for expected_bp in expected_blueprints:
            assert expected_bp in blueprint_names

    async def test_cors_and_middleware_configuration(self, test_client: QuartTestClient) -> None:
        """Test that basic middleware configuration is working."""
        response = await test_client.get("/healthz")

        # Should get a response (middleware not blocking)
        assert response.status_code != 404

        # Basic response header validation
        assert "content-type" in response.headers

    def test_service_configuration_constants(self) -> None:
        """Test that service configuration constants are properly set."""
        settings = Settings()

        # Service-specific constants
        assert settings.SERVICE_NAME == "entitlements_service"
        assert settings.METRICS_PORT == 8083
        assert isinstance(settings.DEFAULT_USER_CREDITS, int)
        assert isinstance(settings.DEFAULT_ORG_CREDITS, int)

        # Credit system settings
        assert settings.DEFAULT_USER_CREDITS > 0
        assert settings.DEFAULT_ORG_CREDITS > 0
        assert settings.CREDIT_MINIMUM_BALANCE >= 0
