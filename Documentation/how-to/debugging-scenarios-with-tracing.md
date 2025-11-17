# Debugging Scenarios with Enhanced Observability

## Scenario 1: Storage Reference Key Mismatch (Our Actual Issue)

### Without Distributed Tracing (What We Experienced)

```
1. E2E test fails with "Invalid content ID format"
2. Check logs - only see final error, no context
3. Manually trace through services
4. Eventually find service_result_handler_impl.py:130
5. Discover key mismatch: "storage_id" vs "default"
```

### With Distributed Tracing

```python
# 1. Query Jaeger with correlation ID
GET http://jaeger:16686/api/traces?tags={correlation_id:batch_123}

# 2. See complete trace visualization:
[Spell Checker] --publishes--> {"default": "content_abc123"}
                                    |
                                    v
[ELS Handler] --reads key "storage_id"--> null
                                    |
                                    v
[Storage Update] --stores--> {spellchecked: {storage_id: null}}
                                    |
                                    v
[CJ Assessment] --fetches--> null --> ERROR

# 3. Click on ELS Handler span, see attributes:
span.attributes = {
    "event.data.spellchecked": {"default": "content_abc123"},
    "storage.key_accessed": "storage_id",
    "storage.value_found": null,
    "error": "Key 'storage_id' not found in spellchecked data"
}
```

### Enhanced Error Message

```python
# In service_result_handler_impl.py
storage_id = spellchecked_ref.get("storage_id")
if not storage_id:
    # Log available keys for debugging
    available_keys = list(spellchecked_ref.keys())
    error_context = ErrorContext(
        error_type="StorageReferenceMissing",
        error_message=f"Key 'storage_id' not found. Available keys: {available_keys}",
        service_name="essay_lifecycle_service",
        operation="update_storage_reference",
        context_data={
            "batch_id": batch_id,
            "essay_id": essay_id,
            "phase": "spellchecked",
            "spellchecked_data": spellchecked_ref,
            "expected_key": "storage_id",
            "actual_keys": available_keys
        }
    )
    span.record_exception(EnhancedError("Storage reference extraction failed", error_context))
```

## Scenario 2: Kafka Topic Not Ready

### Without Observability

```
1. Container starts and immediately tries to consume
2. Gets "UnknownTopicOrPartitionError"
3. Container logs show error but no context
4. Don't know if topic exists or consumer failed to connect
```

### With Enhanced Monitoring

```python
# Startup health check with tracing
async def check_kafka_readiness(self) -> bool:
    """Check if Kafka topics are ready before starting consumer."""
    with self.tracer.start_as_current_span("kafka.readiness_check") as span:
        admin_client = AIOKafkaAdminClient(bootstrap_servers=self.kafka_broker)
        await admin_client.start()
        
        try:
            # List topics
            topics = await admin_client.list_topics()
            span.set_attribute("kafka.available_topics", topics)
            
            # Check required topics
            required_topics = [
                "huleedu.spell_checker.check_request.v1",
                "huleedu.els.batch.phase.outcome.v1"
            ]
            
            missing_topics = [t for t in required_topics if t not in topics]
            
            if missing_topics:
                span.set_attribute("kafka.missing_topics", missing_topics)
                span.set_status(Status(StatusCode.ERROR, f"Missing topics: {missing_topics}"))
                
                # Circuit breaker opens, preventing cascading failures
                self.circuit_breaker.record_failure()
                
                # Rich error context
                raise EnhancedError(
                    "Kafka topics not ready",
                    ErrorContext(
                        error_type="KafkaNotReady",
                        error_message=f"Missing required topics: {missing_topics}",
                        service_name=self.service_name,
                        operation="startup_health_check",
                        context_data={
                            "available_topics": topics,
                            "required_topics": required_topics,
                            "missing_topics": missing_topics
                        }
                    )
                )
            
            span.set_attribute("kafka.ready", True)
            return True
            
        finally:
            await admin_client.stop()
```

### Dashboard Alert

```yaml
# Grafana Alert: Kafka Topic Availability
alert: KafkaTopicNotReady
expr: |
  kafka_topic_ready{service_name="$service"} == 0
for: 30s
annotations:
  summary: "Service {{ $labels.service_name }} waiting for Kafka topics"
  description: "Missing topics: {{ $labels.missing_topics }}"
  runbook: "Check Kafka broker logs and topic creation scripts"
```

## Scenario 3: Service Communication Failure

### Without Tracing

```
1. CJ Assessment can't fetch from Content Service
2. See timeout error in logs
3. Don't know if Content Service is down or network issue
4. Check each service individually
```

### With Distributed Tracing

```python
# Trace shows:
[CJ Assessment] --HTTP GET--> [timeout after 30s]
                                    |
                                    x (no span from Content Service)

# Span attributes show:
{
    "http.url": "http://content_service:8000/api/v1/content/abc123",
    "http.method": "GET",
    "error": "ClientTimeout",
    "circuit_breaker.state": "closed",
    "retry.attempt": 3,
    "retry.max": 3
}

# Circuit breaker opens after failures
[CJ Assessment] --HTTP GET--> [Circuit Open - Fast Fail]
                              Returns cached/default response
```

### Enhanced Circuit Breaker Logging

