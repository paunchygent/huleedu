#!/bin/bash

echo "Testing trace propagation with content provisioning..."

# First, register a batch
echo "1. Registering batch..."
BATCH_RESPONSE=$(curl -si -X POST http://localhost:5001/v1/batches/register \
  -H "Content-Type: application/json" \
  -H "X-User-ID: test-trace-user" \
  -d '{
    "course_code": "ENG5",
    "essay_instructions": "Write about distributed tracing",
    "grading_rubric": "Clarity: 50%, Content: 50%",
    "submission_deadline": "2025-12-31T23:59:59Z",
    "batch_phases": ["SPELLCHECK"],
    "expected_essay_count": 1,
    "user_id": "test-trace-user"
  }')

BATCH_ID=$(echo "$BATCH_RESPONSE" | tail -1 | jq -r '.batch_id')
BATCH_TRACE_ID=$(echo "$BATCH_RESPONSE" | grep -i "x-trace-id:" | cut -d' ' -f2 | tr -d '\r')

echo "Batch ID: $BATCH_ID"
echo "Batch Trace ID: $BATCH_TRACE_ID"

# Wait for ELS to create essay slots
echo -e "\n2. Waiting for essay slots to be created..."
sleep 3

# Get essay IDs from ELS
echo -e "\n3. Getting essay IDs..."
ESSAYS_RESPONSE=$(curl -s http://localhost:5007/v1/batches/$BATCH_ID/status)
echo "Batch status response: $ESSAYS_RESPONSE"

# For now, let's use the File Service to upload content
echo -e "\n4. Uploading content via File Service..."
# Create a temporary file
echo "This is a test essay about distributed tracing. It helps track requests across microservices." > /tmp/test-essay.txt

# Upload file using multipart form
FILE_RESPONSE=$(curl -si -X POST http://localhost:7001/v1/files/batch \
  -F "batch_id=$BATCH_ID" \
  -F "files=@/tmp/test-essay.txt")

FILE_TRACE_ID=$(echo "$FILE_RESPONSE" | grep -i "x-trace-id:" | cut -d' ' -f2 | tr -d '\r')
echo "File upload trace ID: $FILE_TRACE_ID"

# Wait for processing
echo -e "\n5. Waiting for spellcheck processing..."
sleep 10

# Check all traces
echo -e "\n6. Checking traces in Jaeger..."
echo "Batch registration trace: http://localhost:16686/trace/$BATCH_TRACE_ID"
echo "File upload trace: http://localhost:16686/trace/$FILE_TRACE_ID"

# Check for spell checker service in Jaeger
echo -e "\n7. Checking services in Jaeger..."
curl -s "http://localhost:16686/api/services" | jq .

# Clean up
rm -f /tmp/test-essay.txt

echo -e "\nTrace test complete!"