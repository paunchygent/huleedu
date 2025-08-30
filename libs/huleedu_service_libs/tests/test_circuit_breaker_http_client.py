"""
Unit tests for CircuitBreakerHttpClient wrapper.

Tests circuit breaker wrapper functionality for HTTP client operations.
Follows HuleEdu testing excellence patterns with proper type safety.
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError
from huleedu_service_libs.resilience.http_client import CircuitBreakerHttpClient


class MockHttpClient:
    """Mock HTTP client for testing wrapper behavior."""

    def __init__(self) -> None:
        self.call_history: list[tuple[str, tuple, dict]] = []
        self.should_fail = False

    async def get(
        self,
        url: str,
        correlation_id,
        timeout_seconds: int = 10,
        headers: dict[str, str] | None = None,
        **context,
    ) -> str:
        """Mock GET method."""
        self.call_history.append(("get", (url, correlation_id, timeout_seconds), {"headers": headers, **context}))
        if self.should_fail:
            raise ValueError(f"HTTP GET failed for {url}")
        return f"response_from_{url}"

    async def post(
        self,
        url: str,
        data: bytes | str,
        correlation_id,
        timeout_seconds: int = 10,
        headers: dict[str, str] | None = None,
        **context,
    ) -> dict[str, str]:
        """Mock POST method."""
        self.call_history.append(("post", (url, data, correlation_id, timeout_seconds), {"headers": headers, **context}))
        if self.should_fail:
            raise ValueError(f"HTTP POST failed for {url}")
        return {"result": f"post_response_{url}", "data_length": len(data) if isinstance(data, (str, bytes)) else 0}

    def reset(self) -> None:
        """Reset mock state."""
        self.call_history.clear()
        self.should_fail = False


@pytest.fixture
def mock_http_client() -> MockHttpClient:
    """Provide mock HTTP client for testing."""
    return MockHttpClient()


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Provide circuit breaker with test configuration."""
    return CircuitBreaker(
        failure_threshold=2,
        success_threshold=1,
        expected_exception=ValueError,
        name="test_http_circuit",
    )


@pytest.fixture
def circuit_breaker_client(
    mock_http_client: MockHttpClient, circuit_breaker: CircuitBreaker
) -> CircuitBreakerHttpClient:
    """Provide circuit breaker HTTP client for testing."""
    return CircuitBreakerHttpClient(mock_http_client, circuit_breaker)


class TestCircuitBreakerHttpClientConstruction:
    """Test wrapper construction and basic functionality."""

    def test_wrapper_initialization(
        self, mock_http_client: MockHttpClient, circuit_breaker: CircuitBreaker
    ) -> None:
        """Test CircuitBreakerHttpClient initialization."""
        wrapper = CircuitBreakerHttpClient(mock_http_client, circuit_breaker)

        # Verify wrapper has expected structure
        assert hasattr(wrapper, "_delegate")
        assert hasattr(wrapper, "_circuit_breaker")
        assert wrapper._delegate is mock_http_client
        assert wrapper._circuit_breaker is circuit_breaker


