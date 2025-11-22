"""
Integration test for mock provider error handling with queue processor.

Tests that the queue processor correctly handles errors from the mock provider
without raising "generator didn't stop after throw()" exceptions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

import pytest
from common_core import (
    LLMComparisonRequest,
    LLMProviderType,
    QueueStatus,
)
from common_core import (
    LLMConfigOverridesHTTP as LLMConfigOverrides,
)
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.comparison_processor_impl import (
    ComparisonProcessorImpl,
)
from services.llm_provider_service.implementations.llm_orchestrator_impl import LLMOrchestratorImpl
from services.llm_provider_service.implementations.queue_processor_impl import QueueProcessorImpl
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.protocols import (
    ComparisonProcessorProtocol,
    LLMEventPublisherProtocol,
    LLMOrchestratorProtocol,
    LLMProviderProtocol,
    QueueManagerProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest


class MockQueueManager:
    """Mock queue manager for testing."""

    def __init__(self) -> None:
        self.status_updates: list[tuple[uuid.UUID, QueueStatus, Dict[str, Any]]] = []
        self.failed_count = 0
        self.completed_count = 0

    async def update_status(
        self,
        queue_id: uuid.UUID,
        status: QueueStatus,
        message: Optional[str] = None,
        result_location: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """Track status updates."""
        all_kwargs = kwargs.copy()
        if message is not None:
            all_kwargs["error_message"] = message
        if result_location is not None:
            all_kwargs["result_location"] = result_location
        self.status_updates.append((queue_id, status, all_kwargs))
        if status == QueueStatus.FAILED:
            self.failed_count += 1
        elif status == QueueStatus.COMPLETED:
            self.completed_count += 1
        return True

    async def enqueue(self, request: Any) -> bool:
        """Mock enqueue method."""
        return True

    async def dequeue(self) -> Optional[Any]:
        """Mock dequeue method."""
        return None

    async def remove(self, queue_id: uuid.UUID) -> bool:
        """Mock remove method."""
        return True

    async def get_status(self, queue_id: uuid.UUID) -> Optional[Any]:
        """Mock get_status method."""
        return None

    async def get_queue_stats(self) -> Any:
        """Mock get_queue_stats method."""
        return None

    async def cleanup_expired(self) -> int:
        """Mock cleanup_expired method."""
        return 0


class MockEventPublisher:
    """Mock event publisher for testing."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Dict[str, Any]]] = []

    async def publish_llm_request_started(
        self,
        provider: str,
        correlation_id: uuid.UUID,
        metadata: Dict[str, Any],
    ) -> None:
        """Track started events."""
        self.events.append(
            (
                "started",
                {"provider": provider, "correlation_id": correlation_id, "metadata": metadata},
            )
        )

    async def publish_llm_request_completed(
        self,
        provider: str,
        correlation_id: uuid.UUID,
        success: bool,
        response_time_ms: int,
        metadata: Dict[str, Any],
    ) -> None:
        """Track completion events."""
        self.events.append(
            (
                "completed",
                {
                    "provider": provider,
                    "correlation_id": correlation_id,
                    "success": success,
                    "response_time_ms": response_time_ms,
                    "metadata": metadata,
                },
            )
        )

    async def publish_llm_provider_failure(
        self,
        provider: str,
        failure_type: str,
        correlation_id: uuid.UUID,
        error_details: str,
        circuit_breaker_opened: bool = False,
    ) -> None:
        """Track failure events."""
        self.events.append(
            (
                "failure",
                {
                    "provider": provider,
                    "failure_type": failure_type,
                    "correlation_id": correlation_id,
                    "error_details": error_details,
                    "circuit_breaker_opened": circuit_breaker_opened,
                },
            )
        )

    async def publish_to_topic(
        self,
        topic: str,
        envelope: Any,
        key: Optional[str] = None,
    ) -> None:
        """Track topic publications."""
        self.events.append(("topic", {"topic": topic, "envelope": envelope, "key": key}))


class ErrorTriggeringMockProvider:
    """Mock provider that guarantees errors for testing."""

    # Class-level counter to ensure error triggering works across DI instances
    _request_count = 0

    def __init__(self, settings: Settings):
        self.settings = settings

    @classmethod
    def reset_counter(cls) -> None:
        """Reset the request counter for test isolation."""
        cls._request_count = 0

    async def generate_comparison(
        self,
        user_prompt: str,
        correlation_id: uuid.UUID,
        prompt_blocks: list[dict[str, Any]] | None = None,
        system_prompt_override: Optional[str] = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        max_tokens_override: Optional[int] = None,
    ) -> Any:
        """Generate comparison with guaranteed errors every 10th request."""
        # Use class-level counter to ensure shared state across DI instances
        ErrorTriggeringMockProvider._request_count += 1
        current_count = ErrorTriggeringMockProvider._request_count

        print(f"🔥 ErrorTriggeringMockProvider: Processing request #{current_count}")

        # Fail every 10th request to guarantee errors
        if current_count % 10 == 0:
            print(f"💥 ErrorTriggeringMockProvider: Triggering error on request #{current_count}")
            from huleedu_service_libs.error_handling import raise_external_service_error

            raise_external_service_error(
                service="llm_provider_service",
                operation="error_triggering_mock_comparison",
                external_service="error_triggering_mock",
                message="Guaranteed error for testing",
                correlation_id=correlation_id,
                details={"provider": "mock", "request_count": current_count},
            )

        # Otherwise return a mock response
        from common_core import EssayComparisonWinner, LLMProviderType

        from services.llm_provider_service.internal_models import LLMProviderResponse

        print(
            f"✅ ErrorTriggeringMockProvider: Returning success response for "
            f"request #{current_count}"
        )
        return LLMProviderResponse(
            winner=EssayComparisonWinner.ESSAY_A,  # Fixed: use enum, not .value
            justification="Test justification",
            confidence=0.85,
            provider=LLMProviderType.MOCK,
            model="test-model",
            correlation_id=correlation_id,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost_estimate=0.01,
            response_time_ms=10,
        )


