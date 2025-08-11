# HuleEdu Frontend Integration Documentation

## Overview

This documentation provides comprehensive guidance for integrating frontend applications with the HuleEdu API Gateway and WebSocket services. The documentation is organized by use case to help developers quickly find the information they need.

## Quick Navigation

### 🛠️ **Complete Integration Guide**

- **[Svelte Integration Guide](SVELTE_INTEGRATION_GUIDE.md)** - Complete Svelte 5 integration from setup to production deployment
- **[Shared Code Patterns](SHARED_CODE_PATTERNS.md)** - Reusable implementation patterns, utilities, and base clients  
- **[API Reference](API_REFERENCE.md)** - Complete TypeScript types, interfaces, and API specifications

### 📡 **WebSocket Communication**

- **[WebSocket API Documentation](WEBSOCKET_API_DOCUMENTATION.md)** - Technical WebSocket API reference and protocols
- **[Frontend Readiness Checklist](../TASKS/FRONTEND_READINESS_CHECKLIST.md)** - Implementation checklist
- **[API Gateway OpenAPI Specification](http://localhost:4001/docs)** - Interactive API documentation
- **[Common Core Models](../libs/common_core/src/common_core/models/)** - Pydantic model definitions (source of truth)

## Decision Tree: Which Guide Do I Need?

```text
Are you just getting started with HuleEdu integration?
├─ YES → Start with Svelte Integration Guide (covers setup to production)
└─ NO → Continue below

Do you need real-time notifications or live updates?
├─ YES → WebSocket API Documentation + Svelte Integration Guide
└─ NO → Continue below

Do you need TypeScript types and API specifications?
├─ YES → API Reference
└─ NO → Continue below

Do you need reusable code patterns and utilities?
├─ YES → Shared Code Patterns
└─ NO → Start with Svelte Integration Guide for comprehensive examples
```

## Architecture Overview

The HuleEdu platform consists of several services that frontend applications interact with:

### **API Gateway Service** (Port 4001)
- **Authentication**: JWT-based authentication (HS256) for all endpoints except `/healthz` and `/v1/test/no-auth`
- **Batch Management**: Create, upload, and manage essay batches via `/v1/batches/` endpoints
- **Pipeline Control**: Request processing pipelines for batches via `/v1/batches/{batch_id}/pipelines`
- **Status Monitoring**: Real-time batch and processing status via `/v1/batches/{batch_id}/status`
- **File Operations**: File upload proxy via `/v1/files/batch`
- **CORS Support**: Configured for development ports (3000, 3001) and production origins
- **Rate Limiting**: 100 requests per minute per client (configurable)
- **Circuit Breaker**: Automatic failure protection for downstream services

### **WebSocket Service** (Port 8081)
- **Real-Time Notifications**: 15+ notification types for teachers
- **Connection Management**: JWT authentication via query parameter
- **Event Categories**: Batch progress, processing results, file operations, class management
- **Priority Levels**: Critical, immediate, high, standard, low

### **Core Services**
- **Batch Orchestrator**: Manages batch lifecycle and processing
- **Essay Lifecycle**: Handles individual essay processing states
- **Spellcheck Service**: Provides spelling and grammar analysis
- **Content Judgment**: AI-powered content assessment

## Common Integration Patterns

### **Authentication Flow**
1. Obtain JWT token from your authentication service
2. Store token securely (preferably httpOnly cookies)
3. Include `Authorization: Bearer <token>` header in API requests
4. Handle token refresh and expiration

### **Error Handling Strategy**
1. Implement retry logic with exponential backoff
2. Handle specific error types (401, 403, 429, 5xx)
3. Use correlation IDs for debugging
4. Implement circuit breaker patterns for resilience

### **Real-Time Updates**
1. Establish WebSocket connection with JWT authentication
2. Handle connection lifecycle (connect, disconnect, reconnect)
3. Process notifications based on type, category, and priority
4. Update UI state based on real-time events

## Best Practices Summary

1. **Always use correlation IDs** for request tracking and debugging
2. **Implement proper error boundaries** to catch and handle API errors gracefully
3. **Use exponential backoff** for retry logic on transient failures
4. **Store JWT tokens securely** (prefer httpOnly cookies over localStorage)
5. **Implement token refresh** to maintain user sessions
6. **Handle rate limiting** with appropriate retry strategies
7. **Use TypeScript types** for all API interactions to ensure type safety
8. **Implement proper loading states** for better user experience
9. **Log correlation IDs** for debugging and support purposes
10. **Test WebSocket reconnection** scenarios in your application

## Environment Configuration

### **Required Environment Variables**

Based on the API Gateway Service configuration (`services/api_gateway_service/config.py`):

#### **Core Service Configuration**
- `API_GATEWAY_HTTP_HOST`: HTTP server host (default: "0.0.0.0")
- `API_GATEWAY_HTTP_PORT`: HTTP server port (default: 4001)
- `API_GATEWAY_SERVICE_NAME`: Service identifier (default: "api-gateway-service")
- `API_GATEWAY_LOG_LEVEL`: Logging level (default: "INFO")
- `API_GATEWAY_ENV_TYPE`: Environment type (default: "development")

#### **Security Configuration**
- `API_GATEWAY_JWT_SECRET_KEY`: JWT signing secret (required for production)
- `API_GATEWAY_JWT_ALGORITHM`: JWT algorithm (default: "HS256")

#### **CORS Configuration**
- `API_GATEWAY_CORS_ORIGINS`: Allowed origins (default: ["http://localhost:3000", "http://localhost:3001"])
- `API_GATEWAY_CORS_ALLOW_CREDENTIALS`: Allow credentials (default: true)
- `API_GATEWAY_CORS_ALLOW_METHODS`: Allowed HTTP methods (default: ["GET", "POST", "PUT", "DELETE", "OPTIONS"])
- `API_GATEWAY_CORS_ALLOW_HEADERS`: Allowed headers (default: ["*"])

#### **Service Dependencies**
- `API_GATEWAY_CMS_API_URL`: Class Management Service URL (default: "http://class_management_service:8000")
- `API_GATEWAY_FILE_SERVICE_URL`: File Service URL (default: "http://file_service:8000")
- `API_GATEWAY_RESULT_AGGREGATOR_URL`: Result Aggregator Service URL (default: "http://result_aggregator_service:8000")
- `API_GATEWAY_KAFKA_BOOTSTRAP_SERVERS`: Kafka servers (default: "kafka:9092")
- `API_GATEWAY_REDIS_URL`: Redis URL (default: "redis://redis:6379")

#### **Performance & Resilience**
- `API_GATEWAY_HTTP_CLIENT_TIMEOUT_SECONDS`: HTTP client timeout (default: 30)
- `API_GATEWAY_HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS`: Connection timeout (default: 10)
- `API_GATEWAY_RATE_LIMIT_REQUESTS`: Rate limit per minute (default: 100)
- `API_GATEWAY_RATE_LIMIT_WINDOW`: Rate limit window in seconds (default: 60)
- `API_GATEWAY_CIRCUIT_BREAKER_ENABLED`: Enable circuit breaker (default: true)
- `API_GATEWAY_HTTP_CIRCUIT_BREAKER_FAILURE_THRESHOLD`: Failure threshold (default: 5)
- `API_GATEWAY_HTTP_CIRCUIT_BREAKER_RECOVERY_TIMEOUT`: Recovery timeout (default: 60)

## Support and Troubleshooting

### **Common Issues**
- **CORS Errors**: Ensure your development server is running on a supported port (3000, 3001) or configure `API_GATEWAY_CORS_ORIGINS`
- **Authentication Failures**: Check JWT token format (Bearer), algorithm (HS256), and required claims (`sub`, `exp`)
- **WebSocket Connection Issues**: Verify JWT token is included in query parameter for port 8081
- **Rate Limiting**: Default 100 requests/minute - implement proper retry logic with server-specified delays
- **Circuit Breaker**: Service may be temporarily unavailable due to downstream failures

### **Debugging**
- Check correlation IDs in error responses
- Review the OpenAPI specification at `/docs` endpoint
- Monitor health endpoints for service status
- Use browser developer tools to inspect network requests

### **Getting Help**
- Consult the specific guide for your use case
- Check existing TypeScript types for API contracts
- Review error messages and correlation IDs
- Test against health endpoints to verify service availability

---

## Document Status

| Document | Status | Last Updated |
|----------|--------|--------------|
| [Svelte Integration Guide](SVELTE_INTEGRATION_GUIDE.md) | ✅ Available | 2025-08-11 |
| [Shared Code Patterns](SHARED_CODE_PATTERNS.md) | ✅ Available | 2025-08-11 |
| [API Reference](API_REFERENCE.md) | ✅ Available | 2025-08-11 |
| [WebSocket API Documentation](WEBSOCKET_API_DOCUMENTATION.md) | ✅ Available | 2025-08-11 |

---

*This documentation is part of the HuleEdu platform. For technical support or questions, include correlation IDs from error responses when reporting issues.*
