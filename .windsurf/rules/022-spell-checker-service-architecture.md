---
description: "Rules for the Spell Checker Service. Ensures consistent text processing in an event-driven architecture."
globs: 
  - "services/spell_checker_service/**/*.py"
alwaysApply: true
---
# 022: Spell Checker Service Architecture

## 1. Overview

Event-driven worker service for spell checking essays. Consumes from Kafka, processes text, and publishes results.

## 2. Service Identity

- **Name**: `huleedu-spell-checker-service`
- **Type**: Kafka Consumer Worker
- **Stack**: aiokafka, aiohttp, asyncio

## 3. Event Flow

### 3.1. Input

- **Topic**: `essay.spellcheck.requested.v1`
- **Model**: `SpellcheckRequestedDataV1`
- **Group**: `spellchecker-service-group`

### 3.2. Output

- **Topic**: `essay.spellcheck.completed.v1`
- **Model**: `SpellcheckResultDataV1`

### 3.3. Processing Steps

1. Consume event from Kafka
2. Fetch text from Content Service
3. Apply spell checking
4. Store corrected text
5. Publish results
6. Commit offset

## 4. Integrations

### 4.1. Content Service

- **Protocol**: HTTP REST
- **Endpoints**:
  - `GET {CONTENT_SERVICE_URL}/{id}`
  - `POST {CONTENT_SERVICE_URL}`

### 4.2. Kafka

- **Consumer**: AIOKafkaConsumer
- **Producer**: AIOKafkaProducer
- **Serialization**: JSON + Pydantic

## 5. Implementation

### 5.1. Current (MVP)

- Simple string replacements
- Example: "teh" → "the"

### 5.2. Future

- Advanced spell checking
- Grammar checking
- Language detection

## 6. Configuration

### 6.1. Env Vars

- `KAFKA_BOOTSTRAP_SERVERS=kafka:9092`
- `CONTENT_SERVICE_URL=http://content_service:8000/v1/content`
- `LOG_LEVEL=INFO`

### 6.2. Dependencies

- `aiokafka>=0.10.0`
- `aiohttp>=3.9.0`
- `huleedu-common-core`
- `huleedu-service-libs`

## 7. Error Handling

### 7.1. Error Cases

- Content Service down
- Invalid events
- Processing failures
- Storage issues

### 7.2. Resilience

- Manual offset commits
- Future: Circuit breakers, DLQ, retries

## 8. Data Models

### 8.1. Input Event

```python
class SpellcheckRequestedDataV1:
    event: str
    entity_ref: EntityReference
    status: str
    system_metadata: SystemProcessingMetadata
    text_storage_id: str
```

### 8.2. Output Event

```python
class SpellcheckResultDataV1:
    event: str
    entity_ref: EntityReference
    status: str
    system_metadata: SystemProcessingMetadata
    storage_metadata: StorageReferenceMetadata
    corrections_made: int
```

## 9. Monitoring

### 9.1. Logging

- Structured format
- Correlation IDs
- INFO/ERROR levels

### 9.2. Metrics (Future)

- Throughput
- Latency
- Success rate

## 10. Deployment

### 10.1. Docker

- `python:3.11-slim`
- PDM for dependencies
- `python worker.py` entrypoint

## 11. Security

### 11.1. Current

- No auth (dev only)
- No encryption (dev only)
- Pydantic validation only

### 11.2. Future

- Service auth
- Message encryption
- Input sanitization

## 12. Performance

### 12.1. Current

- Single-threaded async
- HTTP-bound performance

### 12.2. Optimizations

- Parallel processing
- Caching
- Batch processing
- Connection pooling
