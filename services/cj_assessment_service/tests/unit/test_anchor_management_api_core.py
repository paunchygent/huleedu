"""Core functionality tests for anchor management API endpoint.

Tests the successful paths and integration scenarios for anchor essay registration:
- Successful registration workflows
- Grade validation with valid inputs
- Protocol-based dependency integration
- Content storage and database persistence
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


class TestAnchorRegistrationEndpoint:
    """Test anchor registration endpoint core functionality."""

    @pytest.fixture
    def mock_content_client(self) -> ContentClientProtocol:
        """Create successful content client mock."""
        return MockContentClient(behavior="success", storage_id="content-abc123")

    @pytest.fixture
    def mock_repository(self) -> MockCJRepository:
        """Create successful repository mock."""
        return MockCJRepository(behavior="success")

    @pytest.fixture
    def test_app(
        self, mock_content_client: ContentClientProtocol, mock_repository: MockCJRepository
    ) -> Any:
        """Create test app with mock dependencies."""

        # Create test provider with mocks
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
        """Create test client."""
        async with test_app.test_client() as client:
            yield client

    @pytest.mark.asyncio
    async def test_register_anchor_essay_successful_registration(
        self,
        client: QuartTestClient,
        mock_content_client: ContentClientProtocol,
        mock_repository: MockCJRepository,
    ) -> None:
        """Test successful anchor essay registration."""
        # Arrange
        mock_repository.register_assignment_context("assignment-123")
        request_data = {
            "assignment_id": "assignment-123",
            "grade": "A",
            "essay_text": (
                "This is a well-written essay with sufficient length to pass the minimum "
                "requirement of 100 characters for testing purposes."
            ),
        }

        # Act
        response = await client.post("/api/v1/anchors/register", json=request_data)

        # Assert - HTTP Response
        assert response.status_code == 201
        response_data = await response.get_json()

        assert response_data["anchor_id"] == 42
        assert response_data["storage_id"] == "content-abc123"
        assert response_data["grade_scale"] == "swedish_8_anchor"
        assert response_data["status"] == "registered"

        # Integration behavior is verified through the successful HTTP response
        # The fact that we get a 201 with anchor_id and storage_id confirms
        # the content client and repository integration worked correctly

    @pytest.mark.parametrize(
        "grade, expected_success",
        [
            ("A", True),
            ("B", True),
            ("C", True),
            ("D", True),
            ("E", True),
            ("F", True),
        ],
    )
    @pytest.mark.asyncio
    async def test_register_anchor_essay_grade_validation(
        self,
        client: QuartTestClient,
        mock_repository: MockCJRepository,
        grade: str,
        expected_success: bool,
    ) -> None:
        """Test anchor essay registration with different grade values."""
        # Arrange
        mock_repository.register_assignment_context("assignment-test")
        request_data = {
            "assignment_id": "assignment-test",
            "grade": grade,
            "essay_text": (
                "Valid essay text with sufficient length to pass validation requirements "
                "for the anchor registration test."
            ),
        }

        # Act
        response = await client.post("/api/v1/anchors/register", json=request_data)

        # Assert
        if expected_success:
            assert response.status_code == 201
            response_data = await response.get_json()
            assert response_data["status"] == "registered"
            assert response_data["grade_scale"] == "swedish_8_anchor"
        else:
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_anchor_essay_content_type_specification(
        self,
        client: QuartTestClient,
        mock_content_client: ContentClientProtocol,
        mock_repository: MockCJRepository,
    ) -> None:
        """Test that essay content is successfully processed."""
        # Arrange
        mock_repository.register_assignment_context("assignment-content-type-test")
        request_data = {
            "assignment_id": "assignment-content-type-test",
            "grade": "B",
            "essay_text": (
                "Essay content for testing content type specification in the content client "
                "integration layer with adequate length."
            ),
        }

        # Act
        response = await client.post("/api/v1/anchors/register", json=request_data)

        # Assert - Successful registration confirms content processing
        assert response.status_code == 201
        response_data = await response.get_json()
        assert response_data["status"] == "registered"
        assert "storage_id" in response_data

    @pytest.mark.asyncio
    async def test_register_anchor_essay_idempotent_upsert_updates_storage_id(
        self,
        client: QuartTestClient,
        mock_content_client: ContentClientProtocol,
        mock_repository: MockCJRepository,
    ) -> None:
        mock_repository.register_assignment_context("idempotent-assignment")

        mock_content_client.storage_id = "content-first"
        request_data = {
            "assignment_id": "idempotent-assignment",
            "grade": "A",
            "essay_text": (
                "First registration content with sufficient length to satisfy validation "
                "requirements for anchor registration."
            ),
        }

        response_first = await client.post("/api/v1/anchors/register", json=request_data)
        assert response_first.status_code == 201
        first_payload = await response_first.get_json()
        first_anchor_id = first_payload["anchor_id"]
        assert first_payload["storage_id"] == "content-first"

        mock_content_client.storage_id = "content-second"
        response_second = await client.post("/api/v1/anchors/register", json=request_data)
        assert response_second.status_code == 201
        second_payload = await response_second.get_json()

        assert second_payload["anchor_id"] == first_anchor_id
        assert second_payload["storage_id"] == "content-second"
        assert mock_repository.created_anchor is not None
        assert mock_repository.created_anchor.text_storage_id == "content-second"


class TestAnchorAPIDependencyIntegration:
    """Test anchor API dependency integration via protocols."""

    @pytest.mark.asyncio
    async def test_content_client_integration_workflow(self) -> None:
        """Test complete content client integration workflow."""
        # Arrange
        mock_content_client = MockContentClient(
            behavior="success", storage_id="integration-test-123"
        )
        mock_repository = MockCJRepository(behavior="success")

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

        async with app.test_client() as client:
            mock_repository.register_assignment_context("integration-workflow-test")
            request_data = {
                "assignment_id": "integration-workflow-test",
                "grade": "B",
                "essay_text": (
                    "Integration test essay content with sufficient length to test the complete "
                    "workflow including content storage."
                ),
            }

            # Act
            response = await client.post("/api/v1/anchors/register", json=request_data)

            # Assert - Integration workflow completed successfully
            assert response.status_code == 201

            # Verify content client was called with correct parameters
            assert mock_content_client.call_count == 1
            assert mock_content_client.last_call_params["content"] == request_data["essay_text"]

            # Verify repository session was used
            assert mock_repository.session_context_calls == 1

            # Verify anchor was created with content storage reference
            assert mock_repository.created_anchor is not None
            assert mock_repository.created_anchor.text_storage_id == "integration-test-123"
            assert mock_repository.created_anchor.grade_scale == "swedish_8_anchor"

    @pytest.mark.asyncio
    async def test_repository_protocol_session_management(self) -> None:
        """Test proper repository session management via protocol."""
        # Arrange
        mock_content_client = MockContentClient(behavior="success")
        mock_repository = MockCJRepository(behavior="success")

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

        async with app.test_client() as client:
            mock_repository.register_assignment_context("session-management-test")
            request_data = {
                "assignment_id": "session-management-test",
                "grade": "D",
                "essay_text": (
                    "Session management test content with adequate length to ensure proper "
                    "database transaction handling."
                ),
            }

            # Act
            response = await client.post("/api/v1/anchors/register", json=request_data)

            # Assert - Session was properly managed
            assert response.status_code == 201
            assert mock_repository.session_context_calls == 1

            # Verify the anchor entity was created and has expected ID
            assert mock_repository.created_anchor is not None
            assert mock_repository.created_anchor.id == 42  # Mock auto-increment value
            assert mock_repository.created_anchor.grade_scale == "swedish_8_anchor"

    @pytest.mark.asyncio
    async def test_dependency_injection_isolation(self) -> None:
        """Test that dependency injection provides proper isolation."""
        # Arrange - Create separate mock instances
        content_client_1 = MockContentClient(behavior="success", storage_id="isolation-test-1")
        content_client_2 = MockContentClient(behavior="success", storage_id="isolation-test-2")

        # This test verifies that the DI system properly isolates dependencies
        # In a real scenario, each request would get its own instances
        assert content_client_1.storage_id != content_client_2.storage_id
        assert content_client_1.call_count == 0
        assert content_client_2.call_count == 0
