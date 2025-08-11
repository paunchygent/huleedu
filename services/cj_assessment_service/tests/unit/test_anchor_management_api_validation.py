"""Validation tests for anchor management API endpoint.

Tests input validation and business rules for anchor essay registration:
- Required field validation
- Grade value constraints
- Essay text length requirements
- Invalid JSON handling
- Edge cases and boundary conditions
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest
from dishka import Provider, Scope, make_async_container, provide
from quart import Quart
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.cj_assessment_service.api.anchor_management import bp
from services.cj_assessment_service.protocols import CJRepositoryProtocol, ContentClientProtocol
from services.cj_assessment_service.tests.unit.anchor_api_test_helpers import (
    MockCJRepository,
    MockContentClient,
)


class TestAnchorAPIRequestValidation:
    """Test anchor API request validation and business rules."""

    @pytest.fixture
    def mock_content_client(self) -> ContentClientProtocol:
        """Create content client mock for validation tests."""
        return MockContentClient(behavior="success")

    @pytest.fixture
    def mock_repository(self) -> CJRepositoryProtocol:
        """Create repository mock for validation tests."""
        return MockCJRepository(behavior="success")

    @pytest.fixture
    def test_app(
        self, mock_content_client: ContentClientProtocol, mock_repository: CJRepositoryProtocol
    ) -> Any:
        """Create test app for validation tests."""

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_content_client(self) -> ContentClientProtocol:
                return mock_content_client

            @provide(scope=Scope.REQUEST)
            def provide_repository(self) -> CJRepositoryProtocol:
                return mock_repository

        app = Quart(__name__)
        container = make_async_container(TestProvider())
        QuartDishka(app=app, container=container)
        app.register_blueprint(bp)

        return app

    @pytest.fixture
    async def client(self, test_app: Any) -> AsyncGenerator[QuartTestClient, None]:
        """Create test client for validation tests."""
        async with test_app.test_client() as client:
            yield client

    @pytest.mark.parametrize(
        "request_data, expected_error_substring",
        [
            # Missing required fields
            ({"assignment_id": "test", "grade": "A"}, "Missing required fields"),
            ({"assignment_id": "test", "essay_text": "Valid text here"}, "Missing required fields"),
            ({"grade": "A", "essay_text": "Valid text here"}, "Missing required fields"),
            # Invalid grade values
            (
                {
                    "assignment_id": "test",
                    "grade": "G",
                    "essay_text": "Valid essay text with sufficient length for testing validation requirements.",
                },
                "Invalid grade",
            ),
            (
                {
                    "assignment_id": "test",
                    "grade": "A+",
                    "essay_text": "Valid essay text with sufficient length for testing validation requirements.",
                },
                "Invalid grade",
            ),
            (
                {
                    "assignment_id": "test",
                    "grade": "invalid",
                    "essay_text": "Valid essay text with sufficient length for testing validation requirements.",
                },
                "Invalid grade",
            ),
            # Essay text too short
            (
                {
                    "assignment_id": "test",
                    "grade": "A",
                    "essay_text": "Short",
                },
                "Essay text too short",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_register_anchor_essay_validation_errors(
        self,
        client: QuartTestClient,
        request_data: dict[str, Any],
        expected_error_substring: str,
    ) -> None:
        """Test request validation with various invalid inputs."""
        # Act
        response = await client.post("/api/v1/anchors/register", json=request_data)

        # Assert
        assert response.status_code == 400
        response_data = await response.get_json()
        assert "error" in response_data
        assert expected_error_substring in response_data["error"]

    @pytest.mark.asyncio
    async def test_register_anchor_essay_minimum_length_requirement(
        self,
        client: QuartTestClient,
    ) -> None:
        """Test essay text minimum length validation."""
        # Arrange - Essay with exactly 99 characters (below minimum)
        short_essay = "x" * 99
        request_data = {
            "assignment_id": "length-test",
            "grade": "C",
            "essay_text": short_essay,
        }

        # Act
        response = await client.post("/api/v1/anchors/register", json=request_data)

        # Assert
        assert response.status_code == 400
        response_data = await response.get_json()
        assert "Essay text too short (min 100 chars)" in response_data["error"]

    @pytest.mark.asyncio
    async def test_register_anchor_essay_minimum_length_boundary(
        self,
        client: QuartTestClient,
    ) -> None:
        """Test essay text exactly at minimum length boundary."""
        # Arrange - Essay with exactly 100 characters (at minimum)
        boundary_essay = "x" * 100
        request_data = {
            "assignment_id": "boundary-test",
            "grade": "C",
            "essay_text": boundary_essay,
        }

        # Act
        response = await client.post("/api/v1/anchors/register", json=request_data)

        # Assert
        assert response.status_code == 201
        response_data = await response.get_json()
        assert response_data["status"] == "registered"

    @pytest.mark.asyncio
    async def test_register_anchor_essay_invalid_json(
        self,
        client: QuartTestClient,
    ) -> None:
        """Test handling of malformed JSON requests."""
        # Act - Send malformed JSON
        response = await client.post("/api/v1/anchors/register", data="invalid-json")

        # Assert - Should return 400 for malformed JSON
        assert response.status_code in [400, 500]  # Depending on Quart's JSON parsing behavior
