# Sprint 2: Production Readiness & Interface Service Foundations (Revised)

**Document**: Sprint 2 Development Strategy
**Status**: 🎯 **PLANNING** - Industry-grade production readiness approach
**Created**: 2025-06-02 _(Revision based on Client Interaction Layer Design Proposal)_
**Sprint Duration**: 3-4 weeks
**Phase**: Bridge between Walking Skeleton (Phase 1) → Frontend MVP (Phase 2)

## 🎯 **SPRINT 2 OBJECTIVES**

Transform the working walking skeleton into a production-ready platform with essential interface services, following enterprise development best practices and the refined Client Interaction Layer design.

## 🎯 SPRINT 2 KEY DIRECTIONAL DECISIONS

* Confirmed: **FastAPI** for the new API Gateway Service.
* Confirmed: **FastAPI/Starlette** for the new WebSocket Manager Service for consistency.
* Further confirmation on authentication mechanisms (JWT/OAuth2 with FastAPI utilities).
* Explicit decision to use **JSON** as the serialization format in API Gateway until scaling demands justify the complexity of Avro or Protobuf.
* The initial strategy for data queries (API Gateway making direct synchronous calls to backend services).
* Decided: Plan for result aggregation and caching implemented in the new Result Aggregator Service (se PRD:s/PRD,md for details).
* Enhanced details on contract definitions within `common_core`.
* Incorporation of relevant scalability, security, and fault tolerance considerations from the new proposal.

### **Primary Goals**

1. **Production Hardening**: Security, resilience, and error handling.
2. **Interface Service Foundations**: API Gateway and WebSocket Manager implementations using FastAPI.
3. **Enhanced Observability**: Distributed tracing and advanced monitoring.
4. **Performance Validation**: Load testing and optimization.
5. **API Documentation**: OpenAPI specifications for client integration, leveraging FastAPI's capabilities.

### **Success Criteria**

* ✅ All services pass security audit and vulnerability scanning.
* ✅ API Gateway (FastAPI-based) handles authentication, routing, and request aggregation.
* ✅ WebSocket Manager (FastAPI/Starlette-based) provides real-time updates via Kafka integration.
* ✅ Distributed tracing operational across all service interactions.
* ✅ Performance benchmarks established with load testing validation.
* ✅ 100% API documentation coverage with OpenAPI specifications (auto-generated where possible).
* ✅ Enhanced error handling and resilience patterns implemented.

## 📋 **INDUSTRY BEST PRACTICES MANDATE (Incorporating Client Interaction Layer Design)**

### **Key Technology Choices for Interface Services**

* **API Gateway Framework**: FastAPI (Python) for its robust Pydantic integration, automatic OpenAPI generation, performance, and comprehensive feature set for authentication and validation.
* **WebSocket Manager Framework**: FastAPI/Starlette (Python) to ensure consistency with the API Gateway, leverage Pydantic for message schemas, and utilize its async capabilities for Kafka consumption and WebSocket handling.
* **Authentication**: JWT-based (potentially leveraging OAuth2 patterns like `OAuth2PasswordBearer` in FastAPI) for stateless, secure client authentication across HTTP and WebSocket interfaces.
* **Serialization Format**: JSON for all internal Kafka messages (via Pydantic) and all external client communication (API Gateway and WebSocket Manager), ensuring simplicity and web compatibility.
* **Data Query/Read Path (Initial Strategy)**: The API Gateway will handle synchronous client queries by making direct, non-blocking API calls to the appropriate backend services.

### **Security-First Approach**

At this stage, enterprise applications require:

* **Authentication & Authorization**: JWT-based security with proper token management via the API Gateway and WebSocket Manager.
* **Input Validation**: Comprehensive request validation and sanitization using Pydantic models at the API Gateway and for any WebSocket client messages.
* **HTTPS Everywhere**: TLS encryption (HTTPS/WSS) for all external communications.
* **Security Scanning**: Automated SAST/DAST integration in CI/CD.
* **Vulnerability Management**: Dependency scanning and security patching.

### **Production Readiness Standards**

