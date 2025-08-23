"""Contract tests for Email Service API endpoints.

These tests ensure API endpoint contracts remain stable and schemas are properly validated.
Focus is on request/response structure validation, not business logic implementation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container
from prometheus_client import CollectorRegistry
from quart import Quart
from quart_dishka import QuartDishka

from services.email_service.api.dev_routes import dev_bp
from services.email_service.api.health_routes import health_bp
from services.email_service.config import Settings
from services.email_service.protocols import (
    EmailProvider,
    EmailSendResult,
    RenderedTemplate,
    TemplateRenderer,
)


@pytest.fixture
async def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = AsyncMock(spec=Settings)
    settings.is_production.return_value = False
    settings.DEFAULT_FROM_EMAIL = "test@huleedu.se"
    settings.DEFAULT_FROM_NAME = "HuleEdu Test"
    return settings


@pytest.fixture
async def production_settings() -> Settings:
    """Create production mode settings for testing."""
    settings = AsyncMock(spec=Settings)
    settings.is_production.return_value = True
    return settings


@pytest.fixture
async def mock_email_provider() -> EmailProvider:
    """Create mock email provider for testing."""
    provider = AsyncMock(spec=EmailProvider)
    provider.send_email.return_value = EmailSendResult(
        success=True,
        provider_message_id="test-message-123",
        error_message=None,
    )
    provider.get_provider_name.return_value = "mock"
    return provider


@pytest.fixture
async def failed_email_provider() -> EmailProvider:
    """Create mock email provider that fails."""
    provider = AsyncMock(spec=EmailProvider)
    provider.send_email.return_value = EmailSendResult(
        success=False,
        provider_message_id=None,
        error_message="Provider connection failed",
    )
    provider.get_provider_name.return_value = "mock"
    return provider


@pytest.fixture
async def mock_template_renderer() -> TemplateRenderer:
    """Create mock template renderer for testing."""
    renderer = AsyncMock(spec=TemplateRenderer)
    renderer.render.return_value = RenderedTemplate(
        subject="Test Subject with Swedish chars: åäö",
        html_content="<p>Välkommen till HuleEdu! Swedish test: ÅÄÖD</p>",
        text_content="Välkommen till HuleEdu! Swedish test: ÅÄÖ",
    )
    renderer.template_exists.return_value = True
    return renderer


@pytest.fixture
async def test_app(
    mock_settings: Settings,
    mock_email_provider: EmailProvider,
    mock_template_renderer: TemplateRenderer,
) -> Quart:
    """Create test Quart app with mock dependencies."""
    app = Quart(__name__)
    app.register_blueprint(health_bp)
    app.register_blueprint(dev_bp)

    # Create provider with mocked dependencies
    provider = Provider()
    provider.provide(lambda: mock_settings, scope=Scope.APP, provides=Settings)
    provider.provide(lambda: mock_email_provider, scope=Scope.REQUEST, provides=EmailProvider)
    provider.provide(lambda: mock_template_renderer, scope=Scope.REQUEST, provides=TemplateRenderer)
    provider.provide(lambda: CollectorRegistry(), scope=Scope.APP, provides=CollectorRegistry)

    # Setup DI container
    container = make_async_container(provider)
    QuartDishka(app=app, container=container)

    return app


@pytest.fixture
async def production_app(
    production_settings: Settings,
    mock_email_provider: EmailProvider,
    mock_template_renderer: TemplateRenderer,
) -> Quart:
    """Create test app in production mode."""
    app = Quart(__name__)
    app.register_blueprint(health_bp)
    app.register_blueprint(dev_bp)

    provider = Provider()
    provider.provide(lambda: production_settings, scope=Scope.APP, provides=Settings)
    provider.provide(lambda: mock_email_provider, scope=Scope.REQUEST, provides=EmailProvider)
    provider.provide(lambda: mock_template_renderer, scope=Scope.REQUEST, provides=TemplateRenderer)
    provider.provide(lambda: CollectorRegistry(), scope=Scope.APP, provides=CollectorRegistry)

    container = make_async_container(provider)
    QuartDishka(app=app, container=container)

    return app


class TestHealthEndpointContracts:
    """Test health endpoint response contracts."""

    @pytest.mark.parametrize(
        "endpoint",
        ["/healthz", "/health"],
        ids=["healthz-endpoint", "health-endpoint"],
    )
    async def test_health_endpoint_response_schema(self, test_app: Quart, endpoint: str) -> None:
        """Test health endpoints return expected schema structure."""
        async with test_app.test_client() as client:
            response = await client.get(endpoint)

            assert response.status_code == 200
            assert response.content_type == "application/json"

            data = await response.get_json()
            assert isinstance(data, dict)
            assert "status" in data
            assert "service" in data
            assert data["status"] == "healthy"
            assert data["service"] == "email_service"

    async def test_health_endpoint_json_content_type(self, test_app: Quart) -> None:
        """Test health endpoints return correct Content-Type header."""
        async with test_app.test_client() as client:
            response = await client.get("/healthz")

            assert response.status_code == 200
            assert "application/json" in response.content_type

    async def test_health_endpoints_consistency(self, test_app: Quart) -> None:
        """Test that both health endpoints return identical responses."""
        async with test_app.test_client() as client:
            healthz_response = await client.get("/healthz")
            health_response = await client.get("/health")

            assert healthz_response.status_code == health_response.status_code
            healthz_data = await healthz_response.get_json()
            health_data = await health_response.get_json()
            assert healthz_data == health_data


class TestDevSendEndpointContract:
    """Test development send endpoint request/response contracts."""

    @pytest.mark.parametrize(
        "request_data",
        [
            {
                "to": "student@universitetet.se",
                "template_id": "verification",
                "variables": {"name": "Åsa Öström", "verification_code": "123456"},
            },
            {
                "to": "lärare@skolan.se",
                "template_id": "welcome",
                "variables": {"teacher_name": "Erik Åberg", "class_name": "Svenska 3"},
            },
        ],
        ids=["swedish-student-verification", "swedish-teacher-welcome"],
    )
    async def test_dev_send_success_response_schema(
        self, test_app: Quart, request_data: dict[str, Any]
    ) -> None:
        """Test successful send request returns expected response schema."""
        async with test_app.test_client() as client:
            response = await client.post("/v1/emails/dev/send", json=request_data)

            assert response.status_code == 200
            assert response.content_type == "application/json"

            data = await response.get_json()
            assert isinstance(data, dict)
            assert set(data.keys()) == {"success", "provider_message_id", "error_message"}
            assert isinstance(data["success"], bool)
            assert data["success"] is True
            assert isinstance(data["provider_message_id"], str)
            assert data["error_message"] is None

    @pytest.mark.parametrize(
        "missing_field, request_data",
        [
            ("to", {"template_id": "verification", "variables": {"name": "Test"}}),
            ("template_id", {"to": "test@example.com", "variables": {"name": "Test"}}),
            ("variables", {"to": "test@example.com", "template_id": "verification"}),
        ],
        ids=["missing-to", "missing-template-id", "missing-variables"],
    )
    async def test_dev_send_missing_fields_error_contract(
        self,
        test_app: Quart,
        missing_field: str,
        request_data: dict[str, Any],
    ) -> None:
        """Test error response contract for missing required fields."""
        async with test_app.test_client() as client:
            response = await client.post("/v1/emails/dev/send", json=request_data)

            assert response.status_code == 400
            assert response.content_type == "application/json"

            data = await response.get_json()
            assert isinstance(data, dict)
            assert "error" in data
            assert "required" in data
            assert isinstance(data["required"], list)
            assert missing_field in data["required"]

    async def test_dev_send_production_mode_restriction(self, production_app: Quart) -> None:
        """Test development endpoint returns 403 in production mode."""
        async with production_app.test_client() as client:
            request_data = {
                "to": "test@example.com",
                "template_id": "verification",
                "variables": {"name": "Test"},
            }
            response = await client.post("/v1/emails/dev/send", json=request_data)

            assert response.status_code == 403
            assert response.content_type == "application/json"

            data = await response.get_json()
            assert isinstance(data, dict)
            assert "error" in data
            assert "production" in data["error"].lower()

    async def test_dev_send_invalid_json_request(self, test_app: Quart) -> None:
        """Test endpoint handles invalid JSON gracefully."""
        async with test_app.test_client() as client:
            response = await client.post(
                "/v1/emails/dev/send",
                data="invalid-json",
                headers={"Content-Type": "application/json"},
            )

            assert response.status_code in [
                400,
                422,
                500,
            ]  # Bad request, unprocessable entity, or server error

    async def test_dev_send_provider_failure_response(
        self,
        mock_settings: Settings,
        failed_email_provider: EmailProvider,
        mock_template_renderer: TemplateRenderer,
    ) -> None:
        """Test response schema when email provider fails."""
        # Create test app with failed email provider
        app = Quart(__name__)
        app.register_blueprint(health_bp)
        app.register_blueprint(dev_bp)

        provider = Provider()
        provider.provide(lambda: mock_settings, scope=Scope.APP, provides=Settings)
        provider.provide(lambda: failed_email_provider, scope=Scope.REQUEST, provides=EmailProvider)
        provider.provide(
            lambda: mock_template_renderer, scope=Scope.REQUEST, provides=TemplateRenderer
        )
        provider.provide(lambda: CollectorRegistry(), scope=Scope.APP, provides=CollectorRegistry)

        container = make_async_container(provider)
        QuartDishka(app=app, container=container)

        async with app.test_client() as client:
            request_data = {
                "to": "test@example.com",
                "template_id": "verification",
                "variables": {"name": "Test"},
            }
            response = await client.post("/v1/emails/dev/send", json=request_data)

            # Should still return 200 with failure details in response
            assert response.status_code == 200
            data = await response.get_json()
            assert data["success"] is False
            assert data["provider_message_id"] is None
            assert isinstance(data["error_message"], str)


class TestDevTemplatesEndpointContract:
    """Test development templates endpoint response contract."""

    async def test_dev_templates_response_schema(self, test_app: Quart) -> None:
        """Test templates endpoint returns expected array structure."""
        async with test_app.test_client() as client:
            response = await client.get("/v1/emails/dev/templates")

            assert response.status_code == 200
            assert response.content_type == "application/json"

            data = await response.get_json()
            assert isinstance(data, dict)
            assert "templates" in data
            assert isinstance(data["templates"], list)

    async def test_dev_templates_content_validation(self, test_app: Quart) -> None:
        """Test templates endpoint returns expected template IDs."""
        async with test_app.test_client() as client:
            response = await client.get("/v1/emails/dev/templates")

            data = await response.get_json()
            templates = data["templates"]

            # Verify known template IDs are present
            expected_templates = {"verification", "password_reset", "welcome", "notification"}
            assert isinstance(templates, list)
            assert len(templates) > 0
            assert all(isinstance(template, str) for template in templates)
            assert expected_templates.issubset(set(templates))

    async def test_dev_templates_production_restriction(self, production_app: Quart) -> None:
        """Test templates endpoint returns 403 in production mode."""
        async with production_app.test_client() as client:
            response = await client.get("/v1/emails/dev/templates")

            assert response.status_code == 403
            assert response.content_type == "application/json"

            data = await response.get_json()
            assert isinstance(data, dict)
            assert "error" in data
            assert "production" in data["error"].lower()


class TestRequestResponseSerialization:
    """Test JSON request/response serialization contracts."""

    @pytest.mark.parametrize(
        "swedish_characters",
        [
            {"name": "Åsa", "location": "Göteborg"},
            {"message": "Välkommen till universitetet!"},
            {"teacher": "Björn Öström", "subject": "Språk & Kommunikation"},
        ],
        ids=["common-swedish-chars", "welcome-message", "teacher-subject"],
    )
    async def test_swedish_character_serialization(
        self, test_app: Quart, swedish_characters: dict[str, str]
    ) -> None:
        """Test that Swedish characters are properly handled in requests and responses."""
        async with test_app.test_client() as client:
            request_data = {
                "to": "test@skolan.se",
                "template_id": "verification",
                "variables": swedish_characters,
            }
            response = await client.post("/v1/emails/dev/send", json=request_data)

            assert response.status_code == 200
            data = await response.get_json()

            # Verify response is properly serialized
            assert isinstance(data, dict)
            assert data["success"] is True

    async def test_content_type_validation(self, test_app: Quart) -> None:
        """Test that endpoints handle missing Content-Type header."""
        async with test_app.test_client() as client:
            # Test without Content-Type
            response = await client.post(
                "/v1/emails/dev/send",
                data='{"to": "test@example.com", "template_id": "test", "variables": {}}',
            )

            assert response.status_code in [400, 415, 422, 500]

    async def test_empty_request_body_handling(self, test_app: Quart) -> None:
        """Test handling of empty request bodies."""
        async with test_app.test_client() as client:
            response = await client.post("/v1/emails/dev/send", json={})

            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data
            assert "required" in data

    async def test_response_json_structure_consistency(self, test_app: Quart) -> None:
        """Test that all JSON responses have consistent structure."""
        async with test_app.test_client() as client:
            # Test success response
            success_response = await client.post(
                "/v1/emails/dev/send",
                json={
                    "to": "test@example.com",
                    "template_id": "verification",
                    "variables": {"name": "Test"},
                },
            )
            success_data = await success_response.get_json()

            # Test error response
            error_response = await client.post("/v1/emails/dev/send", json={})
            error_data = await error_response.get_json()

            # Both responses should be valid JSON dictionaries
            assert isinstance(success_data, dict)
            assert isinstance(error_data, dict)

            # Success response should have expected fields
            assert "success" in success_data
            assert "provider_message_id" in success_data
            assert "error_message" in success_data

            # Error response should have error field
            assert "error" in error_data


class TestErrorResponseFormats:
    """Test standardized error response formats across endpoints."""

    async def test_404_endpoint_not_found(self, test_app: Quart) -> None:
        """Test 404 response format for non-existent endpoints."""
        async with test_app.test_client() as client:
            response = await client.get("/v1/emails/dev/nonexistent")

            assert response.status_code == 404

    async def test_405_method_not_allowed(self, test_app: Quart) -> None:
        """Test 405 response for unsupported HTTP methods."""
        async with test_app.test_client() as client:
            # Try PATCH on GET-only endpoint
            response = await client.patch("/v1/emails/dev/templates")

            assert response.status_code == 405

    @pytest.mark.parametrize(
        "invalid_email",
        [
            "not-an-email",  # Invalid format
            "",  # Empty email
            "@missing-local.com",  # Missing local part
        ],
        ids=["invalid-format", "empty-email", "missing-local"],
    )
    async def test_invalid_email_format_handling(
        self,
        test_app: Quart,
        invalid_email: str,
    ) -> None:
        """Test that invalid email addresses are processed (API doesn't validate emails directly)."""
        async with test_app.test_client() as client:
            request_data = {
                "to": invalid_email,
                "template_id": "verification",
                "variables": {"name": "Test"},
            }
            response = await client.post("/v1/emails/dev/send", json=request_data)

            assert response.status_code == 200
            data = await response.get_json()
            assert isinstance(data, dict)
            assert "success" in data
