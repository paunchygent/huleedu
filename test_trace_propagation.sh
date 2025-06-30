#!/bin/bash

# Test script for trace propagation through the HuleEdu pipeline

echo "Testing trace propagation through HuleEdu pipeline..."

# Submit a test batch
echo "1. Submitting test batch..."
RESPONSE=$(curl -s -X POST http://localhost:5001/api/v1/batches/submit \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test-user-123" \
  -d '{
    "course_code": "EN101",
    "essay_instructions": "Write a short essay about distributed tracing",
    "grading_rubric": "Clarity: 50%, Content: 50%",
    "submission_deadline": "2025-12-31T23:59:59Z",
    "batch_phases": ["SPELLCHECK", "CJ_ASSESSMENT"],
    "text_contents": [
      {
        "text": "This is a test essay about distributed tracing. It helps track requests across multiple services.",
        "submission_id": "test-submission-1"
      },
      {
        "text": "Another test essay discussing observability and monitoring in microservices architectures.",
        "submission_id": "test-submission-2"
      }
    ]
  }')

echo "Response: $RESPONSE"

# Extract batch ID
BATCH_ID=$(echo $RESPONSE | jq -r '.batch_id')
echo "Batch ID: $BATCH_ID"

# Extract X-Trace-ID from response headers (need -i flag for headers)
echo -e "\n2. Getting trace ID from response headers..."
FULL_RESPONSE=$(curl -si -X POST http://localhost:5001/api/v1/batches/submit \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test-user-123" \
  -d '{
    "course_code": "EN101",
    "essay_instructions": "Write a short essay about distributed tracing",
    "grading_rubric": "Clarity: 50%, Content: 50%",
    "submission_deadline": "2025-12-31T23:59:59Z",
    "batch_phases": ["SPELLCHECK", "CJ_ASSESSMENT"],
    "text_contents": [
      {
        "text": "This is a test essay about distributed tracing verification.",
        "submission_id": "test-submission-3"
      }
    ]
  }')

TRACE_ID=$(echo "$FULL_RESPONSE" | grep -i "x-trace-id:" | cut -d' ' -f2 | tr -d '\r')
echo "Trace ID: $TRACE_ID"

echo -e "\n3. Waiting for processing to complete..."
sleep 10

echo -e "\n4. Checking traces in Jaeger..."
echo "You can view the trace at: http://localhost:16686/trace/$TRACE_ID"

# Query Jaeger API for the trace
echo -e "\n5. Querying Jaeger API for trace details..."
curl -s "http://localhost:16686/api/traces/$TRACE_ID" | jq '.data[0] | {traceID, processes: .processes | keys, spanCount: .spans | length}'

echo -e "\nTrace propagation test complete!"