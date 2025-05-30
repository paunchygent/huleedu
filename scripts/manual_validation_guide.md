# HuleEdu Batch Coordination Manual Validation Guide

This guide provides step-by-step terminal commands to validate the completed preparatory tasks for batch coordination.

## Prerequisites

- Docker and docker-compose installed
- `jq` installed for JSON processing (`brew install jq` on macOS)
- Terminal access to the project root directory

## Phase 1: Start and Verify Infrastructure

### 1.1 Start All Services

```bash
# From project root directory
docker-compose up -d

# Wait for services to start (30 seconds)
sleep 30

# Check running containers
docker-compose ps
```

### 1.2 Verify Service Health

```bash
# Check Batch Orchestrator Service
curl -s http://localhost:5001/healthz | jq '.'

# Check Essay Lifecycle API
curl -s http://localhost:6001/healthz | jq '.'

# Check Content Service
curl -s http://localhost:8001/healthz | jq '.'

# Check Prometheus metrics endpoints
curl -s http://localhost:5001/metrics | head -5
curl -s http://localhost:6001/metrics | head -5
curl -s http://localhost:8001/metrics | head -5
curl -s http://localhost:8002/metrics | head -5  # Spell Checker metrics
```

## Phase 2: Test New BOS Registration Endpoint

### 2.1 Register a Test Batch

```bash
# Create test batch registration
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "expected_essay_count": 3,
    "essay_ids": ["essay-001", "essay-002", "essay-003"],
    "course_code": "SV1",
    "class_designation": "Class 9A",
    "essay_instructions": "Write a 500-word essay about Swedish literature"
  }' \
  http://localhost:5001/v1/batches/register | jq '.'
```

**Expected Response:**
```json
{
  "batch_id": "uuid-generated-batch-id",
  "correlation_id": "uuid-generated-correlation-id",
  "status": "registered"
}
```

### 2.2 Save Batch ID for Later Tests

```bash
# Save the batch_id from the response above
export BATCH_ID="your-batch-id-here"
echo "Batch ID: $BATCH_ID"
```

## Phase 3: Monitor Event Processing

### 3.1 Check Kafka Topics

```bash
# List all Kafka topics
docker-compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list | grep huleedu

# Expected topics should include:
# huleedu.batch.essays.registered.v1
# huleedu.file.essay.content.ready.v1
# huleedu.els.batch.essays.ready.v1
# huleedu.els.spellcheck.initiate.command.v1
```

### 3.2 Monitor Service Logs

```bash
# Monitor ELS Worker logs for BatchEssaysRegistered processing
docker-compose logs essay_lifecycle_worker | grep -i "batch\|registered"

# Monitor BOS logs
docker-compose logs batch_orchestrator_service | grep -i "batch\|registered"

# Real-time log monitoring (Ctrl+C to stop)
docker-compose logs -f essay_lifecycle_worker
```

### 3.3 Check for Event Processing

```bash
# Look for batch tracking in ELS logs
docker-compose logs essay_lifecycle_worker | grep -i "$BATCH_ID"

# Check if BOS stored the batch context
docker-compose logs batch_orchestrator_service | grep -i "registering.*$BATCH_ID"
```

## Phase 4: Test Content Service Integration

### 4.1 Verify Content Service Functionality

```bash
# Test content storage (needed for File Service integration)
echo "Test essay content for validation" | curl -X POST \
  -H "Content-Type: application/octet-stream" \
  --data-binary @- \
  http://localhost:8001/v1/content | jq '.'
```

**Expected Response:**
```json
{
  "storage_id": "generated-storage-id",
  "message": "Content stored successfully"
}
```

### 4.2 Test Content Retrieval

```bash
# Save storage_id from above response
export STORAGE_ID="your-storage-id-here"

# Retrieve the content
curl -s http://localhost:8001/v1/content/$STORAGE_ID
```

## Phase 5: Validate Kafka Consumer Setup

### 5.1 Check BOS Kafka Consumer

```bash
# Check if BOS has Kafka consumer ready for BatchEssaysReady events
docker-compose logs batch_orchestrator_service | grep -i "kafka\|consumer"
```

### 5.2 Verify Topic Subscriptions

```bash
# Check ELS worker topic subscriptions
docker-compose logs essay_lifecycle_worker | grep -i "subscr\|topic"
```

## Phase 6: Integration Readiness Check

### 6.1 Service Dependency Validation

```bash
# Check all services are responding
echo "=== Service Status Check ==="
echo "BOS Health: $(curl -s -w "%{http_code}" -o /dev/null http://localhost:5001/healthz)"
echo "ELS Health: $(curl -s -w "%{http_code}" -o /dev/null http://localhost:6001/healthz)"
echo "Content Service Health: $(curl -s -w "%{http_code}" -o /dev/null http://localhost:8001/healthz)"
```

### 6.2 Event Infrastructure Status

```bash
# Check Kafka cluster health
docker-compose exec kafka kafka-broker-api-versions.sh --bootstrap-server localhost:9092

# Check topic partitions
docker-compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --describe | grep huleedu
```

## Phase 7: End-to-End Flow Validation

### 7.1 Simulate Complete Flow (without File Service)

Since the File Service is not yet implemented, we can validate the infrastructure:

```bash
# 1. Register batch (already done above)
echo "✅ Batch registration: COMPLETE"

# 2. Verify ELS received BatchEssaysRegistered
docker-compose logs essay_lifecycle_worker | grep -i "batch.*registered" && echo "✅ ELS batch tracking: READY"

# 3. Check BOS Kafka consumer is ready for BatchEssaysReady
docker-compose logs batch_orchestrator_service | grep -i "kafka.*consumer" && echo "✅ BOS consumer: READY"

# 4. Verify Content Service ready for File Service
curl -s http://localhost:8001/healthz | jq '.status' | grep -q "ok" && echo "✅ Content Service: READY"
```

## Troubleshooting Commands

### Check Container Status

```bash
# See which containers are running
docker-compose ps

# Check specific container logs
docker-compose logs <service-name>

# Restart a specific service
docker-compose restart <service-name>
```

### Debug Kafka Issues

```bash
# Check Kafka connectivity
docker-compose exec kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic huleedu.batch.essays.registered.v1 \
  --from-beginning

# Monitor all HuleEdu topics
docker-compose exec kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --whitelist "huleedu.*" \
  --from-beginning
```

### Check Resource Usage

```bash
# Check container resource usage
docker stats

# Check disk space
df -h
```

## Expected Results Summary

After running these validation steps, you should have:

- ✅ All services healthy and responding
- ✅ BOS registration endpoint working
- ✅ Kafka topics created and accessible
- ✅ ELS worker consuming BatchEssaysRegistered events
- ✅ BOS Kafka consumer ready for BatchEssaysReady events
- ✅ Content Service ready for File Service integration
- ✅ Prometheus metrics endpoints functional

## Cleanup

```bash
# Stop all services (optional)
docker-compose down

# Remove volumes (optional - will lose data)
docker-compose down -v
```

## Next Steps

With successful validation, the system is ready for File Service implementation as outlined in the FILE_SERVICE_IMPLEMENTATION_TASK_TICKET.md. 