# Implement Event-Driven Callback Publishing in LLM Provider Service

THINK VERY HARD and Implement the following task according to my codebase rules and standards: ARCHITECTURE: Implement Event-Driven Callback Publishing in LLM Provider Service

## Context and Problem Statement

The current architecture of the `llm_provider_service` forces clients (like `cj_assessment_service`) to implement complex, stateful, and inefficient HTTP polling loops to retrieve results for queued requests. This pattern violates our core "async-first" and DRY principles, creating tight coupling between services and placing an unnecessary implementation burden on every client.

The immediate goal is to refactor the `llm_provider_service` to support a fully asynchronous, event-driven callback mechanism. This will allow clients to submit a request and receive the result later via a dedicated Kafka topic, eliminating the need for polling and aligning the service with our platform's event-driven standards.

## Required Architecture Rules

**MUST READ** these architectural guidelines before proceeding:

- `.cursor/rules/020-architectural-mandates.mdc` - Service Communication Patterns
- `.cursor/rules/030-event-driven-architecture-eda-standards.mdc` - Core EDA Principles
- `.cursor/rules/042-async-patterns-and-di.mdc` - Dependency Injection and Protocols
- `.cursor/rules/051-pydantic-v2-standards.mdc` - Event Contract Standards
- `.cursor/rules/070-testing-and-quality-assurance.mdc` - Test Architecture

## Implementation Objectives

### Step 1: Define the Callback Event Contract

#### 1.1 Create Callback Event Model

**Action:** In `common_core`, create a new Pydantic model `LLMComparisonResultV1` that will serve as the data payload for the callback event. This model's structure should be based on the existing `LLMOrchestratorResponse` internal model to ensure all necessary data (winner, justification, confidence, metadata, etc.) is included.

**File:** `services/llm_provider_service/internal_models.py` (for reference model) → `common_core/src/common_core/events/llm_provider_events.py` (for new event model).

#### 1.2 Define Callback Topic

**Action:** In `event_enums.py`, add a new `ProcessingEvent` member `LLM_COMPARISON_RESULT`. Add a mapping for this event to the topic name `huleedu.llm_provider.comparison_result.v1`.

**File:** `common_core/src/common_core/event_enums.py`

#### 1.3 Bootstrap New Topic

**Action:** Add the new topic `huleedu.llm_provider.comparison_result.v1` to the list of topics created on startup.

**File:** `scripts/kafka_topic_bootstrap.py`

### Step 2: Update API and Queueing Contracts

#### 2.1 Update API Request Model

**Action:** Add an optional `callback_topic: str | None = None` field to the `LLMComparisonRequest` model.

**File:** `services/llm_provider_service/api_models.py`

#### 2.2 Update Internal Queue Model

**Action:** Add the `callback_topic: str | None = None` field to the `QueuedRequest` model to persist the callback destination.

**File:** `services/llm_provider_service/queue_models.py`

### Step 3: Update Orchestrator to Handle Callback Topic

#### 3.1 Persist Callback Topic During Queuing

**Action:** In the `LLMOrchestratorImpl._queue_request` method, ensure the `callback_topic` from the incoming API request is saved to the `QueuedRequest` object.

**File:** `services/llm_provider_service/implementations/llm_orchestrator_impl.py`

### Step 4: Implement the Callback Publishing Logic

#### 4.1 Refactor Queue Processor

**Action:** Modify the `QueueProcessorImpl._handle_request_success` method. This is the core of the task.

**Logic:**

1. After successfully processing a queued request, check if the `QueuedRequest` object has a `callback_topic` defined.
2. If it does, construct a standard `EventEnvelope` wrapping the new `LLMComparisonResultV1` model.
3. Use the injected `KafkaBus` (via the `LLMEventPublisherProtocol`) to publish this event to the specified topic. The message key should be the `correlation_id`.
4. If no `callback_topic` is present, retain the existing behavior of storing the result in the local cache to ensure backward compatibility.

**File:** `services/llm_provider_service/implementations/queue_processor_impl.py`

## Validation Commands

### Check for existing patterns

```bash
rg "def _queue_request" services/llm_provider_service/implementations/llm_orchestrator_impl.py
rg "def _handle_request_success" services/llm_provider_service/implementations/queue_processor_impl.py
```

### After implementation, validate

```bash
# Verify the new event and topic are available for import
pdm run python -c "from common_core.events.llm_provider_events import LLMComparisonResultV1; print('✅ Event OK')"
pdm run python -c "from common_core.event_enums import ProcessingEvent, topic_name; print(topic_name(ProcessingEvent.LLM_COMPARISON_RESULT))"

# Run new and existing tests
pdm run pytest services/llm_provider_service/tests/unit/ -k "test_queue_processor_callback" -v
```

## Success Criteria

- ✅ The `/api/v1/comparison` endpoint successfully accepts requests with an optional `callback_topic` field.
- ✅ When a `callback_topic` is provided for a queued request, the `QueueProcessor` publishes a valid `EventEnvelope[LLMComparisonResultV1]` to that Kafka topic upon completion.
- ✅ Requests without a `callback_topic` continue to function as before (result stored in local cache).
- ✅ The published Kafka event contains the correct `correlation_id` to allow the client to associate the result with its original request.
- ✅ New unit tests for the callback publishing logic pass.
- ✅ All existing tests for the `llm_provider_service` continue to pass, ensuring no regressions.

## Implementation Strategy

1. **Test-Driven Approach:** Before implementing the publishing logic in **Step 4.1**, write a failing integration test that sends a request with a `callback_topic` and asserts that a corresponding message appears on a test Kafka topic.
2. **Incremental Implementation:** Implement the changes in logical steps, testing after each component is updated.
3. **Backward Compatibility:** Ensure existing functionality continues to work for clients not using callbacks.
4. **Validation:** Use the provided validation commands to verify the implementation.
5. **Documentation:** Update any relevant API documentation to reflect the new callback functionality.

## Anti-Patterns to Avoid

- **DO NOT** modify the existing synchronous return paths (`200 OK`). This change only affects the asynchronous, queued workflow.
- **DO NOT** hardcode the callback topic name within the `QueueProcessor`. It must be read dynamically from the `QueuedRequest` object.
- **DO NOT** publish the entire `LLMOrchestratorResponse`. Create and publish the new, clean `LLMComparisonResultV1` contract.
