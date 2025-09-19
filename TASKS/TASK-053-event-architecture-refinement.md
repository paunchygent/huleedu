# TASK-053: Event Architecture Refinement

## Overview

Standardize and optimize the HuleEdu event-driven architecture to fix critical gaps in our 71-event system before scaling to ~150 events for AI feedback, analytics, and payments in 2025.

## Current State Analysis

### Event System Statistics

- **71 events** defined in `ProcessingEvent` enum (`libs/common_core/src/common_core/event_enums.py`)
- **69 mapped** to Kafka topics in `_TOPIC_MAPPING`
- **2 unmapped** (violating YAGNI principle)
- **17 topics** with naming inconsistencies

### Critical Issues Found

#### 1. Unmapped Events (Delete These)

```python
ESSAY_AIFEEDBACK_COMPLETED      # No topic, no service implementation
ESSAY_EDITOR_REVISION_COMPLETED  # No topic, no service implementation
```

#### 2. Naming Inconsistencies

**Commands - Mixed Patterns:**

```
Current:  huleedu.els.spellcheck.initiate.command.v1
          huleedu.commands.batch.pipeline.v1
Standard: huleedu.{domain}.{action}.command.v1
```

**Segments - Underscore vs Dots:**

```
Current:  huleedu.email.delivery_failed.v1
          huleedu.llm_provider.request_started.v1
Standard: huleedu.email.delivery.failed.v1
          huleedu.llm.provider.request.started.v1
```

#### 3. Missing Infrastructure

- No DLQ (Dead Letter Queue) implementation
- No standardized retry headers
- Inconsistent partition key usage
- No idempotency key pattern enforcement

## Implementation Plan

### Phase 1: Clean & Standardize

#### Task 1.1: Remove Unmapped Events

**File:** `libs/common_core/src/common_core/event_enums.py`

Remove these lines from ProcessingEvent enum:

- Line containing `ESSAY_AIFEEDBACK_COMPLETED`
- Line containing `ESSAY_EDITOR_REVISION_COMPLETED`

#### Task 1.2: Fix Topic Naming

**File:** `libs/common_core/src/common_core/event_enums.py`

Update `_TOPIC_MAPPING` dictionary:

```python
# Commands - standardize to domain-first pattern
ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND: "huleedu.batch.spellcheck.initiate.command.v1",
ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST: "huleedu.batch.pipeline.initiate.command.v1",

# Fix underscores in segments
ProcessingEvent.EMAIL_DELIVERY_FAILED: "huleedu.email.delivery.failed.v1",
ProcessingEvent.LLM_REQUEST_STARTED: "huleedu.llm.provider.request.started.v1",
ProcessingEvent.LLM_REQUEST_COMPLETED: "huleedu.llm.provider.request.completed.v1",
ProcessingEvent.LLM_PROVIDER_FAILURE: "huleedu.llm.provider.failure.v1",
ProcessingEvent.LLM_USAGE_ANALYTICS: "huleedu.llm.provider.usage.analytics.v1",
ProcessingEvent.LLM_COST_ALERT: "huleedu.llm.provider.cost.alert.v1",
ProcessingEvent.LLM_COST_TRACKING: "huleedu.llm.provider.cost.tracking.v1",
ProcessingEvent.LLM_COMPARISON_RESULT: "huleedu.llm.provider.comparison.result.v1",
ProcessingEvent.ENTITLEMENTS_RATE_LIMIT_EXCEEDED: "huleedu.entitlements.rate.limit.exceeded.v1",
```

### Phase 2: Contract Enforcement

#### Task 2.1: Add Header Standards

**File:** `libs/huleedu_service_libs/src/huleedu_service_libs/outbox/manager.py`

Enhance `_create_standard_headers()` method:

```python
def _create_standard_headers(
    self,
    event_data: EventEnvelope[Any],
    provided_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = provided_headers.copy() if provided_headers else {}

    # Existing headers...

    # Add new required headers
    if "X-Correlation-Id" not in headers:
        headers["X-Correlation-Id"] = str(getattr(event_data, "correlation_id", uuid4()))

    if "X-Idempotency-Key" not in headers:
        partition_key = self._resolve_partition_key(event_data)
        event_version = getattr(event_data, "schema_version", "1")
        headers["X-Idempotency-Key"] = f"{topic}:{partition_key}:{event_version}"

    if "X-Retry-Count" not in headers:
        headers["X-Retry-Count"] = "0"

    if "X-Max-Retries" not in headers:
        headers["X-Max-Retries"] = "3"

    if "X-Backoff-Ms" not in headers:
        headers["X-Backoff-Ms"] = "1000,5000,15000"

    if "X-Original-Timestamp" not in headers:
        headers["X-Original-Timestamp"] = datetime.now(UTC).isoformat()

    return headers
```

#### Task 2.2: Partition Key Validation

**File:** Create `libs/common_core/src/common_core/events/partition_contracts.py`

