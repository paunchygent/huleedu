# Loki LogQL Query Specialist - Real-World Examples

Practical examples of using Loki and LogQL for debugging HuleEdu services.

## Table of Contents

1. [Correlation ID Tracing](#correlation-id-tracing)
2. [Error Investigation](#error-investigation)
3. [Event Processing Debugging](#event-processing-debugging)
4. [Performance Analysis](#performance-analysis)
5. [Service Health Checks](#service-health-checks)
6. [Multi-Service Flow Analysis](#multi-service-flow-analysis)

---

## Correlation ID Tracing

### Example 1: User Reports "Essay Not Processed"

**Scenario**: User reports that essay submission succeeded but no results appeared.

**User Provides**: Correlation ID from error response: `550e8400-e29b-41d4-a716-446655440000`

**Query Sequence**:

**Step 1**: Find all logs for this correlation ID
```logql
{container=~"huleedu_.*"} |= "550e8400-e29b-41d4-a716-446655440000"
```

**Results**: Shows logs from:
- `huleedu_content_service` - Essay received
- `huleedu_batch_orchestrator_service` - Batch created
- `huleedu_essay_lifecycle_service` - Processing started
- No logs from `huleedu_spellchecker_service` (indicates failure point)

**Step 2**: Check for errors in essay_lifecycle_service
```logql
{container="huleedu_essay_lifecycle_service"} |= "550e8400-e29b-41d4-a716-446655440000" |= "ERROR"
```

**Results**: Found error:
```json
{
  "timestamp": "2025-11-18T14:32:15.123Z",
  "level": "ERROR",
  "event": "Failed to publish event to Kafka",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "SpellCheckRequestedEvent",
  "error": "KafkaTimeoutError: Failed to send message after 30s"
}
```

**Root Cause**: Kafka connection issue prevented event from reaching spellchecker service.

---

### Example 2: Tracking Batch Processing Flow

**Scenario**: Monitor a batch of 50 essays through the processing pipeline.

**Batch Correlation ID**: `abc-batch-123-def`

**Query**:
```logql
{container=~"huleedu_.*"} |= "abc-batch-123-def"
```

**Timeline View** (from Grafana Troubleshooting dashboard):
```
14:30:00 [content_service] Batch created: 50 essays
14:30:01 [batch_orchestrator] Batch queued for processing
14:30:02 [essay_lifecycle] Started processing batch
14:30:05 [essay_lifecycle] Published 50 SpellCheckRequestedEvents
14:30:10 [spellchecker_service] Received event 1/50
...
14:32:00 [spellchecker_service] Completed 50/50
14:32:01 [essay_lifecycle] All essays processed
14:32:02 [batch_orchestrator] Batch marked complete
```

**Services Involved**: 4 services, 52 log entries

---

## Error Investigation

### Example 3: Database Connection Errors

**Scenario**: Content service showing intermittent errors in production.

**Query**: Find database-related errors in last hour
```logql
{container="huleedu_content_service"} |~ "database|postgres|sqlalchemy" |= "error" [1h]
```

**Results**:
```json
{
  "timestamp": "2025-11-18T15:10:23.456Z",
  "level": "ERROR",
  "event": "Database connection pool exhausted",
  "correlation_id": "xyz-789",
  "pool_size": 10,
  "active_connections": 10,
  "queued_requests": 5
}
```

**Follow-up Query**: Check connection pool metrics
```logql
{container="huleedu_content_service"} |= "pool_size" | json | active_connections >= 8
```

**Action**: Identified connection pool exhaustion. Solution: Increase pool size or investigate connection leaks.

---

### Example 4: Event Processing Failures

**Scenario**: Spellchecker service showing high error rate.

**Query**: All errors with event context
```logql
{container="huleedu_spellchecker_service"} | json | level="error" | event_id!=""
```

**Results**: Multiple errors with same pattern:
```json
{
  "event": "Event processing failed",
  "event_type": "SpellCheckRequestedEvent",
  "error": "ValidationError: 'language' field is required",
  "event_id": "abc-123",
  "correlation_id": "xyz-456"
}
```

**Root Cause**: Missing required field in event contract. Events from essay_lifecycle_service not including language field.

**Verification Query**: Check essay_lifecycle events
```logql
{container="huleedu_essay_lifecycle_service"} |= "SpellCheckRequestedEvent" | json | language=""
```

**Action**: Fix event contract population in essay_lifecycle_service.

---

## Event Processing Debugging

### Example 5: Kafka Queue Latency

**Scenario**: Users reporting slow processing times.

**Query**: Find high queue latency logs
```logql
{container=~"huleedu_.*"} |= "kafka_message_queue_latency_seconds"
```

**Results** (parsed):
```
14:45:12 [spellchecker] Queue latency: 15.2s (correlation: abc-123)
14:45:15 [spellchecker] Queue latency: 18.7s (correlation: def-456)
14:45:20 [spellchecker] Queue latency: 22.3s (correlation: ghi-789)
```

**Follow-up Query**: Check event timestamps vs processing time
```logql
{container="huleedu_spellchecker_service"} | json | event_type="SpellCheckRequestedEvent"
```

**Analysis**: Events sitting in Kafka queue for 15-22 seconds before processing.

**Action**: Check Kafka consumer lag metrics and spellchecker service processing capacity.

---

### Example 6: Duplicate Event Processing

**Scenario**: Suspecting duplicate event processing (idempotency issue).

**Event ID**: `evt-duplicate-123`

**Query**: Find all processing attempts for this event
```logql
{container=~"huleedu_.*"} | json | event_id="evt-duplicate-123"
```

**Results**: Event processed 3 times:
```
14:50:00 [spellchecker] Processing event evt-duplicate-123
14:50:05 [spellchecker] Event processed successfully
14:51:30 [spellchecker] Processing event evt-duplicate-123 (DUPLICATE!)
14:51:32 [spellchecker] Event processed successfully
14:53:00 [spellchecker] Processing event evt-duplicate-123 (DUPLICATE!)
14:53:02 [spellchecker] Event processed successfully
```

**Verification Query**: Check idempotency key usage
```logql
{container="huleedu_spellchecker_service"} |= "idempotency" | json | event_id="evt-duplicate-123"
```

**Root Cause**: Idempotency check not working correctly. Fix idempotency implementation.

---

## Performance Analysis

### Example 7: Slow Request Investigation

**Scenario**: API endpoint `/api/essays/{id}` showing slow response times.

**Query**: Find slow requests (if duration logged)
```logql
{container="huleedu_content_service"} | json | endpoint="/api/essays/" | duration > 2.0
```

**Results**: Multiple slow requests
```json
{
  "timestamp": "2025-11-18T16:00:00.000Z",
  "event": "Request completed",
  "endpoint": "/api/essays/123",
  "method": "GET",
  "duration": 3.5,
  "correlation_id": "slow-req-123"
}
```

**Follow-up**: Trace correlation ID to find bottleneck
```logql
{container=~"huleedu_.*"} |= "slow-req-123"
```

**Timeline**:
```
16:00:00.000 [content_service] Request received
16:00:00.050 [content_service] Querying database
16:00:03.400 [content_service] Database query completed (3.35s!)
16:00:03.500 [content_service] Response sent
```

**Root Cause**: Slow database query. Check query plan and add indexes.

---

### Example 8: Rate Limiting Events

**Scenario**: External LLM provider rate limiting requests.

**Query**: Find rate limit events
```logql
{container="huleedu_llm_provider_service"} |~ "rate limit|throttle|quota"
```

**Results**:
```json
{
  "timestamp": "2025-11-18T16:15:00.000Z",
  "level": "WARNING",
  "event": "Rate limit hit for provider OpenAI",
  "provider": "openai",
  "retry_after": 60,
  "correlation_id": "batch-xyz-123"
}
```

**Follow-up**: Count rate limit events per hour
```logql
sum(count_over_time({container="huleedu_llm_provider_service"} |= "Rate limit hit" [1h]))
```

**Action**: Implement request queuing or switch to alternative provider.

---

## Service Health Checks

### Example 9: Service Startup Issues

**Scenario**: Batch orchestrator service failing to start.

**Query**: Check startup logs
```logql
{container="huleedu_batch_orchestrator_service"} |~ "started|starting|startup"
```

**Results**:
```json
{
  "timestamp": "2025-11-18T17:00:00.000Z",
  "level": "INFO",
  "event": "Service starting"
},
{
  "timestamp": "2025-11-18T17:00:01.000Z",
  "level": "ERROR",
  "event": "Failed to connect to Kafka",
  "error": "KafkaConnectionError: Cannot connect to kafka:9092"
}
```

**Root Cause**: Kafka not reachable. Check network and Kafka service status.

---

### Example 10: Health Check Failures

**Scenario**: Content service health checks failing intermittently.

**Query**: Find health check logs
```logql
{container="huleedu_content_service"} |= "healthz"
```

**Results**: Pattern of failures:
```
17:10:00 [INFO] Health check: healthy
17:10:30 [INFO] Health check: healthy
17:11:00 [ERROR] Health check failed: database connection timeout
17:11:30 [INFO] Health check: healthy
17:12:00 [ERROR] Health check failed: database connection timeout
```

**Pattern**: Health check failures every 2 minutes.

**Follow-up**: Check database connection pool
```logql
{container="huleedu_content_service"} |= "database" | json | level="error"
```

**Action**: Database connection pool exhaustion during peak traffic. Increase pool size.

---

## Multi-Service Flow Analysis

### Example 11: End-to-End Essay Processing

**Scenario**: Trace a single essay through the entire pipeline.

**Essay Correlation ID**: `essay-flow-456`

**Query**: Get chronological view across all services
```logql
{container=~"huleedu_.*"} |= "essay-flow-456"
```

**Complete Flow** (parsed from results):

```
1. 18:00:00.000 [content_service]
   - Essay submitted via API
   - Essay ID: essay-123
   - User ID: user-789

2. 18:00:00.100 [content_service]
   - Essay saved to database
   - StorageReference created: s3://bucket/essay-123.txt

3. 18:00:00.200 [content_service]
   - EssaySubmittedEvent published to Kafka

4. 18:00:00.300 [essay_lifecycle_service]
   - Received EssaySubmittedEvent
   - Started processing

5. 18:00:00.400 [essay_lifecycle_service]
   - Published SpellCheckRequestedEvent

6. 18:00:00.500 [spellchecker_service]
   - Received SpellCheckRequestedEvent
   - Started spell checking

7. 18:00:02.000 [spellchecker_service]
   - Spell check completed: 15 corrections
   - Published SpellCheckCompletedEvent

8. 18:00:02.100 [essay_lifecycle_service]
   - Received SpellCheckCompletedEvent
   - Updated essay metadata

9. 18:00:02.200 [essay_lifecycle_service]
   - Published EssayProcessingCompletedEvent

10. 18:00:02.300 [content_service]
    - Received EssayProcessingCompletedEvent
    - Marked essay as ready

11. 18:00:02.400 [content_service]
    - Sent notification to user-789
```

**Total Duration**: 2.4 seconds across 4 services, 11 steps

**Services Involved**:
- content_service (4 logs)
- essay_lifecycle_service (4 logs)
- spellchecker_service (2 logs)

---

### Example 12: Failed Cross-Service Communication

**Scenario**: Essay stuck in processing state.

**Essay Correlation ID**: `stuck-essay-789`

**Query**: Trace the flow
```logql
{container=~"huleedu_.*"} |= "stuck-essay-789"
```

**Incomplete Flow**:

```
1. 18:30:00.000 [content_service] Essay submitted
2. 18:30:00.100 [content_service] EssaySubmittedEvent published
3. 18:30:00.200 [essay_lifecycle_service] Received event
4. 18:30:00.300 [essay_lifecycle_service] ERROR: Failed to publish SpellCheckRequestedEvent
   - Error: KafkaProducerError: Message too large (5MB)
```

**Root Cause**: Essay content too large for Kafka message. Should use StorageReferenceMetadata pattern.

**Verification**: Check essay size
```logql
{container="huleedu_content_service"} |= "stuck-essay-789" | json | content_size_bytes > 1000000
```

**Action**: Implement StorageReference pattern for large essay content.

---

## Best Practice Examples

### Example 13: Efficient Correlation Tracing Workflow

**Scenario**: Production issue investigation.

**Step 1**: Start broad (last 15 minutes)
```logql
{container=~"huleedu_.*"} |= "correlation-id-123" [15m]
```

**Step 2**: Identify error service
```logql
{container=~"huleedu_.*"} |= "correlation-id-123" |= "ERROR"
```

**Results**: Error in `huleedu_llm_provider_service`

**Step 3**: Focus on error service
```logql
{container="huleedu_llm_provider_service"} |= "correlation-id-123"
```

**Step 4**: Extract structured error details
```logql
{container="huleedu_llm_provider_service"} |= "correlation-id-123" | json | level="error"
```

**Efficiency**: Narrowed from 100+ logs to 3 relevant error logs in 4 queries.

---

### Example 14: Label-First Query Strategy

**Scenario**: Find all errors in last hour.

**Inefficient** (parses all logs):
```logql
{container=~"huleedu_.*"} | json | level="error" [1h]
```

**Efficient** (uses promoted label):
```logql
{level="error"} [1h]
```

**Performance**: 10x faster using promoted label index.

---

## Related Resources

- **reference.md**: Detailed query patterns and LogQL syntax
- **SKILL.md**: Quick reference and activation criteria
- `/observability/grafana/dashboards/HuleEdu_Troubleshooting.json`: Correlation ID tracing dashboard
- `/observability/LOGQL_SYNTAX_FIX.md`: LogQL syntax corrections
