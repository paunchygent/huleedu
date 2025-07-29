# NLP Service - Phase 1 Student Matching Implementation

**STATUS: REFINED - Ready for Implementation**
**LAST UPDATED: 2025-01-29**

## Overview

This document outlines the implementation plan for the NLP Service, focusing exclusively on Phase 1: Student Matching functionality. The service will identify and match student names/emails from essay text against class rosters.

**IMPORTANT**: This is a draft proposal that requires review to ensure full compliance with HuleEdu architectural patterns and standards.

## Current State

### Existing Infrastructure
- Batch Orchestrator Service publishes `BATCH_NLP_INITIATE_COMMAND` events
- Essay Lifecycle Service expects `ESSAY_NLP_COMPLETED` events (needs contract update)
- Class Management Service provides roster API endpoints
- Content Service stores essay text with retrieval API

### Missing Components
1. ~~NLP Service implementation~~ (In Progress)
2. ~~Event contracts for author matching results~~ (✅ Completed)
3. ~~Topic mappings in common_core~~ (✅ Completed)
4. Integration with Essay Lifecycle Service state machine

## Proposed Architecture

### Service Pattern
Following the established **Kafka Worker Service Pattern** with improvements:
- Pure worker service consuming Kafka events
- Clear input/output event contracts
- Better separation of concerns than `spellchecker_service`
- Protocol-based dependency injection
- Isolated business logic in dedicated modules

### Event Flow
```
BOS → BATCH_NLP_INITIATE_COMMAND → NLP Service
                                         ↓
                          ESSAY_AUTHOR_MATCH_SUGGESTED → ELS
```

## Implementation Plan

### Phase 1: Improved Service Structure

```
services/nlp_service/
├── Dockerfile
├── README.md
├── __init__.py
├── worker_main.py                # Entry point with signal handling
├── kafka_consumer.py             # NlpKafkaConsumer class
├── event_processor.py            # Clean message processing
├── config.py                     # Service configuration
├── di.py                         # Dependency injection setup
├── protocols.py                  # All service protocols
├── core_logic.py                 # Pure business functions
├── metrics.py                    # Prometheus metrics
├── implementations/
│   ├── __init__.py
│   ├── content_client_impl.py   # Content Service HTTP client
│   ├── roster_client_impl.py    # Class Management Service client
│   ├── roster_cache_impl.py     # Redis-based roster caching
│   ├── student_matcher_impl.py  # Student matching orchestration
│   └── event_publisher_impl.py  # Result event publishing
├── matching_algorithms/          # Business algorithms (pure)
│   ├── __init__.py
│   ├── email_matcher.py          # Email extraction and matching
│   ├── name_matcher.py           # Name extraction and fuzzy matching
│   └── composite_matcher.py      # Combines all matching strategies
├── pyproject.toml
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/
    └── contract/
```

### Common Core Additions

#### New Event Model (✅ COMPLETED)

```python
# common_core/events/nlp_events.py
from __future__ import annotations
from pydantic import BaseModel, Field
from .base_event_models import ProcessingUpdate

class StudentMatchSuggestion(BaseModel):
    """Represents a potential student match."""
    student_id: str
    student_name: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    match_reason: str  # "exact_name", "fuzzy_name", "email"

class EssayAuthorMatchSuggestedV1(ProcessingUpdate):
    """Event published when author matches are suggested."""
    essay_id: str
    suggestions: list[StudentMatchSuggestion]
    match_status: str  # "HIGH_CONFIDENCE", "NEEDS_REVIEW", "NO_MATCH"
```

#### Topic Mapping (✅ COMPLETED)

```python
# common_core/event_enums.py
ESSAY_AUTHOR_MATCH_SUGGESTED = "essay.author.match.suggested"
# Mapping: "huleedu.essay.author.match.suggested.v1"
```

### Protocol Definitions

```python
# protocols.py
from typing import Protocol
from uuid import UUID
from common_core.models import StudentInfo, StudentMatchSuggestion

class StudentMatcherProtocol(Protocol):
    """Protocol for student identification logic."""
    
    async def find_student_matches(
        self,
        text: str,
        roster: list[StudentInfo],
        correlation_id: UUID
    ) -> list[StudentMatchSuggestion]:
        """Extract and match student identifiers from text."""
        ...

class ClassRosterClientProtocol(Protocol):
    """Protocol for fetching class rosters."""
    
    async def get_class_roster(
        self,
        class_id: str,
        correlation_id: UUID
    ) -> list[StudentInfo]:
        """Fetch student roster from Class Management Service."""
        ...

class ContentClientProtocol(Protocol):
    """Protocol for fetching essay content."""
    
    async def fetch_content(
        self,
        storage_id: str,
        correlation_id: UUID
    ) -> str:
        """Fetch content from Content Service."""
        ...
```

### Core Implementation Details

#### Student Matching Logic
- Extract emails using regex patterns
- Extract potential names from common patterns (Name:, Student:, By:)
- Fuzzy match names against roster using SequenceMatcher
- Assign confidence scores based on match type and quality
- Return sorted suggestions with deduplication