```python
from typing import Any

PARTITION_KEY_CONTRACTS = {
    "batch": "batchId",
    "essay": "essayId",
    "class": "classId",
    "identity": "userId",
    "email": "messageId",
    "entitlements": "subscriptionId",
    "llm.provider": "requestId",
    "commands": "correlationId",
}

def validate_partition_key(topic: str, event_data: dict[str, Any]) -> str:
    """Validate and extract partition key based on topic domain."""
    domain = topic.split(".")[1]  # Extract domain from topic

    if domain not in PARTITION_KEY_CONTRACTS:
        raise ValueError(f"No partition key contract for domain: {domain}")

    key_field = PARTITION_KEY_CONTRACTS[domain]

    # Check in data first, then metadata
    if key_field in event_data.get("data", {}):
        return str(event_data["data"][key_field])
    elif key_field in event_data.get("metadata", {}):
        return str(event_data["metadata"][key_field])
    else:
        raise ValueError(f"Required partition key '{key_field}' not found for domain '{domain}'")
```

#### Task 2.3: DLQ Implementation

**File:** Create `libs/huleedu_service_libs/src/huleedu_service_libs/dlq.py`

```python
class DLQManager:
    """Dead Letter Queue manager for failed event processing."""

    def __init__(self, kafka_client, service_name: str):
        self.kafka_client = kafka_client
        self.service_name = service_name

    async def send_to_dlq(
        self,
        original_topic: str,
        event: dict[str, Any],
        error: Exception,
        retry_count: int,
    ) -> None:
        """Send failed event to DLQ with error context."""
        dlq_topic = f"{original_topic}.dlq.v1"

        dlq_envelope = {
            "original_topic": original_topic,
            "original_event": event,
            "error_message": str(error),
            "error_type": type(error).__name__,
            "retry_count": retry_count,
            "failed_at": datetime.now(UTC).isoformat(),
            "failed_by_service": self.service_name,
        }

        await self.kafka_client.send(
            dlq_topic,
            value=json.dumps(dlq_envelope),
            key=event.get("event_id", str(uuid4())),
        )
```

### Phase 3: Testing & Validation

#### Task 3.1: Contract Tests

**File:** Create `libs/common_core/tests/test_event_contracts.py`

```python
import pytest
from common_core.event_enums import ProcessingEvent, _TOPIC_MAPPING

class TestEventContracts:
    def test_all_events_mapped(self):
        """Ensure all ProcessingEvent entries have topic mappings."""
        for event in ProcessingEvent:
            assert event in _TOPIC_MAPPING, f"Event {event.name} has no topic mapping"

    def test_topic_naming_convention(self):
        """Validate all topics follow naming standards."""
        for event, topic in _TOPIC_MAPPING.items():
            parts = topic.split(".")

            # Must start with 'huleedu'
            assert parts[0] == "huleedu"

            # No underscores in segments
            for part in parts:
                assert "_" not in part, f"Topic {topic} contains underscore in segment"

            # Must end with version
            assert parts[-1].startswith("v"), f"Topic {topic} missing version suffix"

            # Commands must follow pattern
            if "command" in topic:
                assert parts[-2] == "command", f"Command topic {topic} malformed"

    def test_partition_key_contracts(self):
        """Ensure partition key contracts are defined for all domains."""
        domains = set()
        for topic in _TOPIC_MAPPING.values():
            domain = topic.split(".")[1]
            domains.add(domain)

        from common_core.events.partition_contracts import PARTITION_KEY_CONTRACTS

        for domain in domains:
            if domain not in ["pipeline", "validation"]:  # Exceptions
                assert domain in PARTITION_KEY_CONTRACTS
```

#### Task 3.2: CI Validation

**File:** Create `.github/workflows/event-contracts.yml`

```yaml
name: Event Contract Validation
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install pdm
          pdm install
      - name: Run contract tests
        run: pdm run pytest libs/common_core/tests/test_event_contracts.py -v
```

### Phase 4: Documentation

#### Task 4.1: Event Catalog

**File:** Create `docs/event-catalog.md`

Generate from code with script that produces:

```markdown
# Event Catalog

## Domain: batch
| Event | Topic | Partition Key | Retention |
|-------|-------|---------------|-----------|
| BATCH_ESSAYS_REGISTERED | huleedu.batch.essays.registered.v1 | batchId | 30d |
| BATCH_PIPELINE_COMPLETED | huleedu.batch.pipeline.completed.v1 | batchId | 30d |

## Dual-Event Patterns
| Thin Event (State) | Rich Event (Data) | Purpose |
|-------------------|-------------------|---------|
| SPELLCHECK_PHASE_COMPLETED | SPELLCHECK_RESULTS | State: ELS/BCS orchestration<br>Data: Result aggregation |
```

## Success Criteria

- [ ] All 71 events have topic mappings (no unmapped events)
- [ ] Zero underscores in topic segments
- [ ] All command topics follow `huleedu.{domain}.{action}.command.v1`
- [ ] DLQ manager implemented and tested
- [ ] Partition key validation enforced
- [ ] Required headers added to all events
- [ ] Contract tests passing in CI
- [ ] Event catalog auto-generated

## Testing Checklist

```bash
# Run after implementation
pdm run pytest libs/common_core/tests/test_event_contracts.py -v
pdm run pytest libs/huleedu_service_libs/tests/test_dlq.py -v
pdm run python scripts/validate_event_mappings.py
```

## Rollback Plan

- All changes are backward compatible
- Old topic names remain functional during transition
- Consumers subscribe to both old and new topics
- After 30 days, remove old topic subscriptions

## Notes

- This refactoring is REQUIRED before adding new events for AI feedback, advanced analytics, or payments
- Maintains backward compatibility during 30-day transition period
- No database migrations required
- No API changes for clients