```python
# In circuit_breaker.py
async def call(self, func: Callable, *args, **kwargs) -> Any:
    """Execute with circuit breaker and detailed logging."""
    operation_name = f"{func.__module__}.{func.__name__}"
    
    with self.tracer.start_as_current_span(
        f"circuit_breaker.{operation_name}"
    ) as span:
        span.set_attribute("circuit.state", self.state.value)
        span.set_attribute("circuit.failure_count", self.failure_count)
        span.set_attribute("circuit.threshold", self.failure_threshold)
        
        if self.state == CircuitState.OPEN:
            time_since_failure = datetime.now() - self.last_failure_time
            span.set_attribute("circuit.open_duration", time_since_failure.total_seconds())
            
            logger.warning(
                "Circuit breaker OPEN",
                extra={
                    "operation": operation_name,
                    "failure_count": self.failure_count,
                    "last_failure": self.last_failure_time.isoformat(),
                    "recovery_timeout": self.recovery_timeout.total_seconds()
                }
            )
```

## Scenario 4: Event Processing Pipeline Stall

### Without Observability

```
1. Essays stuck at "spell_check_complete" phase
2. No errors in logs
3. Don't know if handler isn't running or events aren't arriving
```

### With Pipeline Monitoring Dashboard

```sql
-- Prometheus query for pipeline flow
sum by (phase) (
  rate(bos_batch_phase_transitions_total[5m])
)

-- Shows:
parsing_complete -> spell_check_initiated: 10/min
spell_check_complete -> cj_assessment_initiated: 0/min  <-- STALL HERE
```

### Trace Investigation

```python
# Query traces for stalled phase
traces = await jaeger_client.search_traces(
    service="essay_lifecycle_service",
    operation="handle_spell_check_complete",
    start_time=datetime.now() - timedelta(minutes=10)
)

# Find: No traces! Handler not being called

# Check Kafka consumer span
consumer_traces = await jaeger_client.search_traces(
    service="essay_lifecycle_service", 
    operation="kafka.consume.huleedu.spell_checker.check_complete.v1"
)

# Find: Consumer subscribed to wrong topic (underscore vs dot)
span.attributes = {
    "kafka.subscribed_topics": ["huleedu.spell_checker.check_complete.v1"],
    "kafka.received_topic": "huleedu.spell_checker.check.complete.v1",
    "error": "No handler for topic"
}
```

## Scenario 5: Database Query Performance

### Without Observability

```
1. Batch registration takes 30+ seconds
2. Don't know which query is slow
3. Add manual timing logs everywhere
```

### With Tracing

```python
# Automatic span creation for each query
class TracedRepository:
    async def get_essays_for_batch(self, batch_id: str) -> List[Essay]:
        with self.tracer.start_as_current_span(
            "db.query.get_essays_for_batch",
            attributes={
                "db.system": "postgresql",
                "db.statement": "SELECT * FROM essays WHERE batch_id = $1",
                "db.table": "essays",
                "batch_id": batch_id
            }
        ) as span:
            start_time = time.time()
            
            result = await self.db.fetch_all(query, batch_id)
            
            duration = time.time() - start_time
            span.set_attribute("db.rows_returned", len(result))
            span.set_attribute("db.duration_ms", duration * 1000)
            
            if duration > 1.0:  # Slow query
                span.set_attribute("db.slow_query", True)
                logger.warning(
                    "Slow database query",
                    extra={
                        "query": "get_essays_for_batch",
                        "duration_ms": duration * 1000,
                        "rows": len(result),
                        "batch_id": batch_id
                    }
                )
            
            return result
```

### Performance Dashboard Panel

```json
{
  "title": "Database Query Performance",
  "targets": [{
    "expr": "histogram_quantile(0.95, sum(rate(db_query_duration_bucket[5m])) by (le, query))",
    "legendFormat": "p95 - {{query}}"
  }],
  "alert": {
    "condition": "WHEN p95 > 1000 FOR 5m",
    "message": "Database query {{query}} p95 latency > 1s"
  }
}
```

## Quick Debugging Checklist with Observability

### 1. Service Won't Start

- Check Jaeger UI for startup spans
- Look for failed health checks
- Check circuit breaker states in logs
- Verify Kafka topic readiness metrics

### 2. Event Not Processing

- Search Jaeger by correlation ID
- Check pipeline flow dashboard
- Verify consumer lag metrics
- Look for circuit breaker trips

### 3. Slow Performance

- Check trace waterfall for bottlenecks
- Look at span durations by operation
- Check database query performance metrics
- Verify no circuit breakers are limiting throughput

### 4. Data Inconsistency

- Trace data flow with correlation ID
- Check span attributes for data values
- Verify storage operation success metrics
- Look for partial failure patterns

### 5. Integration Failures

- Check service dependency dashboard
- Look for timeout patterns in traces
- Verify circuit breaker metrics
- Check network error rates

## Observability-Driven Development

### Before Deploying

```python
# Add trace points at critical paths
with tracer.start_as_current_span("critical_operation") as span:
    span.set_attribute("input.data", str(input_data)[:100])  # Truncate
    span.set_attribute("processing.step", "validation")
    
    # Critical business logic
    result = await process_data(input_data)
    
    span.set_attribute("output.success", result.success)
    span.set_attribute("output.summary", result.summary)
```

### During Testing

```python
# Assert traces exist for critical paths
async def test_e2e_with_tracing(self):
    # Run test
    correlation_id = await self.run_batch_test()
    
    # Verify traces
    traces = await self.get_traces(correlation_id)
    self.assert_trace_path_exists(traces, [
        "api.batch.register",
        "kafka.publish.spell_check_request",
        "spell_checker.process",
        "storage.update_reference",
        "kafka.publish.cj_assessment_request"
    ])
    
    # Verify no errors in traces
    self.assert_no_span_errors(traces)
```

### In Production

- Set up alerts for trace anomalies
- Use trace sampling for performance
- Archive traces for compliance
- Regular trace analysis for optimization
