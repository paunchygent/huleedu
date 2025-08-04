# Phase 2 Processing Flow - Pipeline Execution

**Status:** IMPLEMENTED - Core services operational, AI Feedback pending  
**Purpose:** Multi-service pipeline processing of ready batches  
**Scope:** From READY_FOR_PIPELINE_EXECUTION through all processing phases

## Overview

Phase 2 handles the actual content processing pipeline for batches that have completed Phase 1 (or skipped it for GUEST batches). All batches enter Phase 2 in the same state regardless of origin.

### Entry Conditions
- **GUEST batches**: Enter after BatchContentProvisioningCompletedV1
- **REGULAR batches**: Enter after Phase 1 student matching completion
- **Batch state**: READY_FOR_PIPELINE_EXECUTION
- **Trigger**: ClientBatchPipelineRequestV1 from API Gateway

## Pipeline Architecture

### Sequential Processing Chain
```
Client Request → BOS → ELS → Services → BOS → Client Response
                   ↓
              [Spellcheck] → [CJ Assessment] → [NLP Analysis] → [AI Feedback]
```

### Service Processing Order
1. **Spellcheck Service**: Grammar and spelling analysis
2. **CJ Assessment Service**: Comparative judgment scoring  
3. **NLP Service**: Text analysis and feature extraction
4. **AI Feedback Service**: Automated feedback generation (not implemented)

## Event Flow Architecture

### Pipeline Initiation
1. **ClientBatchPipelineRequestV1** (API Gateway → BOS)
2. **BOS validates batch state** (must be READY_FOR_PIPELINE_EXECUTION)
3. **BatchServiceSpellcheckInitiateCommandDataV1** (BOS → ELS)
4. **ELS forwards to first service** (Spellcheck)

### Inter-Service Progression
```
ELS → Spellcheck → ELS → CJ Assessment → ELS → NLP → ELS → AI Feedback → ELS → BOS
```

Each service follows the pattern:
1. Receives batch processing command from ELS
2. Processes all essays in parallel
3. Publishes completion event back to ELS
4. ELS orchestrates progression to next service
5. Final service completion triggers batch completion

## Service Responsibilities

### Batch Orchestrator Service (BOS)
- **Pipeline Entry**: Validates batch readiness and initiates processing
- **Client Interface**: Handles pipeline requests and provides status updates
- **State Management**: Tracks overall pipeline progression

**Key Operations:**
- Batch state validation before pipeline initiation
- Pipeline phase coordination
- Final results aggregation and client response

### Essay Lifecycle Service (ELS)
- **Service Orchestration**: Routes commands between pipeline services
- **Progress Tracking**: Maintains processing state for each essay
- **Results Aggregation**: Collects and combines results from all services

**Key Patterns:**
- Transactional outbox for reliable event publishing
- Essay-level and batch-level state management
- Service progression logic

### Processing Services

#### Spellcheck Service
- **Grammar Analysis**: Spelling, grammar, and style checking
- **Error Categorization**: Structured error classification
- **Batch Processing**: Parallel processing of all essays

#### CJ Assessment Service  
- **Comparative Scoring**: Relative quality assessment
- **Ranking Generation**: Essay ranking within batch
- **Rubric Application**: Standards-based evaluation

#### NLP Service (Phase 2 Mode)
- **Text Analysis**: Feature extraction, complexity metrics
- **Content Classification**: Topic identification, sentiment analysis
- **Linguistic Features**: Readability, vocabulary analysis

#### AI Feedback Service
- **Status**: Not yet implemented
- **Planned**: Automated feedback generation based on analysis results

## Event Models and Topics

### Pipeline Initiation Events
```python
# Client request
ClientBatchPipelineRequestV1:
    batch_id: str
    requested_services: list[str]  # ["spellcheck", "cj_assessment", "nlp"]
    priority: str = "normal"

# Service initiation commands  
BatchServiceSpellcheckInitiateCommandDataV1
BatchServiceCJAssessmentInitiateCommandDataV1
BatchServiceNLPInitiateCommandDataV1
```

### Service Completion Events
```python
# Service-specific completion events
BatchSpellcheckCompletedV1
BatchCJAssessmentCompletedV1  
BatchNLPAnalysisCompletedV1

# Each contains:
    batch_id: str
    processed_essays: list[ProcessedEssayResult]
    processing_summary: ProcessingSummary
    service_metadata: dict[str, Any]
```

### Final Pipeline Event
```python
BatchPipelineCompletedV1:
    batch_id: str
    completed_services: list[str]
    processing_duration: timedelta
    final_results: BatchProcessingResults
```

## Processing Patterns

### Parallel Essay Processing
- Each service processes all essays in batch concurrently
- Configurable concurrency limits (default: 10 concurrent essays)
- Graceful handling of individual essay failures
- Batch succeeds with partial results if majority succeeds

### Error Handling Strategy
```python
# Per-essay error handling
EssayProcessingResult:
    essay_id: str
    status: "success" | "error" | "skipped"
    results: dict[str, Any] | None
    error_message: str | None
    processing_duration: float

# Batch-level summary
ProcessingSummary:
    total_essays: int
    successful: int
    failed: int  
    skipped: int
    average_duration: float
```

### Service Integration Patterns

**Command Handler Pattern:**
```python
class BatchServiceHandler(CommandHandlerProtocol):
    async def handle(self, command: BatchServiceCommand) -> None:
        # 1. Validate batch and essays
        # 2. Process essays in parallel with semaphore
        # 3. Aggregate results
        # 4. Publish completion event via outbox
```

**Outbox Pattern:**
- All services use transactional outbox for reliable event publishing
- Prevents data loss during service failures
- Ensures event ordering and idempotency

## Performance Requirements

### Processing Targets
- **Spellcheck**: <2s per essay, <30s per batch (20 essays)
- **CJ Assessment**: <5s per essay, <60s per batch
- **NLP Analysis**: <3s per essay, <45s per batch
- **Total Pipeline**: <5 minutes for 30-essay batch

### Scalability Limits
- **Maximum batch size**: 100 essays
- **Concurrent batches**: 50 per service
- **Service isolation**: Independent scaling per service

## Monitoring and Observability

### Key Metrics
```python
# Pipeline progression
pipeline_duration_seconds = Histogram(
    "pipeline_processing_duration_seconds",
    ["service_name", "batch_size_range"]
)

# Service performance
service_processing_duration = Histogram(
    "service_essay_processing_seconds", 
    ["service_name", "essay_complexity"]
)

# Error rates
service_error_rate = Counter(
    "service_processing_errors_total",
    ["service_name", "error_type"]
)
```

### Health Checks
- Individual service health endpoints
- End-to-end pipeline health validation
- Service dependency health monitoring

## Operational Considerations

### Service Dependencies
- All services require PostgreSQL database access
- Kafka connectivity for event processing  
- Content service access for essay text retrieval
- Redis for caching and deduplication

### Deployment Patterns
- Each service runs as independent Docker container
- Shared Kafka cluster for event routing
- Service-specific database isolation
- Horizontal scaling per service demand

### Common Issues
- **Pipeline stalling**: Check service health, Kafka connectivity
- **Partial results**: Review individual service logs for essay failures
- **Performance degradation**: Monitor resource usage, database connections
- **Event ordering**: Verify outbox processing and Kafka partition assignment
