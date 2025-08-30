"""
Unit tests for CircuitBreakerContentServiceClient wrapper.

Tests circuit breaker wrapper functionality for Content Service operations.
Follows HuleEdu testing excellence patterns with proper type safety.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError
from huleedu_service_libs.resilience.content_service import CircuitBreakerContentServiceClient


class MockContentServiceClient:
    """Mock Content Service client for testing wrapper behavior."""

    def __init__(self) -> None:
        self.call_history: list[tuple[str, tuple, dict]] = []
        self.should_fail = False
        self.stored_content: dict[str, str] = {}
        self.next_storage_id = "storage_123"

    async def fetch_content(
        self,
        storage_id: str,
        correlation_id,
        essay_id: str | None = None,
    ) -> str:
        """Mock fetch content method."""
        self.call_history.append(
            ("fetch_content", (storage_id, correlation_id), {"essay_id": essay_id})
        )
        if self.should_fail:
            raise ValueError(f"Failed to fetch content for storage_id: {storage_id}")

        # Return stored content or default
        return self.stored_content.get(storage_id, f"mock_content_for_{storage_id}")

    async def store_content(
        self,
        content: str,
        content_type: ContentType,
        correlation_id,
        essay_id: str | None = None,
    ) -> str:
        """Mock store content method."""
        self.call_history.append(
            ("store_content", (content, content_type, correlation_id), {"essay_id": essay_id})
        )
        if self.should_fail:
            raise ValueError(f"Failed to store content of type: {content_type}")

        # Store content and return storage ID
        storage_id = self.next_storage_id
        self.stored_content[storage_id] = content
        return storage_id

    def reset(self) -> None:
        """Reset mock state."""
        self.call_history.clear()
        self.stored_content.clear()
        self.should_fail = False
        self.next_storage_id = "storage_123"


@pytest.fixture
def mock_content_client() -> MockContentServiceClient:
    """Provide mock Content Service client for testing."""
    return MockContentServiceClient()


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Provide circuit breaker with test configuration."""
    return CircuitBreaker(
        failure_threshold=2,
        success_threshold=1,
        expected_exception=ValueError,
        name="test_content_circuit",
    )


@pytest.fixture
def circuit_breaker_client(
    mock_content_client: MockContentServiceClient, circuit_breaker: CircuitBreaker
) -> CircuitBreakerContentServiceClient:
    """Provide circuit breaker Content Service client for testing."""
    return CircuitBreakerContentServiceClient(mock_content_client, circuit_breaker)