#### Caching Strategy
- Cache class rosters in Redis with 1-hour TTL
- Key pattern: `nlp:roster:{class_id}`
- Reduces API calls to Class Management Service
- Implement cache-aside pattern with fallback

#### Error Handling
- Use structured error handling from `huleedu_service_libs`
- Roster fetch failures: Queue for retry with backoff
- Content fetch failures: Skip essay, publish error event
- Partial batch processing: Continue with remaining essays

## Technical Considerations

### Dependency Management (OBS! No version pinning! pdm will handle this)
```toml
[project]
dependencies = [
    "quart",
    "aiokafka",
    "aiohttp",
    "redis",
    "prometheus-client",
    "dishka",
    "quart-dishka",
    "huleedu-common-core",
    "huleedu-service-libs",
]
```

### Environment Variables
- `NLP_SERVICE_HTTP_PORT` (default: 7006)
- `NLP_SERVICE_PROMETHEUS_PORT` (default: 9099)
- `NLP_SERVICE_KAFKA_BOOTSTRAP_SERVERS`
- `NLP_SERVICE_KAFKA_CONSUMER_GROUP_ID`
- `NLP_SERVICE_CONTENT_SERVICE_URL`
- `NLP_SERVICE_CLASS_MANAGEMENT_SERVICE_URL`
- `NLP_SERVICE_REDIS_URL`
- `NLP_SERVICE_LOG_LEVEL`

### Metrics to Implement
- `nlp_essays_processed_total{status="success|failure"}`
- `nlp_match_confidence_histogram`
- `nlp_roster_cache_hits_total`
- `nlp_processing_duration_seconds`
- `nlp_api_calls_total{service="content|class_management"}`

## Integration Requirements

### Essay Lifecycle Service Updates
1. Add new state transitions for author matching
2. Consume `EssayAuthorMatchSuggestedV1` events
3. Update state machine to handle match statuses
4. Implement API endpoints for manual association

### API Gateway Extensions
1. Add proxy routes for Essay-Student association endpoints
2. Implement batch status aggregation including match status

## Testing Strategy

### Unit Tests
- Student matcher algorithms
- Name extraction patterns
- Fuzzy matching logic
- Confidence score calculation

### Integration Tests
- Kafka event consumption/publishing
- API client interactions with mocks
- Redis caching behavior
- Error handling scenarios

### Contract Tests
- Event schema validation
- API contract compliance
- Backwards compatibility checks

## Future Extensibility Considerations

While implementing Phase 1 only, the architecture should support:
1. Additional analyzer types (readability, complexity) without core refactoring
2. Pluggable analyzer registration system
3. Configurable analysis pipeline
4. Result aggregation patterns

**NOTE**: These are architectural considerations only - Phase 1 implementation should NOT include these features.

## Success Criteria

1. Service successfully processes `BATCH_NLP_INITIATE_COMMAND` events
2. Accurately identifies student names/emails in essay text
3. Produces confidence-scored match suggestions
4. Publishes proper events for Essay Lifecycle consumption
5. Implements caching to minimize API calls
6. Handles errors gracefully with structured error events
7. Provides comprehensive observability through metrics
8. Achieves >90% test coverage
9. Follows all HuleEdu architectural patterns

## Architectural Decisions

### Q1: Event Design
**Question**: Should we use the existing `ESSAY_NLP_COMPLETED` event or create a new specific event?
**Decision**: Created new `ESSAY_AUTHOR_MATCH_SUGGESTED` event for clearer semantic meaning and future extensibility.

### Q2: Caching Strategy
**Question**: Is the caching strategy appropriate for the Class Management integration?
**Decision**: 1-hour TTL for class rosters is reasonable. Consider cache invalidation via events in Phase 2.

### Q3: Roster Updates
**Question**: Should the service handle roster updates via events or continue with API polling?
**Decision**: API polling is acceptable for Phase 1. Event-driven updates can be added later.

### Q4: Retry Strategy
**Question**: What should be the retry strategy for failed roster fetches?
**Decision**: Implement exponential backoff with max 3 retries. Failed essays go to DLQ after retries exhausted.

### Q5: No Match Handling
**Question**: How should we handle essays with no identifiable student information?
**Decision**: Publish event with `match_status: "NO_MATCH"` and empty suggestions list. Let ELS handle the workflow.

## Implementation Priority

1. ~~Define event contracts in common_core~~ (✅ COMPLETED)
2. Create improved service scaffold with better separation
3. Implement protocols and core matching logic
4. Add API client implementations with caching
5. Setup Kafka consumer and event processing
6. Implement comprehensive error handling
7. Add metrics and observability
8. Create test suite with >90% coverage
9. Update Essay Lifecycle Service integration
10. Document API contracts and deployment

## Key Improvements Over Spellchecker Service

1. **Better Separation**: Business logic isolated in `matching_algorithms/` directory
2. **Cleaner Protocols**: All protocols in single file at service root
3. **Pure Functions**: `core_logic.py` contains testable pure functions
4. **Organized Implementations**: Clear subdirectory structure for different concerns
5. **Explicit Worker Pattern**: `worker_main.py` entry point matches other services

---

**STATUS**: Architectural review complete. Ready for implementation with improved structure.