---
trigger: model_decision
description: "Rules for the Content Service. Follow for all content management, processing, and delivery features to maintain single responsibility and proper integration."
---

---
description: Defines the architecture and implementation details for the Content Service
globs: 
alwaysApply: false
---
# 021: Content Service Architecture

## 1. Service Identity
- **Package**: `huleedu-content-service`
- **Port**: 8001 (HTTP API)
- **Stack**: Quart, aiofiles, Hypercorn
- **Purpose**: Content storage and retrieval service
- **Architecture**: Blueprint-based API structure

## 2. Service Structure **BLUEPRINT PATTERN**

### 2.1. Directory Structure
```
services/content_service/
├── app.py                     # Lean Quart application (setup, DI, Blueprint registration)
├── api/                       # Blueprint API routes directory
│   ├── __init__.py
│   ├── health_routes.py       # /healthz, /metrics endpoints
│   └── content_routes.py      # /v1/content endpoints
├── config.py                  # Pydantic settings
├── protocols.py               # Service behavioral contracts
├── pyproject.toml
├── Dockerfile
└── tests/
```

### 2.2. Blueprint Implementation
- **app.py**: Lean setup focused on Blueprint registration and dependency sharing
- **api/health_routes.py**: Standard health and metrics endpoints
- **api/content_routes.py**: Content-specific API routes
- **Dependencies**: Shared from app.py to Blueprints via module functions

## 3. API Specification

### 3.1. Endpoints

#### POST /v1/content
- Store content and return storage ID
- **Request**: Raw binary data in request body
- **Response**: `{"storage_id": "uuid"}`
- **Status**: 201 (success), 400 (no data), 500 (storage error)
- **Blueprint**: content_routes.py

#### GET /v1/content/{content_id}
- Retrieve content by storage ID
- **Response**: Raw content data
- **Status**: 200 (success), 404 (not found), 500 (retrieval error)
- **Blueprint**: content_routes.py

#### GET /healthz
- Health check endpoint
- **Response**: `{"status": "ok", "message": "Content Service is healthy"}`
- **Status**: 200 (healthy), 503 (unhealthy)
- **Blueprint**: health_routes.py

#### GET /metrics
- Prometheus metrics endpoint
- **Response**: Metrics in Prometheus format
- **Status**: 200 (success), 500 (error)
- **Blueprint**: health_routes.py

## 4. Storage Implementation

### 4.1. Storage Backend
- **Type**: Local filesystem storage
- **Root Path**: Configurable via `CONTENT_STORE_ROOT_PATH` environment variable
- **Default**: `/data/content_service_store`
- **File Naming**: UUID-based content IDs (no file extensions)

### 4.2. Storage Operations
- **Write**: Async file operations using `aiofiles`
- **Read**: Async file operations using `aiofiles`
- **Persistence**: Docker volume mount for data persistence

## 5. Configuration

### 5.1. Environment Variables
- `CONTENT_STORE_ROOT_PATH`: Storage root directory path
- `PORT`: HTTP server port (default: 8001)
- `LOG_LEVEL`: Logging level (default: INFO)
- `ENV_TYPE`: Environment type (development, docker, etc.)

### 5.2. Dependencies
- `quart>=0.19.4`: Async web framework
- `aiofiles>=23.1.0`: Async file operations
- `hypercorn>=0.16.0`: ASGI server
- `python-dotenv>=1.0.0`: Environment configuration
- `huleedu-common-core`: Shared models and types
- `prometheus-client`: Metrics collection

## 6. Integration Points

### 6.1. Consumers
- **Spell Checker Service**: Fetches original text, stores corrected text
- **Batch Service**: May store uploaded content
- **Future Services**: Any service requiring content storage

### 6.2. Communication Pattern
- **Protocol**: HTTP REST API
- **Data Format**: Raw binary content
- **Service Discovery**: Environment variable `CONTENT_SERVICE_URL`

## 7. Deployment

### 7.1. Docker Configuration
- **Base Image**: `python:3.11-slim`
- **Package Manager**: PDM
- **Volume Mount**: `/data/content_service_store`
- **Health Check**: `/healthz` endpoint
- **Port Exposure**: 8001

### 7.2. Development Commands
- `pdm run start`: Production server with Hypercorn
- `pdm run dev`: Development server with debug mode

## 8. Monitoring and Logging

### 8.1. Logging
- **Utility**: `huleedu_service_libs.logging_utils` (centralized)
- **Levels**: INFO for operations, ERROR for failures
- **Content**: Storage operations, retrieval requests, errors
- **Correlation IDs**: Tracked for all operations

### 8.2. Metrics
- **Request Counts**: HTTP requests by method, endpoint, status
- **Request Duration**: Response time histograms
- **Content Operations**: Storage/retrieval operation counters
- **Endpoint**: `/metrics` (Prometheus format)