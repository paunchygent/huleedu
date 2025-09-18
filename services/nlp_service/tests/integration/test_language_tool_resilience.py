"""Integration tests for LanguageToolServiceClient resilience patterns.

These tests verify circuit breaker behavior, retry logic, and graceful degradation
patterns work correctly with real CircuitBreaker instances and mocked HTTP responses.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import AsyncGenerator

import aiohttp
import pytest
from aioresponses import aioresponses
from common_core.events.nlp_events import GrammarAnalysis
from common_core.status_enums import CircuitBreakerState
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

from services.nlp_service.config import Settings
from services.nlp_service.implementations.language_tool_client_impl import (
    LanguageToolServiceClient,
)


@pytest.mark.integration
class TestLanguageToolServiceClientResilience:
    """Integration tests for LanguageToolServiceClient resilience patterns."""

    @pytest.fixture
    def test_settings(self) -> Settings:
        """Provide test settings with resilience configuration."""
        settings = Settings()
        # Override for faster testing
        settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
        settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 30  # seconds
        settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2
        settings.LANGUAGE_TOOL_REQUEST_TIMEOUT = 30
        settings.LANGUAGE_TOOL_MAX_RETRIES = 3
        settings.LANGUAGE_TOOL_RETRY_DELAY = 0.5  # 0.5s, 1s, 2s exponential backoff
        settings.LANGUAGE_TOOL_SERVICE_URL = "http://language-tool-test:8085"
        settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_ENABLED = True
        return settings

    @pytest.fixture
    def circuit_breaker(self, test_settings: Settings) -> CircuitBreaker:
        """Provide real CircuitBreaker for testing."""
        return CircuitBreaker(
            name="language_tool_service",
            failure_threshold=test_settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=timedelta(
                seconds=test_settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT
            ),
            success_threshold=test_settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
            expected_exception=HuleEduError,
            service_name="nlp_service",
        )

    @pytest.fixture
    def client_with_circuit_breaker(
        self, test_settings: Settings, circuit_breaker: CircuitBreaker
    ) -> LanguageToolServiceClient:
        """Provide LanguageToolServiceClient with attached circuit breaker."""
        client = LanguageToolServiceClient(test_settings)
        client._circuit_breaker = circuit_breaker  # type: ignore[attr-defined]
        return client

    @pytest.fixture
    def client_without_circuit_breaker(self, test_settings: Settings) -> LanguageToolServiceClient:
        """Provide LanguageToolServiceClient without circuit breaker."""
        return LanguageToolServiceClient(test_settings)

    @pytest.fixture
    async def http_session(self) -> AsyncGenerator[aiohttp.ClientSession, None]:
        """Provide real HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def sample_language_tool_response(self) -> dict:
        """Sample Language Tool API response."""
        return {
            "matches": [
                {
                    "message": "Possible spelling mistake",
                    "shortMessage": "Spelling mistake",
                    "offset": 10,
                    "length": 7,
                    "replacements": [{"value": "correct"}],
                    "rule": {
                        "id": "MORFOLOGIK_RULE_EN_US",
                        "category": {"id": "TYPOS", "name": "Spelling"},
                    },
                    "type": {"typeName": "misspelling"},
                    "context": {"text": "This is incorect text", "offset": 8},
                }
            ],
            "language": "en-US",
            "grammar_category_counts": {"TYPOS": 1},
            "grammar_rule_counts": {"MORFOLOGIK_RULE_EN_US": 1},
        }

    @pytest.mark.asyncio
    async def test_real_http_call_success(
        self,
        client_with_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
        sample_language_tool_response: dict,
    ) -> None:
        """Test successful HTTP call with real circuit breaker and mocked response."""
        correlation_id = uuid.uuid4()
        text = "This is a test text with potential grammar issues."

        with aioresponses() as m:
            m.post(
                "http://language-tool-test:8085/v1/check",
                payload=sample_language_tool_response,
                status=200,
            )

            result = await client_with_circuit_breaker.check_grammar(
                text=text, http_session=http_session, correlation_id=correlation_id, language="en"
            )

            # Verify successful parsing
            assert isinstance(result, GrammarAnalysis)
            assert result.error_count == 1
            assert len(result.errors) == 1
            assert result.errors[0].rule_id == "MORFOLOGIK_RULE_EN_US"
            assert result.errors[0].message == "Possible spelling mistake"
            assert result.language == "en-US"
            assert result.processing_time_ms > 0

            # Verify circuit breaker stayed closed
            assert client_with_circuit_breaker._circuit_breaker is not None
            assert client_with_circuit_breaker._circuit_breaker.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips_after_failures(
        self,
        client_with_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
    ) -> None:
        """Test circuit breaker opens after failure threshold (5 failures)."""
        correlation_id = uuid.uuid4()
        text = "Test text"

        # Circuit should be closed initially
        assert client_with_circuit_breaker._circuit_breaker is not None
        assert client_with_circuit_breaker._circuit_breaker.state == CircuitBreakerState.CLOSED

        with aioresponses() as m:
            # Mock 5 consecutive 500 errors
            for _ in range(5):
                m.post("http://language-tool-test:8085/v1/check", status=500, repeat=True)

            # Make 5 calls that should trigger circuit breaker
            for i in range(5):
                with pytest.raises(HuleEduError) as exc_info:
                    await client_with_circuit_breaker.check_grammar(
                        text=text, http_session=http_session, correlation_id=correlation_id
                    )
                assert "Language Tool Service returned 500" in str(exc_info.value)

                # Circuit should still be closed until we hit the threshold
                if i < 4:
                    assert client_with_circuit_breaker._circuit_breaker is not None
                    assert (
                        client_with_circuit_breaker._circuit_breaker.state
                        == CircuitBreakerState.CLOSED
                    )
                else:
                    # After 5th failure, circuit should be OPEN
                    assert client_with_circuit_breaker._circuit_breaker is not None
                    assert (
                        client_with_circuit_breaker._circuit_breaker.state
                        == CircuitBreakerState.OPEN
                    )

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery_cycle(
        self,
        client_with_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
        sample_language_tool_response: dict,
    ) -> None:
        """Test full circuit breaker recovery: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
        correlation_id = uuid.uuid4()
        text = "Test text"

        # Force circuit to OPEN by simulating failures
        assert client_with_circuit_breaker._circuit_breaker is not None
        client_with_circuit_breaker._circuit_breaker.failure_count = 5
        client_with_circuit_breaker._circuit_breaker._transition_to_open()
        assert client_with_circuit_breaker._circuit_breaker.state == CircuitBreakerState.OPEN

        # Set recovery timeout to a very small value for testing
        client_with_circuit_breaker._circuit_breaker.recovery_timeout = timedelta(milliseconds=10)

        # Wait for recovery timeout
        await asyncio.sleep(0.02)  # 20ms > 10ms timeout

        with aioresponses() as m:
            # First call should transition to HALF_OPEN
            m.post(
                "http://language-tool-test:8085/v1/check",
                payload=sample_language_tool_response,
                status=200,
            )

            result = await client_with_circuit_breaker.check_grammar(
                text=text, http_session=http_session, correlation_id=correlation_id
            )

            # Verify successful call and circuit is HALF_OPEN
            assert isinstance(result, GrammarAnalysis)
            assert client_with_circuit_breaker._circuit_breaker is not None
            assert (
                client_with_circuit_breaker._circuit_breaker.state == CircuitBreakerState.HALF_OPEN
            )
            assert client_with_circuit_breaker._circuit_breaker.success_count == 1

            # Second successful call should close the circuit
            m.post(
                "http://language-tool-test:8085/v1/check",
                payload=sample_language_tool_response,
                status=200,
                repeat=True,
            )

            await client_with_circuit_breaker.check_grammar(
                text=text, http_session=http_session, correlation_id=correlation_id
            )

            # Circuit should now be CLOSED
            assert client_with_circuit_breaker._circuit_breaker is not None
            assert client_with_circuit_breaker._circuit_breaker.state == CircuitBreakerState.CLOSED
            assert client_with_circuit_breaker._circuit_breaker.success_count == 0  # Reset on close

    @pytest.mark.asyncio
    async def test_concurrent_requests_during_circuit_open(
        self,
        client_with_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
    ) -> None:
        """Test multiple concurrent requests are blocked when circuit is open."""
        # Force circuit to OPEN by setting failure time properly
        assert client_with_circuit_breaker._circuit_breaker is not None
        client_with_circuit_breaker._circuit_breaker._transition_to_open()
        client_with_circuit_breaker._circuit_breaker.last_failure_time = datetime.utcnow()
        assert client_with_circuit_breaker._circuit_breaker.state == CircuitBreakerState.OPEN

        correlation_id = uuid.uuid4()
        text = "Test text"

        # Make 3 concurrent requests - all should return graceful degradation
        tasks = [
            client_with_circuit_breaker.check_grammar(
                text=text, http_session=http_session, correlation_id=correlation_id, language="en"
            )
            for _ in range(3)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should return graceful degradation (empty GrammarAnalysis)
        for result in results:
            # Check if it's an exception or result
            if isinstance(result, Exception):
                # If it's still an exception, the circuit breaker didn't work as expected
                print(f"Unexpected exception: {result}")
                # For debugging, let's check the circuit state
                assert client_with_circuit_breaker._circuit_breaker is not None
                print(f"Circuit state: {client_with_circuit_breaker._circuit_breaker.get_state()}")
                raise result
            assert isinstance(result, GrammarAnalysis)
            assert result.error_count == 0
            assert len(result.errors) == 0
            assert result.language == "en-US"  # Default fallback

        # Circuit should still be OPEN
        assert client_with_circuit_breaker._circuit_breaker is not None
        assert client_with_circuit_breaker._circuit_breaker.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_circuit_open(
        self,
        client_with_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
    ) -> None:
        """Test handler continues processing when circuit is open (graceful degradation)."""
        # Force circuit to OPEN with proper failure time
        assert client_with_circuit_breaker._circuit_breaker is not None
        client_with_circuit_breaker._circuit_breaker._transition_to_open()
        client_with_circuit_breaker._circuit_breaker.last_failure_time = datetime.utcnow()
        assert client_with_circuit_breaker._circuit_breaker.state == CircuitBreakerState.OPEN

        correlation_id = uuid.uuid4()
        text = "Swedish text: Hej världen med åäö!"

        # Should return graceful degradation without HTTP call
        result = await client_with_circuit_breaker.check_grammar(
            text=text, http_session=http_session, correlation_id=correlation_id, language="sv"
        )

        # Verify graceful degradation
        assert isinstance(result, GrammarAnalysis)
        assert result.error_count == 0
        assert len(result.errors) == 0
        assert result.language == "sv-SE"  # Mapped from "sv" by _map_language_code
        assert result.processing_time_ms >= 0  # May be 0 when circuit is open

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(
        self,
        client_without_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
    ) -> None:
        """Test exponential backoff retry delays: 0.5s, 1s, 2s."""
        correlation_id = uuid.uuid4()
        text = "Test text"

        with aioresponses() as m:
            # Mock 4 consecutive 500 errors (initial + 3 retries)
            m.post("http://language-tool-test:8085/v1/check", status=500, repeat=True)

            start_time = time.time()

            with pytest.raises(HuleEduError) as exc_info:
                await client_without_circuit_breaker.check_grammar(
                    text=text, http_session=http_session, correlation_id=correlation_id
                )

            end_time = time.time()
            total_time = end_time - start_time

            # Expected delays: 0.5 + 1.0 + 2.0 = 3.5 seconds minimum
            # Plus some tolerance for HTTP timeouts and processing
            assert total_time >= 3.4, f"Expected at least 3.4s, got {total_time:.2f}s"
            assert total_time < 8.0, f"Expected less than 8s, got {total_time:.2f}s"
            assert "after 4 attempts" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_4xx_errors_no_retry(
        self,
        client_without_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
    ) -> None:
        """Test 4xx errors are not retried (immediate failure)."""
        correlation_id = uuid.uuid4()
        text = "Test text"

        with aioresponses() as m:
            # Mock 400 error - should not retry
            m.post(
                "http://language-tool-test:8085/v1/check",
                status=400,
                payload={"error": "Bad request"},
            )

            start_time = time.time()

            with pytest.raises(HuleEduError) as exc_info:
                await client_without_circuit_breaker.check_grammar(
                    text=text, http_session=http_session, correlation_id=correlation_id
                )

            end_time = time.time()
            total_time = end_time - start_time

            # Should fail immediately without retries (< 1 second)
            assert total_time < 1.0, f"Expected immediate failure, got {total_time:.2f}s"
            assert "Language Tool Service returned 400" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_correlation_id_propagation(
        self,
        client_with_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
        sample_language_tool_response: dict,
    ) -> None:
        """Test correlation ID is propagated in HTTP headers."""
        correlation_id = uuid.uuid4()
        text = "Test text"

        with aioresponses() as m:
            m.post(
                "http://language-tool-test:8085/v1/check",
                payload=sample_language_tool_response,
                status=200,
            )

            await client_with_circuit_breaker.check_grammar(
                text=text, http_session=http_session, correlation_id=correlation_id
            )

            # Verify correlation ID was sent in request header
            assert len(m.requests) == 1
            request_key = list(m.requests.keys())[0]
            request_call = m.requests[request_key][0]
            # Access the actual request from kwargs
            headers = request_call.kwargs.get("headers", {})
            assert "X-Correlation-ID" in headers
            assert headers["X-Correlation-ID"] == str(correlation_id)

    @pytest.mark.asyncio
    async def test_language_code_mapping(
        self,
        client_with_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
        sample_language_tool_response: dict,
    ) -> None:
        """Test language code mapping (en -> en-US, sv -> sv-SE)."""
        correlation_id = uuid.uuid4()

        test_cases = [
            ("en", "en-US"),
            ("sv", "sv-SE"),
            ("auto", "auto"),
            ("unknown", "unknown"),  # Pass through unmapped codes
        ]

        for input_lang, expected_lang in test_cases:
            with aioresponses() as m:
                m.post(
                    "http://language-tool-test:8085/v1/check",
                    payload=sample_language_tool_response,
                    status=200,
                )

                await client_with_circuit_breaker.check_grammar(
                    text="Test text åäö",
                    http_session=http_session,
                    correlation_id=correlation_id,
                    language=input_lang,
                )

                # Verify mapped language was sent in request payload
                assert len(m.requests) == 1
                request_key = list(m.requests.keys())[0]
                request_call = m.requests[request_key][0]
                # Access the json data from kwargs
                json_data = request_call.kwargs.get("json", {})
                assert json_data["language"] == expected_lang
                assert "åäö" in json_data["text"]  # Swedish characters preserved

    @pytest.mark.asyncio
    async def test_circuit_breaker_metrics_state_transitions(
        self,
        client_with_circuit_breaker: LanguageToolServiceClient,
        http_session: aiohttp.ClientSession,
    ) -> None:
        """Test circuit breaker state transitions are properly tracked."""
        # Verify initial state
        assert client_with_circuit_breaker._circuit_breaker is not None
        state = client_with_circuit_breaker._circuit_breaker.get_state()
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["success_count"] == 0

        # Force failures to transition to OPEN
        client_with_circuit_breaker._circuit_breaker.failure_count = 5
        client_with_circuit_breaker._circuit_breaker._transition_to_open()

        state = client_with_circuit_breaker._circuit_breaker.get_state()
        assert state["state"] == "open"
        assert state["failure_count"] == 5

        # Transition to HALF_OPEN
        client_with_circuit_breaker._circuit_breaker._transition_to_half_open()
        state = client_with_circuit_breaker._circuit_breaker.get_state()
        assert state["state"] == "half_open"
        assert state["failure_count"] == 0  # Reset on transition

        # Transition back to CLOSED
        client_with_circuit_breaker._circuit_breaker._transition_to_closed()
        state = client_with_circuit_breaker._circuit_breaker.get_state()
        assert state["state"] == "closed"
        assert state["success_count"] == 0  # Reset on close
