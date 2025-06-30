#!/bin/bash

echo "Testing full trace propagation through HuleEdu pipeline..."

# Submit a batch with text content directly
echo "1. Submitting batch with text content..."
RESPONSE=$(curl -si -X POST http://localhost:5001/v1/batches/register \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test-user-trace" \
  -d '{
    "course_code": "ENG5",
    "essay_instructions": "Write about distributed tracing in microservices",
    "grading_rubric": "Clarity: 50%, Content: 50%",
    "submission_deadline": "2025-12-31T23:59:59Z",
    "batch_phases": ["SPELLCHECK"],
    "text_contents": [
      {
        "text": "Distributed tracing helps track requests across microservices. It provides visibility into complex systems.",
        "submission_id": "trace-test-001"
      },
      {
        "text": "Observability includes metrics, logs, and traces. These three pillars help understand system behavior.",
        "submission_id": "trace-test-002"  
      }
    ],
    "expected_essay_count": 2,
    "user_id": "test-user-trace"
  }')

# Extract trace ID and batch ID
TRACE_ID=$(echo "$RESPONSE" | grep -i "x-trace-id:" | cut -d' ' -f2 | tr -d '\r')
BATCH_ID=$(echo "$RESPONSE" | tail -1 | jq -r '.batch_id')

echo "Trace ID: $TRACE_ID"
echo "Batch ID: $BATCH_ID"
echo "Jaeger URL: http://localhost:16686/trace/$TRACE_ID"

# Wait for processing
echo -e "\n2. Waiting for processing to propagate through services..."
sleep 15

# Check for services in the trace
echo -e "\n3. Checking services involved in the trace..."
TRACE_DATA=$(curl -s "http://localhost:16686/api/traces/$TRACE_ID")

if [ -z "$TRACE_DATA" ] || [ "$TRACE_DATA" = "{\"data\":null,\"total\":0,\"limit\":0,\"offset\":0,\"errors\":null}" ]; then
    echo "No trace data found. Checking if Jaeger has any traces..."
    curl -s "http://localhost:16686/api/services" | jq .
else
    echo "$TRACE_DATA" | jq '.data[0] | {
        traceID, 
        spanCount: .spans | length, 
        services: .processes | to_entries | map(.value.serviceName) | unique,
        duration: ((.spans | map(.startTime + .duration) | max) - (.spans | map(.startTime) | min)) / 1000000
    }'
fi

# Check Kafka topics for events
echo -e "\n4. Checking for spellcheck events..."
docker exec huleedu_kafka kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic huleedu.essay.spellcheck.requested.v1 \
    --from-beginning \
    --max-messages 5 \
    --timeout-ms 5000 2>/dev/null | grep -o '"correlation_id":"[^"]*"' | tail -2

echo -e "\nTrace propagation test complete!"