* **Error Handling**: Structured error responses, retry mechanisms (client-side where appropriate), circuit breakers (if deemed necessary for specific internal calls).
* **Observability**: Distributed tracing, centralized logging (with correlation IDs), advanced metrics.
* **Performance**: Load testing, resource optimization, SLA definitions.
* **Resilience**: Health checks, graceful degradation, timeout management for internal service calls from the API Gateway.
* **Documentation**: API specifications (OpenAPI), service documentation, operational runbooks.

### **Interface Service Requirements (Aligned with PRD Phase 2 & Client Interaction Layer Design)**

* **API Gateway**: Single entry point built with FastAPI, integrated JWT authentication, dynamic routing to backend services (for commands via Kafka, for queries via direct calls), and response aggregation.
* **WebSocket Manager**: Real-time communication backbone using FastAPI/Starlette, consuming Kafka events and distributing them to authenticated WebSocket clients.
* **Result Aggregator**: Skeleton service for dashboard data consolidation and caching, designed to be queried by the API Gateway.

---

## 🚀 **SPRINT 2 EXECUTION PHASES**

## **PHASE 1: Security & Authentication Foundation**

**Priority**: CRITICAL | **Duration**: 1 week | **Dependencies**: None

### **S2.1: API Gateway & WebSocket Authentication & Security**

**Objective**: Implement JWT-based authentication and HTTPS/WSS security in API Gateway and WebSocket Manager.

**Tasks**:

* [ ] **JWT Authentication Middleware (FastAPI)**: Implement token generation (if applicable, e.g., a login endpoint), validation (using FastAPI's `OAuth2PasswordBearer` or similar), and refresh mechanisms in the API Gateway.
* [ ] **WebSocket Authentication (FastAPI/Starlette)**: Secure WebSocket connections by validating JWT during the handshake.
* [ ] **HTTPS/WSS Configuration**: TLS certificates and secure communication setup for all external endpoints.
* [ ] **Input Validation (Pydantic)**: Ensure all API Gateway endpoints and any WebSocket client-sent messages use Pydantic models for validation.
* [ ] **Security Headers**: CORS, CSP, and security header configuration in the API Gateway.

**Deliverables**:

* API Gateway and WebSocket Manager with integrated JWT authentication.
* HTTPS/WSS configuration for all external endpoints.
* Pydantic-based input validation framework utilized.

**Acceptance Criteria**:

* JWT authentication flow operational in API Gateway (e.g., login, validate token).
* WebSocket connections successfully authenticate using JWT.
* All external communications use HTTPS/WSS.
* Input validation prevents common security vulnerabilities.
* Security headers properly configured.

---

### **S2.2: Security Scanning & Compliance**

**Objective**: Integrate automated security scanning and vulnerability management.

**Tasks**:

* [ ] **CI Security Integration**: SAST/DAST scanning in GitHub Actions.
* [ ] **Dependency Scanning**: Automated vulnerability detection for all packages.
* [ ] **Security Audit Framework**: Manual security testing checklist.
* [ ] **Secrets Management**: Secure handling of API keys (e.g., JWT signing secret) and sensitive configuration.
* [ ] **Security Documentation**: Update security architecture and threat model documentation to include new interface services.

**Deliverables**:

* Automated security scanning in CI pipeline.
* Vulnerability management process.
* Security audit checklist and procedures.
* Secrets management implementation.

**Acceptance Criteria**:

* No critical or high severity vulnerabilities in codebase.
* Secrets properly managed and not exposed in configuration.
* Security scanning integrated in CI/CD pipeline.
* Security audit documentation updated.

---

## **PHASE 2: Interface Service Development**

**Priority**: HIGH | **Duration**: 1.5 weeks | **Dependencies**: Phase 1

### **S2.3: API Gateway Service Implementation (FastAPI)**

**Objective**: Create the primary frontend interface service using FastAPI, with routing, command-to-event translation, and query handling.

**Tasks**:

* [ ] **API Gateway Architecture (FastAPI)**: Develop the service using FastAPI, organizing with routers (similar to Blueprints). Structure will include `main.py` (FastAPI app setup), API route modules, Pydantic models for DTOs (in `common_core` or service-local if truly specific).
* [ ] **Request Routing & Command Handling**:
  * For write operations/commands: Translate authenticated HTTP requests into Kafka command events (using `EventEnvelope` from `common_core`) and publish them using `aiokafka`. Return HTTP 202 Accepted with a correlation ID.
  * For read operations/queries: Handle requests by making direct, non-blocking HTTP calls to appropriate backend services (e.g., using `httpx`).
* [ ] **Response Aggregation**: For query endpoints, combine data from multiple internal service calls if necessary.
* [ ] **Rate Limiting**: Implement rate limiting (e.g., using `slowapi` with FastAPI) to protect backend services.
* [ ] **Logging Integration**: Ensure use of `huleedu_service_libs.logging_utils` with correlation IDs propagated from requests or generated for new commands.
* [ ] **Contract Definitions**: Define all API request and response Pydantic models in `common_core` (e.g., in `common_core.api_models.gateway.v1`) for versioning and reusability.

**Service Structure (Example for FastAPI)**:

``` text
services/api_gateway_service/
├── main.py                    # FastAPI application setup, middleware
├── api/                       # Directory for API routers
│   ├── __init__.py
│   ├── health_routes.py       # REQUIRED: /healthz, /metrics endpoints
│   ├── auth_routes.py         # JWT authentication endpoints (e.g., login)
│   ├── batch_routes.py        # Batch management API (commands & queries)
│   ├── file_routes.py         # File upload proxy (if routed via gateway)
│   └── results_routes.py      # Results query endpoints
├── core_logic/                # Business logic for command mapping, query orchestration
│   ├── __init__.py
│   ├── command_mapper.py      # Logic to map HTTP requests to Kafka events
│   └── query_orchestrator.py  # Logic to call backend services for queries
├── implementations/           # Implementations of protocols if complex (e.g., custom auth logic beyond FastAPI utils)
│   ├── __init__.py
│   └── rate_limiter.py        # (If using a custom class-based rate limiter)
├── config.py                  # Pydantic BaseSettings configuration
├── di.py                      # Dishka dependency injection providers (e.g., for Kafka producer)
└── pyproject.toml
```

**Acceptance Criteria**:

* API Gateway built with FastAPI, exposing documented endpoints including `/healthz` and `/metrics`.
* JWT authentication middleware correctly validates tokens.
* Write operations translate to Kafka events; query operations retrieve data from backend services.
* Response aggregation for queries combines data correctly.
* Rate limiting protects backend services effectively.
* Standardized logging with correlation IDs is implemented.
* API contracts (request/response models) are defined in `common_core`.

---

### **S2.4: WebSocket Manager Service Implementation (FastAPI/Starlette)**

**Objective**: Enable real-time communication using FastAPI/Starlette, consuming Kafka events and pushing them to authenticated clients.

**Tasks**:

* [ ] **WebSocket Service Architecture (FastAPI/Starlette)**: Develop the service with FastAPI, defining WebSocket endpoint(s).
* [ ] **Kafka Event Consumer (`aiokafka`)**: Run an `aiokafka` consumer in a background task (managed by FastAPI's lifecycle events) to subscribe to relevant Kafka topics (defined in `common_core.enums`).
* [ ] **WebSocket Server Logic**: Manage WebSocket connection lifecycle (connect, disconnect), handle JWT authentication during handshake.
* [ ] **Event Filtering & Routing**: Filter consumed Kafka events based on client subscriptions (e.g., by correlation ID, entity ID) and route them to appropriate subscribed clients.
* [ ] **Contract Definitions**: Define WebSocket message Pydantic models (e.g., for server-to-client events, client subscription messages) in `common_core` (e.g., in `common_core.api_models.websocket.v1`).

**Service Structure (Example for FastAPI/Starlette)**:

``` text
services/websocket_manager_service/
├── main.py                    # FastAPI app setup, WebSocket endpoint(s)
├── kafka_consumer.py          # Kafka consumer logic, event processing
├── connection_manager.py      # Manages active WebSocket connections & subscriptions
├── event_router.py            # Logic to route Kafka events to connected clients
├── config.py                  # Pydantic BaseSettings configuration
├── di.py                      # Dishka DI providers (e.g., for Kafka consumer, connection manager)
└── pyproject.toml
```

_(Note: `protocols.py` and `protocol_implementations/` might be less relevant if logic is directly in `connection_manager.py` or `event_router.py`, but can be used if complex abstractions are needed.)_

**Acceptance Criteria**:

* WebSocket Manager built with FastAPI/Starlette, including `/healthz` and `/metrics` HTTP endpoints.
* WebSocket connections are authenticated using JWT.
* Backend Kafka events from subscribed topics are processed and routed to appropriate, authenticated frontend clients.
* Connection lifecycle and client subscriptions are managed effectively.
* Event filtering ensures clients receive relevant updates only.
* Standardized logging with correlation IDs (where applicable) is implemented.
* WebSocket message contracts are defined in `common_core`.

---

### **S2.5: Result Aggregator Service Skeleton**

**Objective**: Foundation service for dashboard data aggregation and queries, designed for interaction with the API Gateway.

**Service Structure (Hybrid: FastAPI for API, `aiokafka` for worker)**:

``` text
services/result_aggregator_service/
├── main.py                    # FastAPI application setup for API endpoints
├── api/
│   ├── __init__.py
│   ├── health_routes.py       # REQUIRED: /healthz, /metrics endpoints
│   └── dashboard_routes.py    # Dashboard data query endpoints (queried by API Gateway)
├── worker_main.py             # Kafka event consumer entry point (if separate process)
├── event_processor.py         # Logic for consuming events and updating aggregated views/cache
├── data_aggregator.py         # Core logic for aggregating data from various sources/events
├── cache_manager.py           # Caching strategy implementation (e.g., Redis, in-memory)
├── config.py                  # Pydantic BaseSettings configuration
├── di.py                      # Dishka dependency injection providers
└── pyproject.toml
```

_(Note: `protocols.py` and `implementations/` can be used to structure `data_aggregator.py`, `cache_manager.py`, `event_processor.py` if beneficial.)_

**Tasks**:

* [ ] **Hybrid Service Architecture**: Design with a FastAPI HTTP API (for queries from API Gateway) and an `aiokafka` worker component for consuming events.
* [ ] **Data Aggregation Logic**: Initial logic for combining results or states from backend service events.
* [ ] **Query Interface**: Define API endpoints for the API Gateway to fetch aggregated dashboard data.
* [ ] **Caching Strategy**: Outline and implement a basic caching strategy for frequently accessed data.
* [ ] **Event Consumer**: Set up Kafka consumer to listen to relevant result/status events and update aggregations/cache.

**Acceptance Criteria**:

* Service provides API endpoints for aggregated data, callable by the API Gateway.
* Dashboard queries return properly formatted data.
* Basic caching mechanism is in place.
* Event consumption updates aggregations or cache as expected.

---

## **PHASE 3: Advanced Observability & Performance**

**Priority**: HIGH | **Duration**: 1 week | **Dependencies**: Phases 1-2

### **S2.6: Distributed Tracing Implementation**

**Objective**: Implement comprehensive distributed tracing across all services, including new interface services.

**Tasks**:

* [ ] **OpenTelemetry Integration**: Add OpenTelemetry instrumentation to all microservices (including FastAPI Gateway & WebSocket Manager).
* [ ] **Jaeger Setup**: Deploy Jaeger for trace collection and visualization (e.g., in `docker-compose.yml`).
* [ ] **Correlation ID Enhancement**: Ensure robust propagation and logging of correlation IDs across HTTP, Kafka, and WebSocket interactions.
* [ ] **Performance Insights**: Use traces to identify bottlenecks and optimization opportunities.
* [ ] **Trace Analysis**: Establish a dashboard or process for analyzing service interactions via Jaeger.

**Deliverables**:

* Distributed tracing across all service interactions.
* Jaeger deployment for trace visualization.
* Documented performance bottlenecks.
* Trace analysis dashboard/guidelines.

**Acceptance Criteria**:

* All service interactions (HTTP calls via Gateway, Kafka events, WebSocket messages) are captured in distributed traces.
* End-to-end request tracking is demonstrable.
* Performance bottlenecks are identified and documented.
* Trace analysis provides actionable insights.

---

### **S2.7: Performance Testing & Optimization**

**Objective**: Establish performance benchmarks and optimize critical paths, especially for the new interface layer.

**Tasks**:

* [ ] **Load Testing Framework**: Implement automated load testing (e.g., using k6, Locust) for realistic scenarios targeting the API Gateway and WebSocket Manager.
* [ ] **Performance Benchmarking**: Establish SLA targets for critical API Gateway endpoints and WebSocket message throughput/latency.
* [ ] **Resource Optimization**: Optimize container resources (CPU, memory) and application performance for all services.
* [ ] **Scalability Testing**: Test horizontal scaling patterns for the API Gateway and WebSocket Manager.
* [ ] **Performance Monitoring**: Enhance Prometheus metrics for performance tracking of new services.

**Testing Scenarios**:

* API Gateway handling concurrent command submissions (translating to Kafka events) and query requests.
* WebSocket Manager handling concurrent connections and broadcasting high-frequency events.
* Batch registration and file upload under load (as initiated via API Gateway).
* Concurrent spell checking processing (end-to-end flow initiated via gateway).

**Deliverables**:

* Automated load testing suite.
* Performance benchmarks and SLA definitions.
* Resource optimization recommendations.
* Scalability test results for interface services.

**Acceptance Criteria**:

* Load testing validates platform handles expected user volumes (e.g., 1000 concurrent users).
* API Gateway and WebSocket Manager performance benchmarks meet or exceed SLA requirements (e.g., API response times < 500ms 95th percentile).
* Resource utilization optimized.
* Horizontal scaling patterns for interface services proven effective.

---

## **PHASE 4: API Documentation & Integration Preparation**

**Priority**: MEDIUM | **Duration**: 0.5 weeks | **Dependencies**: Phases 1-3

### **S2.8: OpenAPI Specification & Documentation**

**Objective**: Complete API documentation for frontend integration, leveraging FastAPI for API Gateway.

**Tasks**:

* [ ] **OpenAPI Specs (FastAPI)**: Generate comprehensive OpenAPI documentation for all API Gateway endpoints (leveraging FastAPI's auto-generation from Pydantic models and route definitions).
* [ ] **WebSocket API Documentation**: Document WebSocket connection endpoints, authentication, and message formats (based on `common_core` Pydantic models).
* [ ] **Client SDK Generation**: Generate TypeScript client SDKs from OpenAPI specs for the API Gateway.
* [ ] **API Testing**: Implement contract testing to validate API specifications against running services.
* [ ] **Integration Documentation**: Create frontend integration guides and examples for using the API Gateway and WebSocket Manager.
* [ ] **Versioning Strategy**: Finalize and document API versioning and deprecation policies.

**Deliverables**:

* Complete OpenAPI specifications for all public APIs (API Gateway).
* Documented WebSocket API.
* Generated TypeScript client SDKs.
* API contract testing suite.
* Frontend integration documentation.

**Acceptance Criteria**:

* 100% API Gateway endpoint coverage in OpenAPI specifications.
* WebSocket API is clearly documented.
* Generated client SDKs provide type-safe frontend integration for API Gateway.
* Contract tests validate API specifications accuracy.
* Documentation enables efficient frontend development.

---

## **📊 QUALITY GATES & ACCEPTANCE CRITERIA**

_(This section remains largely the same but implicitly now applies to the new FastAPI-based services as well)_

### **Security Quality Gates**

* [ ] **Zero Critical Vulnerabilities**: No critical or high severity security issues.
* [ ] **Authentication Testing**: JWT flows for API Gateway and WebSocket Manager tested and secure.
* [ ] **Input Validation**: All API Gateway endpoints and relevant WebSocket messages validate and sanitize input using Pydantic.
* [ ] **HTTPS/WSS Enforcement**: All external communications encrypted.
* [ ] **Security Headers**: Proper security headers configured on API Gateway.

### **Performance Quality Gates**

* [ ] **Load Testing**: Platform handles target concurrent users (e.g., 1000).
* [ ] **Response Times**: API Gateway endpoints respond within target (e.g., 500ms 95th percentile). WebSocket message delivery latency meets targets.
* [ ] **Resource Utilization**: Container resource usage optimized.
* [ ] **Scalability**: Horizontal scaling for API Gateway and WebSocket Manager validated.
* [ ] **SLA Compliance**: All performance targets met.

### **Integration Quality Gates**

* [ ] **API Gateway**: All intended backend services/functionalities accessible via gateway.
* [ ] **WebSocket Manager**: Real-time updates functional and correctly routed.
* [ ] **Authentication**: End-to-end authentication flow working for HTTP and WebSockets.
* [ ] **Distributed Tracing**: Key service interactions traced.
* [ ] **Documentation**: 100% API coverage in specifications (API Gateway).

### **Operational Quality Gates**

* [ ] **Health Checks**: All services, including new interface services, provide detailed health information.
* [ ] **Monitoring**: Enhanced metrics and alerting operational for new services.
* [ ] **Error Handling**: Graceful error responses and recovery mechanisms implemented.
* [ ] **Logging**: Centralized, structured logging with correlation IDs implemented across all services.
* [ ] **CI/CD**: All quality gates automated in pipeline.

---

## **🔄 RISK MITIGATION & CONTINGENCY**

_(Risks are generally similar, but mitigations might now involve FastAPI-specific considerations)_

### **Technical Risks**

* **Risk**: Authentication integration complexity with FastAPI/JWT.
  * **Mitigation**: Leverage FastAPI's built-in OAuth2 utilities; start with simple JWT validation, iterate.
* **Risk**: WebSocket scaling challenges with FastAPI/Starlette.
  * **Mitigation**: Implement recommended Kafka consumer group strategy (unique IDs for broadcast), connection pooling, and test horizontal scaling patterns.
* **Risk**: Performance optimization complexity for FastAPI services.
  * **Mitigation**: Focus on critical path optimization first; utilize async capabilities effectively.

### **Schedule Risks**

* **Risk**: Interface service development complexity (even with FastAPI).
  * **Mitigation**: Implement minimal viable services first, enhance iteratively based on frontend needs.
* **Risk**: Learning curve for FastAPI if team is predominantly Quart-focused.
  * **Mitigation**: Focused learning sessions, pair programming, leverage FastAPI's extensive documentation.
* **Risk**: Security implementation time overruns.
  * **Mitigation**: Prioritize authentication and basic security, defer advanced features if necessary.

### **Quality Risks**

* **Risk**: Security vulnerabilities in new FastAPI-based services.
  * **Mitigation**: Automated security scanning, thorough code reviews, regular security audits.
* **Risk**: Performance regression in existing services due to interaction with new gateway.
  * **Mitigation**: Continuous performance monitoring, regression testing.

---

## **🎯 SPRINT 2 SUCCESS DEFINITION**

### **Industry-Grade Deliverables**

1. **Production Security**: Robust JWT-based authentication, HTTPS/WSS, input validation, vulnerability scanning for all services.
2. **Interface Services (FastAPI-based)**: API Gateway and WebSocket Manager operational and meeting functional requirements.
3. **Advanced Observability**: Distributed tracing, enhanced metrics, performance insights.
4. **Performance Validation**: Load testing, optimization, SLA compliance for interface services.
5. **API Documentation**: Complete OpenAPI specs for API Gateway, well-documented WebSocket API, client SDKs.

### **Readiness for Phase 2 (Frontend MVP)**

* ✅ **Authentication Infrastructure**: JWT-based auth via FastAPI Gateway ready for frontend integration.
* ✅ **API Gateway (FastAPI)**: Single, secure entry point for all frontend requests.
* ✅ **Real-time Communication (FastAPI)**: WebSocket Manager for live updates to the frontend.
* ✅ **Performance Validated**: Platform ready for production user loads through the new interface layer.
* ✅ **Documentation Complete**: Frontend developers can integrate efficiently with well-defined APIs.

### **Business Value Delivered**

* **Security Compliance**: Platform meets enterprise security standards.
* **Scalability Foundation**: Architecture (including new interface services) proven to handle growth.
* **Developer Experience**: Well-documented FastAPI-based APIs enable rapid frontend development.
* **Operational Excellence**: Comprehensive monitoring and troubleshooting capabilities.
* **Production Readiness**: Platform ready for real user traffic via a modern, robust interface layer.

---
**🏆 SPRINT 2 VISION (Revised)**: Transform the walking skeleton into a production-ready, secure, observable, and scalable platform, featuring a high-performance **FastAPI-based client interaction layer (API Gateway and WebSocket Manager)** that provides the perfect foundation for frontend development and real-world deployment.