class MockQueueProcessorProvider(Provider):
    """DI provider for queue processor integration tests."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide test settings."""
        settings = Settings()
        settings.USE_MOCK_LLM = True
        settings.QUEUE_POLL_INTERVAL_SECONDS = 0.1
        settings.QUEUE_MAX_RETRIES = 0  # Disable retries to test error handling directly
        return settings

    @provide(scope=Scope.APP)
    def provide_providers(self, settings: Settings) -> Dict[LLMProviderType, LLMProviderProtocol]:
        """Provide mock providers with forced error simulation."""
        # Use a custom error-triggering provider that fails every 10th request
        mock_provider = ErrorTriggeringMockProvider(settings=settings)
        return {
            LLMProviderType.MOCK: mock_provider,
            LLMProviderType.OPENAI: mock_provider,
            LLMProviderType.ANTHROPIC: mock_provider,
        }

    @provide(scope=Scope.APP)
    def provide_comparison_processor(
        self,
        providers: Dict[LLMProviderType, LLMProviderProtocol],
        event_publisher: LLMEventPublisherProtocol,
        settings: Settings,
    ) -> ComparisonProcessorProtocol:
        """Provide comparison processor for domain logic."""
        return ComparisonProcessorImpl(
            providers=providers,
            event_publisher=event_publisher,
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def provide_orchestrator(
        self,
        providers: Dict[LLMProviderType, LLMProviderProtocol],
        event_publisher: LLMEventPublisherProtocol,
        queue_manager: QueueManagerProtocol,
        trace_context_manager: TraceContextManagerImpl,
        settings: Settings,
    ) -> LLMOrchestratorProtocol:
        """Provide real orchestrator with mock providers."""
        return LLMOrchestratorImpl(
            providers=providers,
            event_publisher=event_publisher,
            queue_manager=queue_manager,
            trace_context_manager=trace_context_manager,
            settings=settings,
        )

    @provide(scope=Scope.APP)
    def provide_queue_manager(self) -> QueueManagerProtocol:
        """Provide mock queue manager."""
        return MockQueueManager()

    @provide(scope=Scope.APP)
    def provide_event_publisher(self) -> LLMEventPublisherProtocol:
        """Provide mock event publisher."""
        return MockEventPublisher()

    @provide(scope=Scope.APP)
    def provide_trace_context_manager(self) -> TraceContextManagerImpl:
        """Provide real trace context manager."""
        return TraceContextManagerImpl()


@pytest.fixture
async def di_container() -> AsyncGenerator[AsyncContainer, None]:
    """Create DI container for testing."""
    container = make_async_container(MockQueueProcessorProvider())
    yield container
    await container.close()


@pytest.mark.asyncio
async def test_queue_processor_handles_mock_provider_errors(di_container: AsyncContainer) -> None:
    """Test that queue processor handles mock provider errors correctly."""
    # Reset error triggering provider counter for test isolation
    ErrorTriggeringMockProvider.reset_counter()

    # Get dependencies from container
    comparison_processor = await di_container.get(ComparisonProcessorProtocol)
    queue_manager = await di_container.get(QueueManagerProtocol)
    event_publisher = await di_container.get(LLMEventPublisherProtocol)
    trace_context_manager = await di_container.get(TraceContextManagerImpl)
    settings = await di_container.get(Settings)

    # Create queue processor
    queue_processor = QueueProcessorImpl(
        comparison_processor=comparison_processor,
        queue_manager=queue_manager,
        event_publisher=event_publisher,
        trace_context_manager=trace_context_manager,
        settings=settings,
    )

    # Process multiple requests to trigger guaranteed errors (every 10th request)
    successful_count = 0
    error_count = 0
    max_attempts = 25  # This will trigger 2-3 errors (10th, 20th requests)

    for i in range(max_attempts):
        request_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        user_prompt = f"""Compare these essays - attempt {i}

**Essay A (ID: essay_a_{i}):**
Essay A content for attempt {i}

**Essay B (ID: essay_b_{i}):**
Essay B content for attempt {i}"""

        request_data = LLMComparisonRequest(
            user_prompt=user_prompt,
            callback_topic="test.callback.topic",
            correlation_id=correlation_id,
            llm_config_overrides=LLMConfigOverrides(
                provider_override=LLMProviderType.MOCK,
            ),
        )

        queued_request = QueuedRequest(
            queue_id=request_id,
            request_data=request_data,
            status=QueueStatus.QUEUED,
            queued_at=datetime.now(timezone.utc),
            size_bytes=len(request_data.model_dump_json()),
            callback_topic="test.callback.topic",
            trace_context={},
        )

        # Clear previous status updates to track this request only
        initial_update_count = len(queue_manager.status_updates)

        # Process the request - should handle errors internally
        try:
            await queue_processor._process_request(queued_request)
            # If we get here, no exception was raised (good!)

            # Check status updates since this request started
            new_updates = queue_manager.status_updates[initial_update_count:]

            # Find the final status for this request
            request_final_status = None
            all_statuses_for_request = []
            for queue_id, status, kwargs in new_updates:
                if queue_id == request_id:
                    all_statuses_for_request.append(status)
                    request_final_status = status

            print(
                f"📊 Request {i + 1} (ID: {request_id}): "
                f"statuses = {all_statuses_for_request}, final = {request_final_status}"
            )

            if request_final_status == QueueStatus.COMPLETED:
                successful_count += 1
            elif request_final_status == QueueStatus.FAILED:
                error_count += 1
                print(f"🚨 Detected FAILED status for request {i + 1}")
            else:
                print(f"⚠️  Request {i + 1} has unexpected final status: {request_final_status}")

        except Exception as e:
            # This should NOT happen with our fix
            pytest.fail(f"Queue processor raised unexpected exception: {e}")

    # Verify results
    assert successful_count > 0, "Should have successfully processed some requests"
    assert error_count > 0, "Should have encountered guaranteed errors (every 10th request)"
    assert successful_count + error_count == max_attempts, (
        f"All requests should be accounted for: "
        f"{successful_count} + {error_count} != {max_attempts}"
    )

    # With ErrorTriggeringMockProvider, we expect exactly 2 errors
    # (10th and 20th requests out of 25)
    expected_errors = max_attempts // 10  # Should be 2 for 25 requests
    assert error_count == expected_errors, (
        f"Expected {expected_errors} errors but got {error_count}"
    )

    print(
        f"✅ Successfully processed {max_attempts} requests: "
        f"{successful_count} successful, {error_count} failed"
    )
    print("✅ All errors were handled internally without raising exceptions")
    print(
        f"✅ Error rate: {error_count}/{max_attempts} = "
        f"{error_count / max_attempts:.1%} as expected"
    )


@pytest.mark.asyncio
async def test_queue_processor_error_within_context_manager(di_container: AsyncContainer) -> None:
    """Test that errors within trace context manager are handled correctly."""
    # Reset error triggering provider counter for test isolation
    ErrorTriggeringMockProvider.reset_counter()

    # Get dependencies
    comparison_processor = await di_container.get(ComparisonProcessorProtocol)
    queue_manager = await di_container.get(QueueManagerProtocol)
    event_publisher = await di_container.get(LLMEventPublisherProtocol)
    trace_context_manager = await di_container.get(TraceContextManagerImpl)
    settings = await di_container.get(Settings)

    # Create queue processor
    queue_processor = QueueProcessorImpl(
        comparison_processor=comparison_processor,
        queue_manager=queue_manager,
        event_publisher=event_publisher,
        trace_context_manager=trace_context_manager,
        settings=settings,
    )

    # Create a request with trace context
    request_id = uuid.uuid4()
    correlation_id = uuid.uuid4()

    user_prompt = """Test error handling with trace context

**Essay A (ID: essay_a_trace):**
Essay A with trace

**Essay B (ID: essay_b_trace):**
Essay B with trace"""

    request_data = LLMComparisonRequest(
        user_prompt=user_prompt,
        callback_topic="test.callback.topic",
        correlation_id=correlation_id,
        llm_config_overrides=LLMConfigOverrides(
            provider_override=LLMProviderType.MOCK,
        ),
    )

    queued_request = QueuedRequest(
        queue_id=request_id,
        request_data=request_data,
        status=QueueStatus.QUEUED,
        queued_at=datetime.now(timezone.utc),
        size_bytes=len(request_data.model_dump_json()),
        callback_topic="test.callback.topic",
        trace_context={"traceparent": "00-1234567890abcdef-1234567890abcdef-01"},
    )

    # Process the request multiple times to ensure we hit an error case
    error_encountered = False
    for _ in range(50):  # Try up to 50 times to hit the 5% error rate
        queue_manager.status_updates = []  # Reset for each attempt

        try:
            await queue_processor._process_request(queued_request)

            # Check if this attempt resulted in an error
            if queue_manager.status_updates:
                last_status = queue_manager.status_updates[-1][1]
                if last_status == QueueStatus.FAILED:
                    error_encountered = True
                    break
        except Exception as e:
            pytest.fail(f"Should handle error internally, but raised: {e}")

    assert error_encountered, "Should have encountered at least one mock provider error"
    print("Successfully handled error within trace context manager without raising exception")
