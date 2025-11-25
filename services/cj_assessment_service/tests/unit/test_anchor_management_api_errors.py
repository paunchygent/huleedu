"""Error handling tests for anchor management API endpoint.

Tests error scenarios and failure conditions for anchor essay registration:
- Content service failures
- Database operation failures
- Missing response data handling
- Unexpected exceptions
- HTTP method validation
"""

from __future__ import annotations

import pytest
from dishka import Provider, Scope, make_async_container, provide
from quart import Quart
from quart_dishka import QuartDishka

from services.cj_assessment_service.api.anchor_management import bp
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.unit.anchor_api_test_helpers import (
    FailingMockRepository,
    MissingStorageIdClient,
    MockCJRepository,
    MockContentClient,
)


class TestAnchorAPIErrorHandling:
    """Test anchor API error handling scenarios."""

    @pytest.fixture
    def failing_content_client(self) -> MockContentClient:
        """Create content client that fails."""
        return MockContentClient(behavior="failure")

    @pytest.fixture
    def failing_repository(self) -> MockCJRepository:
        """Create repository that fails on database operations."""
        return MockCJRepository(behavior="database_failure")

    @pytest.fixture
    def missing_storage_id_client(self) -> MissingStorageIdClient:
        """Create content client that returns response without storage_id."""
        return MissingStorageIdClient()

    @pytest.mark.asyncio
    async def test_content_service_failure_handling(
        self, failing_content_client: MockContentClient
    ) -> None:
        """Test handling of content service failures."""
        # Arrange
        mock_repository = MockCJRepository(behavior="success")

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_content_client(self) -> ContentClientProtocol:
                return failing_content_client

            @provide(scope=Scope.REQUEST)
            def provide_session_provider(self) -> SessionProviderProtocol:
                return mock_repository

            @provide(scope=Scope.REQUEST)
            def provide_anchor_repository(self) -> AnchorRepositoryProtocol:
                return mock_repository

            @provide(scope=Scope.REQUEST)
            def provide_instruction_repository(self) -> AssessmentInstructionRepositoryProtocol:
                return mock_repository

        app = Quart(__name__)
        container = make_async_container(TestProvider())
        QuartDishka(app=app, container=container)
        app.register_blueprint(bp)

        async with app.test_client() as client:
            request_data = {
                "assignment_id": "content-failure-test",
                "grade": "A",
                "essay_text": (
                    "Test content for content service failure scenario with adequate length "
                    "for testing proper error handling."
                ),
            }

            # Ensure assignment context exists so workflow reaches content storage call
            mock_repository.register_assignment_context("content-failure-test")

            # Act
            response = await client.post("/api/v1/anchors/register", json=request_data)

            # Assert - Internal server error due to content service failure
            assert response.status_code == 500
            response_data = await response.get_json()
            assert "error" in response_data
            assert "Internal server error" in response_data["error"]

    @pytest.mark.asyncio
    async def test_missing_content_id_handling(
        self, missing_storage_id_client: MissingStorageIdClient
    ) -> None:
        """Test handling when content service doesn't return storage_id."""
        # Arrange
        mock_repository = MockCJRepository(behavior="success")

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_content_client(self) -> ContentClientProtocol:
                return missing_storage_id_client

            @provide(scope=Scope.REQUEST)
            def provide_session_provider(self) -> SessionProviderProtocol:
                return mock_repository

            @provide(scope=Scope.REQUEST)
            def provide_anchor_repository(self) -> AnchorRepositoryProtocol:
                return mock_repository

            @provide(scope=Scope.REQUEST)
            def provide_instruction_repository(self) -> AssessmentInstructionRepositoryProtocol:
                return mock_repository

        app = Quart(__name__)
        container = make_async_container(TestProvider())
        QuartDishka(app=app, container=container)
        app.register_blueprint(bp)

        async with app.test_client() as client:
            request_data = {
                "assignment_id": "missing-storage-id-test",
                "grade": "C",
                "essay_text": (
                    "Test content for missing storage ID scenario with sufficient length "
                    "to test error handling properly."
                ),
            }

            # Register assignment context to reach storage-id handling logic
            mock_repository.register_assignment_context("missing-storage-id-test")

            # Act
            response = await client.post("/api/v1/anchors/register", json=request_data)

            # Assert - Content service issue
            assert response.status_code == 500
            response_data = await response.get_json()
            assert "error" in response_data
            assert "Failed to store essay content" in response_data["error"]

    @pytest.mark.asyncio
    async def test_database_failure_handling(self, failing_repository: MockCJRepository) -> None:
        """Test handling of database operation failures."""
        # Arrange
        mock_content_client = MockContentClient(behavior="success")

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_content_client(self) -> ContentClientProtocol:
                return mock_content_client

            @provide(scope=Scope.REQUEST)
            def provide_session_provider(self) -> SessionProviderProtocol:
                return failing_repository

            @provide(scope=Scope.REQUEST)
            def provide_anchor_repository(self) -> AnchorRepositoryProtocol:
                return failing_repository

            @provide(scope=Scope.REQUEST)
            def provide_instruction_repository(self) -> AssessmentInstructionRepositoryProtocol:
                return failing_repository

        app = Quart(__name__)
        container = make_async_container(TestProvider())
        QuartDishka(app=app, container=container)
        app.register_blueprint(bp)

        async with app.test_client() as client:
            request_data = {
                "assignment_id": "database-failure-test",
                "grade": "E",
                "essay_text": (
                    "Test content for database failure scenario with appropriate length "
                    "to ensure proper error handling coverage."
                ),
            }

            # Register assignment context to trigger database failure path
            failing_repository.register_assignment_context("database-failure-test")

            # Act
            response = await client.post("/api/v1/anchors/register", json=request_data)

            # Assert - Database operation failure
            assert response.status_code == 500
            response_data = await response.get_json()
            assert "error" in response_data
            assert "Internal server error" in response_data["error"]

    @pytest.mark.asyncio
    async def test_general_exception_handling(self) -> None:
        """Test handling of unexpected exceptions."""
        # Arrange - Create mock that raises unexpected exception
        mock_content_client = MockContentClient(behavior="success")

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_content_client(self) -> ContentClientProtocol:
                return mock_content_client

            @provide(scope=Scope.REQUEST)
            def provide_session_provider(self) -> SessionProviderProtocol:
                return FailingMockRepository()  # type: ignore[return-value]

            @provide(scope=Scope.REQUEST)
            def provide_anchor_repository(self) -> AnchorRepositoryProtocol:
                return FailingMockRepository()  # type: ignore[return-value]

            @provide(scope=Scope.REQUEST)
            def provide_instruction_repository(self) -> AssessmentInstructionRepositoryProtocol:
                return FailingMockRepository()  # type: ignore[return-value]

        app = Quart(__name__)
        container = make_async_container(TestProvider())
        QuartDishka(app=app, container=container)
        app.register_blueprint(bp)

        async with app.test_client() as client:
            request_data = {
                "assignment_id": "unexpected-error-test",
                "grade": "F",
                "essay_text": (
                    "Test content for unexpected exception scenario with sufficient length "
                    "to trigger exception handling path."
                ),
            }

            # Act
            response = await client.post("/api/v1/anchors/register", json=request_data)

            # Assert - Unexpected exception handled
            assert response.status_code == 500
            response_data = await response.get_json()
            assert "error" in response_data
            assert "Internal server error" in response_data["error"]

    @pytest.mark.parametrize(
        "http_method",
        ["get", "put", "patch", "delete"],
    )
    @pytest.mark.asyncio
    async def test_unsupported_http_methods(self, http_method: str) -> None:
        """Test that unsupported HTTP methods return appropriate errors."""
        # Arrange
        mock_content_client = MockContentClient(behavior="success")
        mock_repository = MockCJRepository(behavior="success")

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_content_client(self) -> ContentClientProtocol:
                return mock_content_client

            @provide(scope=Scope.REQUEST)
            def provide_session_provider(self) -> SessionProviderProtocol:
                return mock_repository

            @provide(scope=Scope.REQUEST)
            def provide_anchor_repository(self) -> AnchorRepositoryProtocol:
                return mock_repository

            @provide(scope=Scope.REQUEST)
            def provide_instruction_repository(self) -> AssessmentInstructionRepositoryProtocol:
                return mock_repository

        app = Quart(__name__)
        container = make_async_container(TestProvider())
        QuartDishka(app=app, container=container)
        app.register_blueprint(bp)

        async with app.test_client() as client:
            # Act
            response = await getattr(client, http_method)("/api/v1/anchors/register")

            # Assert - Method not allowed
            assert response.status_code == 405
