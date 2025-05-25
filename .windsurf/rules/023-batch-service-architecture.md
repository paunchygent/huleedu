---
description: "Rules for batch processing operations. Ensures reliable job scheduling and bulk data processing."
globs: 
  - "services/batch_service/**/*.py"
alwaysApply: true
---
# 023: Batch Service Architecture

## 1. Overview
Orchestration service for triggering and managing essay processing workflows.

## 2. Service Identity
- **Name**: `huleedu-batch-service`
- **Port**: 5000
- **Stack**: Quart, aiokafka, aiohttp
- **Type**: HTTP API + Event Producer

## 3. API Endpoints

### 3.1. Active Endpoints
- `POST /v1/trigger-spellcheck`
  - **Request**: `{"text": "essay content"}`
  - **Response**: 
    ```json
    {
      "message": "Spellcheck triggered",
      "essay_id": "uuid",
      "correlation_id": "uuid"
    }
    ```
  - **Status**: 202 Accepted

- `GET /healthz`
  - **Response**: `{"status": "ok"}`
  - **Status**: 200 OK

### 3.2. Planned Endpoints
- `POST /v1/batch` - Create batch
- `POST /v1/batch/{id}/spellcheck` - Trigger batch spellcheck
- `GET /v1/batch/{id}/status` - Get batch status

## 4. Event Flow

### 4.1. Published Events
```python
# Topic: essay.spellcheck.requested.v1
{
  "event": "huleedu.essay.spellcheck.requested.v1",
  "entity_ref": {
    "entity_id": "essay_123",
    "entity_type": "essay"
  },
  "status": "pending_spellcheck",
  "system_metadata": {
    "timestamp": "2025-05-25T12:00:00Z",
    "correlation_id": "corr_123"
  },
  "text_storage_id": "content_123"
}
```

### 4.2. Processing Steps
1. Receive essay via HTTP
2. Store in Content Service
3. Generate IDs
4. Publish event
5. Return response

## 5. Integrations

### 5.1. Content Service
- **Protocol**: HTTP REST
- **Endpoint**: `POST {CONTENT_SERVICE_URL}`
- **Purpose**: Store essay content

### 5.2. Kafka
- **Role**: Event producer
- **Topic**: `essay.spellcheck.requested.v1`
- **Serialization**: JSON + Pydantic

## 6. Configuration

### 6.1. Environment
```env
PORT=5000
HOST=0.0.0.0
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
CONTENT_SERVICE_URL=http://content_service:8000/v1/content
LOG_LEVEL=INFO
```

### 6.2. Dependencies
- `quart>=0.19.4`
- `aiokafka>=0.10.0`
- `aiohttp>=3.9.0`
- `huleedu-common-core`
- `huleedu-service-libs`

## 7. Error Handling

### 7.1. Error Responses
```json
{
  "error": "Service unavailable",
  "details": "Content Service is down"
}
```

### 7.2. HTTP Status Codes
- 400: Bad request
- 500: Server error
- 202: Accepted (async processing)

## 8. Security

### 8.1. Current (MVP)
- No auth
- Basic input validation

### 8.2. Future
- API key auth
- Request validation
- Rate limiting

## 9. Deployment

### 9.1. Docker
- **Base**: `python:3.11-slim`
- **Package Manager**: PDM
- **Command**: `hypercorn app:app -c hypercorn_config.py`

## 10. Monitoring

### 10.1. Logging
- Structured format
- Correlation IDs
- INFO/ERROR levels

### 10.2. Metrics (Future)
- Request rate/latency
- Event publishing success
- Service health