class TestCircuitBreakerContentServiceClientConstruction:
    """Test wrapper construction and basic functionality."""

    def test_wrapper_initialization(
        self, mock_content_client: MockContentServiceClient, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test CircuitBreakerContentServiceClient initialization."""
        wrapper = CircuitBreakerContentServiceClient(mock_content_client, circuit_breaker)

        # Verify wrapper has expected structure
        assert hasattr(wrapper, "_delegate")
        assert hasattr(wrapper, "_circuit_breaker")
        assert wrapper._delegate is mock_content_client
        assert wrapper._circuit_breaker is circuit_breaker


class TestContentOperationsWithCircuitBreaker:
    """Test Content Service operations through circuit breaker."""

    @pytest.mark.asyncio
    async def test_fetch_content_success(
        self,
        circuit_breaker_client: CircuitBreakerContentServiceClient,
        mock_content_client: MockContentServiceClient,
    ) -> None:
        """Test successful content fetch through circuit breaker."""
        correlation_id = uuid4()
        storage_id = "test_storage_123"
        essay_id = "essay_456"

        result = await circuit_breaker_client.fetch_content(
            storage_id, correlation_id, essay_id=essay_id
        )

        assert result == "mock_content_for_test_storage_123"
        assert len(mock_content_client.call_history) == 1
        call = mock_content_client.call_history[0]
        assert call[0] == "fetch_content"
        assert call[1] == (storage_id, correlation_id)
        assert call[2]["essay_id"] == essay_id

    @pytest.mark.asyncio
    async def test_store_content_success(
        self,
        circuit_breaker_client: CircuitBreakerContentServiceClient,
        mock_content_client: MockContentServiceClient,
    ) -> None:
        """Test successful content storage through circuit breaker."""
        correlation_id = uuid4()
        content = "This is test essay content for storage."
        content_type = ContentType.ORIGINAL_ESSAY
        essay_id = "essay_789"

        result = await circuit_breaker_client.store_content(
            content, content_type, correlation_id, essay_id=essay_id
        )

        assert result == "storage_123"  # Mock returns this storage ID
        assert len(mock_content_client.call_history) == 1
        call = mock_content_client.call_history[0]
        assert call[0] == "store_content"
        assert call[1] == (content, content_type, correlation_id)
        assert call[2]["essay_id"] == essay_id

    @pytest.mark.asyncio
    async def test_fetch_without_essay_id(
        self,
        circuit_breaker_client: CircuitBreakerContentServiceClient,
        mock_content_client: MockContentServiceClient,
    ) -> None:
        """Test content fetch without essay ID."""
        correlation_id = uuid4()
        storage_id = "test_storage_no_essay"

        result = await circuit_breaker_client.fetch_content(storage_id, correlation_id)

        assert result == "mock_content_for_test_storage_no_essay"
        assert len(mock_content_client.call_history) == 1
        call = mock_content_client.call_history[0]
        assert call[2]["essay_id"] is None

    @pytest.mark.asyncio
    async def test_store_without_essay_id(
        self,
        circuit_breaker_client: CircuitBreakerContentServiceClient,
        mock_content_client: MockContentServiceClient,
    ) -> None:
        """Test content storage without essay ID."""
        correlation_id = uuid4()
        content = "General content without essay association."
        content_type = ContentType.PROCESSING_LOG

        result = await circuit_breaker_client.store_content(content, content_type, correlation_id)

        assert result == "storage_123"
        assert len(mock_content_client.call_history) == 1
        call = mock_content_client.call_history[0]
        assert call[2]["essay_id"] is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_error_propagation(
        self,
        circuit_breaker_client: CircuitBreakerContentServiceClient,
        mock_content_client: MockContentServiceClient,
    ) -> None:
        """Test that Content Service errors are properly propagated."""
        correlation_id = uuid4()
        storage_id = "failing_storage"
        mock_content_client.should_fail = True

        with pytest.raises(
            ValueError, match="Failed to fetch content for storage_id: failing_storage"
        ):
            await circuit_breaker_client.fetch_content(storage_id, correlation_id)

        assert len(mock_content_client.call_history) == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(
        self,
        circuit_breaker_client: CircuitBreakerContentServiceClient,
        mock_content_client: MockContentServiceClient,
    ) -> None:
        """Test circuit breaker opens after threshold failures."""
        correlation_id = uuid4()

        # First success
        result = await circuit_breaker_client.fetch_content("success_storage", correlation_id)
        assert result == "mock_content_for_success_storage"

        # Enable failures and hit threshold (2 failures)
        mock_content_client.should_fail = True
        for i in range(2):
            with pytest.raises(ValueError):
                await circuit_breaker_client.fetch_content(f"fail_storage_{i}", correlation_id)

        # Circuit should now be open - next call blocked
        with pytest.raises(CircuitBreakerError):
            await circuit_breaker_client.fetch_content("blocked_storage", correlation_id)

        # Verify the blocked call didn't reach the mock (1 success + 2 failures = 3 total)
        assert len(mock_content_client.call_history) == 3


class TestProtocolCompliance:
    """Test CircuitBreakerContentServiceClient properly implements ContentServiceClientProtocol.
    """

    def test_implements_protocol(
        self, circuit_breaker_client: CircuitBreakerContentServiceClient
    ) -> None:
        """Test that the wrapper properly implements the protocol."""
        # Should have required methods from ContentServiceClientProtocol
        assert hasattr(circuit_breaker_client, "fetch_content")
        assert hasattr(circuit_breaker_client, "store_content")
        assert callable(circuit_breaker_client.fetch_content)
        assert callable(circuit_breaker_client.store_content)


class TestContentTypeHandling:
    """Test different content types through the circuit breaker."""

    @pytest.mark.asyncio
    async def test_different_content_types(
        self,
        circuit_breaker_client: CircuitBreakerContentServiceClient,
        mock_content_client: MockContentServiceClient,
    ) -> None:
        """Test storing different content types."""
        correlation_id = uuid4()

        # Test each content type
        content_types = [
            ContentType.ORIGINAL_ESSAY,
            ContentType.PROCESSING_LOG,
            ContentType.NLP_METRICS_JSON,
            ContentType.CORRECTED_TEXT,
        ]

        storage_ids = []
        for i, content_type in enumerate(content_types):
            mock_content_client.next_storage_id = f"storage_{i + 1}"
            content = f"Content for {content_type.value}"

            storage_id = await circuit_breaker_client.store_content(
                content, content_type, correlation_id
            )
            storage_ids.append(storage_id)

        # Verify all types were processed
        assert len(storage_ids) == 4
        assert len(mock_content_client.call_history) == 4

        # Verify content types in history
        for i, content_type in enumerate(content_types):
            call = mock_content_client.call_history[i]
            assert call[1][1] == content_type  # content_type parameter


class TestRoundTripOperations:
    """Test storing and fetching content through circuit breaker."""

    @pytest.mark.asyncio
    async def test_store_and_fetch_roundtrip(
        self,
        circuit_breaker_client: CircuitBreakerContentServiceClient,
        mock_content_client: MockContentServiceClient,
    ) -> None:
        """Test complete store and fetch cycle."""
        correlation_id = uuid4()
        original_content = "This is a test essay that will be stored and retrieved."
        content_type = ContentType.ORIGINAL_ESSAY
        essay_id = "roundtrip_essay"

        # Store content
        storage_id = await circuit_breaker_client.store_content(
            original_content, content_type, correlation_id, essay_id=essay_id
        )
        assert storage_id == "storage_123"

        # Fetch content back
        retrieved_content = await circuit_breaker_client.fetch_content(
            storage_id, correlation_id, essay_id=essay_id
        )

        # Should get the same content back (mock stores it)
        assert retrieved_content == original_content
        assert len(mock_content_client.call_history) == 2

    @pytest.mark.asyncio
    async def test_mixed_operations_with_circuit_breaker(
        self,
        circuit_breaker_client: CircuitBreakerContentServiceClient,
        mock_content_client: MockContentServiceClient,
    ) -> None:
        """Test mixed store/fetch operations with some failures."""
        correlation_id = uuid4()

        # Successful store
        storage_id = await circuit_breaker_client.store_content(
            "Success content", ContentType.ORIGINAL_ESSAY, correlation_id
        )
        assert storage_id == "storage_123"

        # Successful fetch
        content = await circuit_breaker_client.fetch_content(storage_id, correlation_id)
        assert content == "Success content"

        # One failure (won't trigger circuit breaker yet)
        mock_content_client.should_fail = True
        with pytest.raises(ValueError):
            await circuit_breaker_client.fetch_content("fail_storage", correlation_id)

        # Successful operation should still work (circuit not open)
        mock_content_client.should_fail = False
        content2 = await circuit_breaker_client.fetch_content(storage_id, correlation_id)
        assert content2 == "Success content"

        # Verify all operations were attempted
        assert len(mock_content_client.call_history) == 4
