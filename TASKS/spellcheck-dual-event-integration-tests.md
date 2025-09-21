# Spellcheck Dual-Event Integration Tests

## Test Scope

End-to-end validation of dual-event flow from Spellchecker Service through consumers

## Architecture Overview

The dual-event pattern splits spellcheck processing into two specialized events:

1. **Thin Event (SpellcheckPhaseCompletedV1)**: State transitions only (~300 bytes)
   - Topic: `huleedu.batch.spellcheck.phase.completed.v1`
   - Consumers: ELS (Essay Lifecycle Service), BCS (Batch Conductor Service)

2. **Rich Event (SpellcheckResultV1)**: Full business metrics
   - Topic: `huleedu.essay.spellcheck.results.v1`
   - Consumers: RAS (Result Aggregator Service), future NLP services

## Test Scenarios

### 1. Happy Path

**Description**: Spellchecker publishes both events → ELS/BCS process thin → RAS processes rich

**Test Steps**:

1. Trigger spellcheck request via test harness
2. Monitor Kafka topics for both events
3. Verify ELS updates essay state to `spellchecked_success`
4. Verify BCS records phase completion
5. Verify RAS stores complete metrics

**Assertions**:

- Both events published within 100ms of each other
- Event IDs are different but correlation IDs match
- All consumers process within 500ms

### 2. Event Correlation

**Description**: Verify both events share same correlation_id for tracing

**Test Steps**:

1. Capture both events from Kafka
2. Extract correlation_id from each
3. Query service logs using correlation_id

**Assertions**:

- correlation_id matches across both events
- Trace spans connect properly in Jaeger
- Logs can be correlated across services

### 3. State Consistency

**Description**: ELS state transitions match RAS business metrics

**Test Steps**:

1. Process essay with known correction count
2. Query ELS for essay status
3. Query RAS for correction metrics

**Assertions**:

- If corrections > 0, both show success status
- If processing failed, both show failed status
- Timestamps align within 1 second

### 4. Failure Scenarios

#### 4.1 Thin Event Fails, Rich Succeeds

**Test Steps**:

1. Block ELS/BCS consumers
2. Allow RAS consumer
3. Publish events

**Expected Behavior**:

- RAS records metrics successfully
- ELS/BCS retry on reconnection
- System remains partially operational

#### 4.2 Rich Event Fails, Thin Succeeds

**Test Steps**:

1. Block RAS consumer
2. Allow ELS/BCS consumers
3. Publish events

**Expected Behavior**:

- State transitions complete
- Metrics missing but recoverable
- Pipeline continues without metrics

#### 4.3 Spellchecker Service Crash During Publishing

**Test Steps**:

1. Start spellcheck processing
2. Kill service after thin event published
3. Restart service

**Expected Behavior**:

- Outbox pattern ensures rich event eventually published
- No data loss or duplication
- Idempotency prevents reprocessing

### 5. Performance Benchmarks

#### Baseline Single-Event (Legacy)

- Message size: ~2KB (with full metrics)
- Network transfer for 1000 essays: 2MB
- Processing time per event: ~5ms

#### Dual-Event Pattern

- Thin event size: ~300 bytes
- Rich event size: ~1.5KB
- Network transfer for 1000 essays:
  - State consumers (ELS/BCS): 300KB (85% reduction)
  - Metrics consumer (RAS): 1.5MB (25% reduction)
- Processing time:
  - Thin event: ~2ms (60% faster)
  - Rich event: ~4ms (20% faster)

## Infrastructure Requirements

### Docker Compose Setup

```yaml
services:
  kafka:
    image: confluentinc/cp-kafka:latest

  spellchecker-service:
    build: ./services/spellchecker_service

  essay-lifecycle-service:
    build: ./services/essay_lifecycle_service

  batch-conductor-service:
    build: ./services/batch_conductor_service

  result-aggregator-service:
    build: ./services/result_aggregator_service
```

### Kafka Message Inspection

```bash
# Monitor thin events
docker exec huleedu_kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic huleedu.batch.spellcheck.phase.completed.v1 \
  --from-beginning

# Monitor rich events
docker exec huleedu_kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic huleedu.essay.spellcheck.results.v1 \
  --from-beginning
```

### Database State Verification

```bash
# Check ELS state
docker exec huleedu_essay_lifecycle_db psql -U huleedu_user -d huleedu_essay_lifecycle \
  -c "SELECT essay_id, status, updated_at FROM essays WHERE batch_id = '...'"

# Check RAS metrics
docker exec huleedu_result_aggregator_db psql -U huleedu_user -d huleedu_result_aggregator \
  -c "SELECT essay_id, corrections_made, l2_corrections, spell_corrections FROM essay_results WHERE batch_id = '...'"
```

## Success Criteria

### Functional Requirements

- [ ] All state transitions recorded correctly in ELS
- [ ] All business metrics properly aggregated in RAS
- [ ] No data loss or duplication under normal operations
- [ ] Graceful degradation during partial failures

### Performance Requirements

- [ ] 80%+ reduction in network traffic for state-only consumers
- [ ] 50%+ reduction in processing time for state transitions
- [ ] <100ms latency between thin and rich event publishing
- [ ] <500ms end-to-end processing for both events

### Observability Requirements

- [ ] Events correlatable via correlation_id
- [ ] Complete trace spans in Jaeger
- [ ] Metrics exported to Prometheus
- [ ] Structured logs with proper context

## Test Implementation

### Unit Tests

Located in:

- `services/spellchecker_service/tests/unit/test_event_publisher_outbox_unit.py`
- `services/result_aggregator_service/tests/unit/test_event_processor_spellcheck_*.py`
- `services/batch_conductor_service/tests/unit/test_bcs_idempotency_basic.py`

### Integration Tests

Located in:

- `tests/integration/test_spellcheck_dual_event_flow.py`
- `services/*/tests/integration/test_kafka_consumer_*.py`

### E2E Tests

Located in:

- `tests/functional/test_e2e_spellcheck_workflows.py`

## Rollback Plan

If issues discovered post-deployment:

1. Consumers can be reverted independently (backward compatible)
2. Spellchecker can publish both legacy and new events temporarily
3. Feature flag to control which events are published
4. Monitor for 24 hours before removing legacy support

## References

- Rule 030: Event-Driven Architecture Standards
- Rule 052: Event Contract Standards
- Task: Spellcheck Dual-Event Pattern Implementation
- Design Doc: Performance Optimization via Event Splitting
