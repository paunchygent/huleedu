# TASK-LLM-02: Refactor CJ Assessment Service to Consume LLM Callbacks

THINK VERY HARD and Implement the following task according to my codebase rules and standards: ARCHITECTURE: Refactor CJ Assessment Service to Consume LLM Callbacks

## 📋 Context and Problem Statement

Following the enhancement of the `llm_provider_service` to support event-driven callbacks (per `TASK-LLM-01`), its primary client, the `cj_assessment_service`, must now be refactored to leverage this new, superior architectural pattern.

The client's current implementation (`LLMProviderServiceClient`) contains complex, stateful, and inefficient HTTP polling logic. This creates a tight coupling to the provider's internal state and violates our core async-first, event-driven principles.

The immediate goal is to completely remove this polling mechanism and refactor the `cj_assessment_service` to operate as a stateless "fire-and-forget" client. It will send a request with a callback topic and then asynchronously receive the result via a dedicated Kafka consumer, simplifying its logic and improving system resilience.

## ⚠️ Critical Prerequisite

This task is critically dependent on the completion of **`TASK-LLM-01`**. The `llm_provider_service` must be capable of publishing to a callback topic before this client-side refactoring can begin.

## 📚 Required Architecture Rules

**MUST READ** these architectural guidelines before proceeding:

- `.cursor/rules/020-architectural-mandates.mdc` - Service Communication Patterns
- `.cursor/rules/030-event-driven-architecture-eda-standards.mdc` - Core EDA Principles
- `.cursor/rules/042-async-patterns-and-di.mdc` - Dependency Injection and Async Patterns
- `.cursor/rules/051-pydantic-v2-standards.mdc` - Event Contract Standards
- `.cursor/rules/070-testing-and-quality-assurance.mdc` - Test Architecture

## 🎯 Implementation Objectives

### Step 1: Update Service Configuration

#### 1.1 Add Callback Topic to Configuration

- **Action:** Add a new configuration variable `LLM_PROVIDER_CALLBACK_TOPIC` to the `Settings` class, with the value `huleedu.llm_provider.comparison_result.v1`.
- **File:** `services/cj_assessment_service/config.py`

### Step 2: Refactor the LLM Provider Service Client

#### 2.1 Send Callback Topic in Request

- **Action:** Modify the `generate_comparison` method in `LLMProviderServiceClient` to include the `callback_topic` (from the new config setting) in the JSON payload of the `POST` request sent to the `llm_provider_service`.
- **File:** `services/cj_assessment_service/implementations/llm_provider_service_client.py`

#### 2.2 Remove All Polling Logic

- **Action:** This is the primary simplification. **Delete** the `_handle_queued_response` and `_poll_for_results` methods entirely. The `generate_comparison` method's logic should now simply return the result on a `200 OK`, return `None` on a `202 Accepted` (as the result will arrive via Kafka), and raise an appropriate error on other status codes.
- **File:** `services/cj_assessment_service/implementations/llm_provider_service_client.py`

### Step 3: Implement the Kafka Result Consumer

#### 3.1 Subscribe to Callback Topic

- **Action:** In the `CJAssessmentKafkaConsumer`, add the new `LLM_PROVIDER_CALLBACK_TOPIC` to the list of subscribed topics.
- **File:** `services/cj_assessment_service/kafka_consumer.py`

#### 3.2 Create New Result Handler

- **Action:** In `event_processor.py` (or a new, dedicated handler module), implement a new method `process_llm_comparison_result`. This method will be responsible for processing the incoming result from the callback topic.
- **Logic:**
  1. Deserialize the `EventEnvelope` containing the `LLMComparisonResultV1` payload
  2. Use the `correlation_id` to look up the state of the original CJ Assessment job
  3. Pass the `LLMComparisonResultV1` data to the next logical step in the workflow, which is `scoring_ranking.record_comparisons_and_update_scores`
- **Files:** 
  - `services/cj_assessment_service/event_processor.py`
  - `services/cj_assessment_service/cj_core_logic/scoring_ranking.py`

## 🔍 Validation Commands

### Find code to be removed

```bash
rg "_poll_for_results|_handle_queued_response" services/cj_assessment_service/implementations/
```

### After implementation, validate:

```bash
# Verify the new consumer is wired correctly
rg "huleedu.llm_provider.comparison_result.v1" services/cj_assessment_service/

# Run targeted tests for the new consumer logic
pdm run pytest services/cj_assessment_service/tests/unit/ -k "test_llm_result_consumer" -v

# Run the full end-to-end test to validate the complete refactored workflow
pdm run pytest tests/functional/test_e2e_cj_assessment_workflows.py -v
```

## ✅ Success Criteria

- [ ] The `LLMProviderServiceClient` in `cj_assessment_service` contains no HTTP polling logic
- [ ] All requests to the `llm_provider_service` from the client now include a `callback_topic`
- [ ] The service correctly subscribes to and consumes messages from the `huleedu.llm_provider.comparison_result.v1` topic
- [ ] A new handler correctly processes the `LLMComparisonResultV1` event and integrates it back into the CJ assessment workflow
- [ ] The complete, end-to-end comparative judgment workflow functions correctly using the asynchronous callback mechanism
- [ ] All relevant unit, integration, and E2E tests are updated and pass

## ⛔ Anti-Patterns to Avoid

- **DO NOT** leave any remnants of the polling logic in the client. The goal is complete removal.
- **DO NOT** introduce any blocking calls while waiting for the Kafka callback. The service must remain fully asynchronous.
- **DO NOT** create a new, separate Kafka consumer. Integrate the new topic subscription into the existing `CJAssessmentKafkaConsumer`.