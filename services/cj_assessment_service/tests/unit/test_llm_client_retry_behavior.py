"""Unit tests for LLM Provider Service client retry behavior."""

import json
from unittest.mock import MagicMock

import aiohttp
import pytest

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
)
from services.cj_assessment_service.implementations.retry_manager_impl import RetryManagerImpl


class MockResponse:
    """Mock HTTP response."""

    def __init__(self, status: int, text: str, request_info=None):
        self.status = status
        self._text = text
        self.request_info = request_info or MagicMock()
        self.history = []
        self.headers = {}

    async def text(self):
        return self._text

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=self.request_info,
                history=self.history,
                status=self.status,
                message=f"HTTP {self.status}",
            )


class TestLLMClientRetryBehavior:
    """Test retry behavior for different error scenarios."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings."""
        settings = Settings()
        settings.LLM_PROVIDER_SERVICE_URL = "http://test-llm-service/api/v1"
        settings.llm_retry_enabled = True
        settings.llm_retry_attempts = 3
        settings.llm_retry_wait_min_seconds = 0.1  # Fast retries for tests
        settings.llm_retry_wait_max_seconds = 0.5
        return settings

    @pytest.fixture
    def retry_manager(self, settings: Settings) -> RetryManagerImpl:
        """Create retry manager."""
        return RetryManagerImpl(settings)

    @pytest.fixture
    def test_prompt(self) -> str:
        """Create test prompt."""
        return """Compare these two essays and determine which is better written.
Essay A (ID: test-123):
This is a test essay A with good structure.

Essay B (ID: test-456):
This is test essay B with different qualities.

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation of your decision
- 'confidence': Rating from 1-5 (5 = very confident)"""

    async def test_retryable_503_error_with_json_body(
        self,
        settings: Settings,
        retry_manager: RetryManagerImpl,
        test_prompt: str,
    ):
        """Test that 503 errors with is_retryable=true trigger retries."""
        # Create mock session
        mock_session = MagicMock(spec=aiohttp.ClientSession)

        # Track number of calls
        call_count = 0

        # Create error response
        error_response = MockResponse(
            status=503,
            text=json.dumps(
                {
                    "error": "Mock provider simulated error",
                    "error_type": "EXTERNAL_SERVICE_ERROR",
                    "is_retryable": True,
                    "correlation_id": "test-123",
                }
            ),
        )

        # Create success response
        success_response = MockResponse(
            status=200,
            text=json.dumps(
                {
                    "winner": "Essay A",
                    "justification": "Better structure",
                    "confidence": 4.5,
                    "provider": "mock",
                    "model": "mock-model",
                }
            ),
        )

        # Mock post method - must be a regular function, not async
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Context manager mock
            class AsyncContextManager:
                async def __aenter__(self):
                    # Fail first 2 attempts, succeed on 3rd
                    if call_count < 3:
                        return error_response
                    else:
                        return success_response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return False

            return AsyncContextManager()

        mock_session.post = mock_post

        # Create client and make request
        client = LLMProviderServiceClient(
            session=mock_session, settings=settings, retry_manager=retry_manager
        )

        result, error = await client.generate_comparison(test_prompt)

        # Verify retries happened
        assert call_count == 3, f"Expected 3 calls (2 failures + 1 success), got {call_count}"
        assert error is None
        assert result is not None
        assert result["winner"] == "Essay A"

    async def test_retryable_500_error_without_json(
        self,
        settings: Settings,
        retry_manager: RetryManagerImpl,
        test_prompt: str,
    ):
        """Test that 500 errors without JSON body trigger retries."""
        # Create mock session
        mock_session = MagicMock(spec=aiohttp.ClientSession)

        # Track number of calls
        call_count = 0

        # Create error response
        error_response = MockResponse(status=500, text="Internal Server Error")

        # Mock post method - must be a regular function, not async
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Context manager mock
            class AsyncContextManager:
                async def __aenter__(self):
                    return error_response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return False

            return AsyncContextManager()

        mock_session.post = mock_post

        # Create client and make request
        client = LLMProviderServiceClient(
            session=mock_session, settings=settings, retry_manager=retry_manager
        )

        # Expect failure after all retries
        result, error = await client.generate_comparison(test_prompt)

        # Verify all retry attempts were made
        assert call_count == 3, f"Expected 3 retry attempts, got {call_count}"
        assert result is None
        assert error is not None
        assert "500" in error or "Internal Server Error" in error

    async def test_non_retryable_400_error(
        self,
        settings: Settings,
        retry_manager: RetryManagerImpl,
        test_prompt: str,
    ):
        """Test that 400 errors do not trigger retries."""
        # Create mock session
        mock_session = MagicMock(spec=aiohttp.ClientSession)

        # Track number of calls
        call_count = 0

        # Create error response
        error_response = MockResponse(
            status=400, text=json.dumps({"error": "Invalid request format", "is_retryable": False})
        )

        # Mock post method - must be a regular function, not async
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Context manager mock
            class AsyncContextManager:
                async def __aenter__(self):
                    return error_response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return False

            return AsyncContextManager()

        mock_session.post = mock_post

        # Create client and make request
        client = LLMProviderServiceClient(
            session=mock_session, settings=settings, retry_manager=retry_manager
        )

        result, error = await client.generate_comparison(test_prompt)

        # Verify no retries for non-retryable error
        assert call_count == 1, f"Expected 1 call (no retries), got {call_count}"
        assert result is None
        assert error is not None
        assert "Invalid request format" in error

    async def test_network_connection_error_retries(
        self,
        settings: Settings,
        retry_manager: RetryManagerImpl,
        test_prompt: str,
    ):
        """Test that network connection errors trigger retries."""
        # Create mock session
        mock_session = MagicMock(spec=aiohttp.ClientSession)

        # Track number of calls
        call_count = 0

        # Mock post method to raise connection error
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise aiohttp.ClientConnectionError("Connection refused")

        mock_session.post = mock_post

        # Create client and make request
        client = LLMProviderServiceClient(
            session=mock_session, settings=settings, retry_manager=retry_manager
        )

        result, error = await client.generate_comparison(test_prompt)

        # Verify retries happened for connection error
        assert call_count == 3, f"Expected 3 retry attempts, got {call_count}"
        assert result is None
        assert error is not None
        assert "Connection refused" in error or "client error" in error.lower()

    async def test_timeout_error_retries(
        self,
        settings: Settings,
        retry_manager: RetryManagerImpl,
        test_prompt: str,
    ):
        """Test that timeout errors trigger retries."""
        # Create mock session
        mock_session = MagicMock(spec=aiohttp.ClientSession)

        # Track number of calls
        call_count = 0

        # Mock post method to raise timeout
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise aiohttp.ServerTimeoutError("Request timeout")

        mock_session.post = mock_post

        # Create client and make request
        client = LLMProviderServiceClient(
            session=mock_session, settings=settings, retry_manager=retry_manager
        )

        result, error = await client.generate_comparison(test_prompt)

        # Verify retries happened for timeout
        assert call_count == 3, f"Expected 3 retry attempts, got {call_count}"
        assert result is None
        assert error is not None

    async def test_successful_response_no_retries(
        self,
        settings: Settings,
        retry_manager: RetryManagerImpl,
        test_prompt: str,
    ):
        """Test that successful responses don't trigger retries."""
        # Create mock session
        mock_session = MagicMock(spec=aiohttp.ClientSession)

        # Track number of calls
        call_count = 0

        # Create success response
        success_response = MockResponse(
            status=200,
            text=json.dumps(
                {
                    "winner": "Essay B",
                    "justification": "More compelling argument",
                    "confidence": 4.2,
                    "provider": "anthropic",
                    "model": "claude-3-haiku",
                }
            ),
        )

        # Mock post method - must be a regular function, not async
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Context manager mock
            class AsyncContextManager:
                async def __aenter__(self):
                    return success_response

                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return False

            return AsyncContextManager()

        mock_session.post = mock_post

        # Create client and make request
        client = LLMProviderServiceClient(
            session=mock_session, settings=settings, retry_manager=retry_manager
        )

        result, error = await client.generate_comparison(test_prompt)

        # Verify no retries for success
        assert call_count == 1, f"Expected 1 call (no retries), got {call_count}"
        assert error is None
        assert result is not None
        assert result["winner"] == "Essay B"
        assert result["confidence"] == 4.2