class TestHttpOperationsWithCircuitBreaker:
    """Test HTTP operations through circuit breaker."""

    @pytest.mark.asyncio
    async def test_get_success(self, circuit_breaker_client: CircuitBreakerHttpClient, mock_http_client: MockHttpClient) -> None:
        """Test successful GET request through circuit breaker."""
        correlation_id = uuid4()
        url = "https://example.com/api/test"

        result = await circuit_breaker_client.get(url, correlation_id, timeout_seconds=30)

        assert result == "response_from_https://example.com/api/test"
        assert len(mock_http_client.call_history) == 1
        call = mock_http_client.call_history[0]
        assert call[0] == "get"
        assert call[1] == (url, correlation_id, 30)

    @pytest.mark.asyncio
    async def test_post_success(self, circuit_breaker_client: CircuitBreakerHttpClient, mock_http_client: MockHttpClient) -> None:
        """Test successful POST request through circuit breaker."""
        correlation_id = uuid4()
        url = "https://example.com/api/submit"
        data = "test payload"

        result = await circuit_breaker_client.post(url, data, correlation_id, timeout_seconds=45, headers={"Content-Type": "text/plain"})

        expected_response = {"result": "post_response_https://example.com/api/submit", "data_length": 12}
        assert result == expected_response
        assert len(mock_http_client.call_history) == 1
        call = mock_http_client.call_history[0]
        assert call[0] == "post"
        assert call[1] == (url, data, correlation_id, 45)
        assert call[2]["headers"] == {"Content-Type": "text/plain"}

    @pytest.mark.asyncio
    async def test_get_with_context(self, circuit_breaker_client: CircuitBreakerHttpClient, mock_http_client: MockHttpClient) -> None:
        """Test GET request with additional context parameters."""
        correlation_id = uuid4()
        url = "https://example.com/api/context-test"

        result = await circuit_breaker_client.get(
            url, 
            correlation_id, 
            timeout_seconds=20, 
            headers={"Authorization": "Bearer token"}, 
            service_context="test_service",
            operation_id="op_123"
        )

        assert result == "response_from_https://example.com/api/context-test"
        assert len(mock_http_client.call_history) == 1
        call = mock_http_client.call_history[0]
        assert call[2]["service_context"] == "test_service"
        assert call[2]["operation_id"] == "op_123"

    @pytest.mark.asyncio
    async def test_circuit_breaker_error_propagation(
        self, circuit_breaker_client: CircuitBreakerHttpClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test that HTTP errors are properly propagated."""
        correlation_id = uuid4()
        url = "https://example.com/api/fail"
        mock_http_client.should_fail = True

        with pytest.raises(ValueError, match="HTTP GET failed for https://example.com/api/fail"):
            await circuit_breaker_client.get(url, correlation_id)

        assert len(mock_http_client.call_history) == 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(
        self, circuit_breaker_client: CircuitBreakerHttpClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test circuit breaker opens after threshold failures."""
        correlation_id = uuid4()
        url = "https://example.com/api/unstable"

        # First success
        result = await circuit_breaker_client.get(url, correlation_id)
        assert result == "response_from_https://example.com/api/unstable"

        # Enable failures and hit threshold (2 failures)
        mock_http_client.should_fail = True
        for i in range(2):
            with pytest.raises(ValueError):
                await circuit_breaker_client.get(f"{url}/{i}", correlation_id)

        # Circuit should now be open - next call blocked
        with pytest.raises(CircuitBreakerError):
            await circuit_breaker_client.get(url, correlation_id)

        # Verify the blocked call didn't reach the mock (1 success + 2 failures = 3 total)
        assert len(mock_http_client.call_history) == 3


class TestProtocolCompliance:
    """Test that CircuitBreakerHttpClient properly implements HttpClientProtocol."""

    def test_implements_protocol(self, circuit_breaker_client: CircuitBreakerHttpClient) -> None:
        """Test that the wrapper properly implements the protocol."""
        # Should have required methods from HttpClientProtocol
        assert hasattr(circuit_breaker_client, "get")
        assert hasattr(circuit_breaker_client, "post")
        assert callable(circuit_breaker_client.get)
        assert callable(circuit_breaker_client.post)


class TestErrorHandlingEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_mixed_success_failure_patterns(
        self, circuit_breaker_client: CircuitBreakerHttpClient, mock_http_client: MockHttpClient
    ) -> None:
        """Test mixed success/failure patterns with circuit breaker."""
        correlation_id = uuid4()

        # Success
        result1 = await circuit_breaker_client.get("https://api.com/1", correlation_id)
        assert result1 == "response_from_https://api.com/1"

        # Failure
        mock_http_client.should_fail = True
        with pytest.raises(ValueError):
            await circuit_breaker_client.get("https://api.com/fail", correlation_id)

        # Success again (should reset failure count)
        mock_http_client.should_fail = False
        result2 = await circuit_breaker_client.get("https://api.com/2", correlation_id)
        assert result2 == "response_from_https://api.com/2"

        # Verify all calls reached the mock
        assert len(mock_http_client.call_history) == 3

    @pytest.mark.asyncio
    async def test_bytes_data_post(self, circuit_breaker_client: CircuitBreakerHttpClient, mock_http_client: MockHttpClient) -> None:
        """Test POST request with bytes data."""
        correlation_id = uuid4()
        url = "https://example.com/api/binary"
        data = b"binary payload"

        result = await circuit_breaker_client.post(url, data, correlation_id)

        expected_response = {"result": "post_response_https://example.com/api/binary", "data_length": 14}
        assert result == expected_response
        assert len(mock_http_client.call_history) == 1
        call = mock_http_client.call_history[0]
        assert call[1] == (url, data, correlation_id, 10)  # Default timeout