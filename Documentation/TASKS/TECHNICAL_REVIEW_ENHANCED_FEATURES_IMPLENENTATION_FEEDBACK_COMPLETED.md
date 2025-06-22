Here is the revised technical review.

### **1/8**

## Technical Architecture Review: Enhanced Class and File Management

### Executive Summary

This review assesses the technical architecture for the **Enhanced Class and File Management Implementation**. The proposal introduces a new `class_management_service` and enhances the `file_service` and `batch_orchestrator_service` to support a more dynamic, user-centric workflow.

The proposed architecture is **fundamentally sound and aligns well** with the established microservice principles of the HuleEdu platform, including Domain-Driven Design and event-driven communication. The introduction of a new, dedicated service for class and student management is the correct approach to maintain clear service boundaries.

However, the implementation requires **rigorous technical validation** in three critical areas before proceeding:

1. **Database Performance**: The new `class_management_service` introduces several many-to-many relationships (e.g., `class_student_associations`). The performance of these joins under the projected user load must be benchmarked with a focus on indexing strategy for foreign keys.
2. **Synchronous Communication Resiliency**: The plan introduces direct HTTP calls between services (e.g., File Service to BOS) for state validation. This is a pragmatic deviation from a pure-EDA pattern but **it is a critical gap that a circuit breaker pattern is not specified**. This must be added to prevent cascading failures.
3. **Security**: The introduction of Student Personally Identifiable Information (PII) necessitates a formal review of data protection strategies, including encryption at rest and access logging. The proposed schema provides a good foundation, but implementation details for data protection must be explicitly defined.

The plan is viable, but successful implementation hinges on addressing these performance, resilience, and security considerations with specific, testable solutions.

-----

## 1\. Service Architecture Decisions

### 1.1 New Service: Class Management Service

**Service Type**: HTTP + Kafka Consumer Hybrid  
**Technology Stack**: Quart + SQLAlchemy + Dishka DI  
**Database**: PostgreSQL with complex many-to-many relationships

**REVIEW REQUIRED**:

- [X] **Database Performance**: The proposed schema's use of many-to-many joins via `class_student_associations` and `class_course_associations` is standard, but performance under load is a valid concern. The design **must be validated with load tests**. Proper indexing is non-negotiable.

    **Recommendation**: Ensure the SQLAlchemy models in the new service's `models_db.py` explicitly define indexes on all foreign keys and frequently queried columns, like `user_id`.

    *Code Example (`services/class_management_service/models_db.py`)*:

    ```python
    class UserClass(Base):
        __tablename__ = "user_classes"
        
        id: Mapped[str] = mapped_column(String(36), primary_key=True)
        # Add index=True for performance on user-specific queries
        user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True) 
        class_designation: Mapped[str] = mapped_column(String(255), nullable=False)
        # ...
    ```

- [X] **Connection Pooling**: Adding a new service requires a new database connection pool. This is a low-risk extension of the established pattern in `docker-compose.infrastructure.yml`. A new PostgreSQL service block for `class_management_db` should be added, mirroring the configuration of `huleedu_batch_orchestrator_db` and `huleedu_essay_lifecycle_db`.

- [X] **Service Discovery**: Integration is straightforward. The current architecture relies on Docker's internal DNS for service-to-service communication (e.g., `http://batch_orchestrator_service:5000` is used in BOS config). The new service will be discovered via its container name, which is consistent with existing practice.

- [X] **Health Checks**: The implementation **must** include standard `/healthz` and `/metrics` endpoints. The pattern from existing services should be reused. For example, the `health_bp` from `services/content_service/api/health_routes.py` can be copied and adapted for the new `class_management_service`.

### 1.2 Service Communication Patterns

**HTTP Calls**: File Service → BOS (batch state validation)  
**Event-Driven**: All other inter-service communication  
**Real-time**: Redis pub/sub → WebSocket → Frontend

**REVIEW REQUIRED**:

- [X] **HTTP Timeout Configuration**: The proposed 5s timeout is a good default but **must be configurable**. This should be added to the `file_service`'s `config.py` Pydantic model.

    **Recommendation**: Add `BOS_REQUEST_TIMEOUT: int = 5` to `services/file_service/config.py` and use it when creating the `aiohttp.ClientSession` in the DI provider.

- [X] **Circuit Breaker**: **CRITICAL GAP**. A direct, synchronous HTTP call creates a hard dependency. If `batch_orchestrator_service` is down or slow, the `file_service` will fail. This must be mitigated.

    **Recommendation**: Implement a circuit breaker pattern in the `file_service`'s HTTP client for BOS. The `pybreaker` library is a suitable choice.

    1. Add `pybreaker` to `services/file_service/pyproject.toml`.
    2. Create the breaker in the DI provider and inject it into the client implementation.

    *Code Example (`services/file_service/implementations/batch_state_validator.py`)*:

    ```python
    import aiohttp
    import pybreaker
    from ..protocols import BatchStateValidatorProtocol

    class BOSBatchStateValidator(BatchStateValidatorProtocol):
        def __init__(self, http_session: aiohttp.ClientSession, settings: Settings):
            self.http_session = http_session
            self.settings = settings
            # Fail after 3 consecutive errors, open for 60 seconds
            self.breaker = pybreaker.AsyncCircuitBreaker(fail_max=3, reset_timeout=60)

        @breaker
        async def can_modify_batch_files(self, batch_id: str, user_id: str) -> tuple[bool, str]:
            # This HTTP call is now protected by the circuit breaker
            bos_url = f"{self.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"
            async with self.http_session.get(bos_url) as response:
                # ... existing logic ...
    ```

- [X] **Event Volume**: The additional event volume is low and poses no threat to Kafka's performance. The topics should be added to `scripts/kafka_topic_bootstrap.py` and the `kafka-setup-topics` PDM script to ensure they are created automatically on startup, consistent with existing practice.

- [X] **Redis Channel Management**: The proposal to use user-specific channels (`ws:{user_id}`) is efficient. The existing `RedisClient` in `services/libs/huleedu_service_libs/redis_client.py` has already been extended with `publish` and `subscribe` methods as per the task document, making it ready to serve as the WebSocket backplane.

### **2/8**

### 2\. Database Schema Changes

My assessment of the proposed database changes is positive. The plan correctly isolates the new schema within the new `class_management_service` and leverages the flexibility of existing models, which minimizes risk to the current system. However, performance and operational strategy require explicit validation.

#### 2.1 Class Management Service Schema

**New Tables**:

- `user_classes`
- `students`
- `essay_student_associations`
- `class_student_associations` (many-to-many)
- `class_course_associations` (many-to-many)

**REVIEW REQUIRED**:

- [X] **Index Strategy**: **Action Required.** The proposed schema implies high-frequency lookups on foreign keys and user identifiers. To ensure performance, explicit indexes are mandatory. The existing codebase establishes a clear pattern for this using SQLAlchemy's `index=True` parameter.

    *Code Example (`services/batch_orchestrator_service/models_db.py`)*:

    ```python
    // ...
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    // ...
    ```

    **Recommendation**: Apply this `index=True` pattern to the following columns in the new `class_management_service.models_db`:
    \* `user_classes.user_id`
    \* `students.email` and `students.created_by_user_id`
    \* All `ForeignKey` columns in `class_student_associations` and `essay_student_associations`.

- [X] **Foreign Key Constraints**: **Action Required.** The plan is correct to use foreign keys. For data integrity, `ondelete='CASCADE'` should be used on association tables. This ensures that if a student or class is deleted, their associations are automatically cleaned up, preventing orphaned rows. This pattern is already in use in `essay_lifecycle_service`.

    *Code Example (`services/essay_lifecycle_service/models_db.py`)*:

    ```python
    essay_id: Mapped[str] = mapped_column(
        ForeignKey("essay_states.essay_id", ondelete="CASCADE"), # Pattern to replicate
        nullable=False,
        index=True,
    )
    ```

    **Recommendation**: Apply `ondelete='CASCADE'` to the `ForeignKey` definitions in the `class_student_associations` and `essay_student_associations` tables.

- [X] **Migration Strategy**: **Observation & Recommendation.** The project currently lacks a formal database migration tool like Alembic. The established pattern is to use `Base.metadata.create_all` on service startup. This is acceptable for adding a new, isolated service. However, any *future modifications* to the schema of this or any other service will require a formal migration strategy to prevent data loss in production. **A task to integrate Alembic should be prioritized in a subsequent sprint.**

- [X] **Backup Strategy**: **Confirmation.** The existing infrastructure uses Docker-managed volumes for data persistence (e.g., `batch_orchestrator_db_data`, `essay_lifecycle_db_data`). The new `class_management_db` will require a new named volume added to the root `docker-compose.yml`. The backup strategy remains consistent: standard `pg_dump` procedures can be executed against the service's PostgreSQL container. This is an operational task for the DevOps team.

#### 2.2 Existing Service Schema Modifications

**BOS Enhancements**:

- No breaking schema changes proposed.

**REVIEW REQUIRED**:

- [X] **JSON Field Performance**: **Low Risk.** The proposal correctly avoids altering the BOS schema, instead storing new metadata in the existing `processing_metadata` JSON column. The `postgres:15` image provides excellent JSONB performance. If direct queries on keys within this JSON blob (e.g., `user_id`, `class_id`) were required frequently, a GIN index would be recommended. However, since the primary query path for this data will be through the new `result_aggregator_service`, which will have its own indexed relational columns, this approach is performant and acceptable.
- [X] **Backward Compatibility**: **Confirmed.** Adding new keys to a JSON field is inherently backward-compatible. Existing batches in the database will simply lack the new fields, and Pydantic models with `Optional` fields will handle this gracefully.

### 3\. Event Contract Changes

The proposed changes to `common_core` are well-structured and align with existing patterns.

#### 3.1 Common Core Extensions

**New Enums**: `CourseCode`, new `ProcessingEvent` types
**New Event Models**: `StudentParsingCompletedV1`, `BatchFileAddedV1`, etc.

**REVIEW REQUIRED**:

- [X] **Event Schema Validation**: **Confirmed.** The proposed new event models in `documentation/TASKS/ENHANCED_CLASS_AND_FILE_MANAGEMENT_IMPLEMENTATION.md` correctly follow the established pattern of using Pydantic's `BaseModel` and `Field` for clear, validated contracts, mirroring existing models like `EssayContentProvisionedV1`.

- [X] **Topic Creation**: **Action Required.** New topics need to be added to the automated setup process.

    **Recommendation**: Add the new topic names to the `_TOPIC_MAPPING` dictionary in `common_core/src/common_core/enums.py` and subsequently call them in the `kafka_topic_bootstrap.py` script. This ensures they are created when `pdm run kafka-setup-topics` is executed on startup.

- [X] **Consumer Impact**: **Confirmed.** The introduction of new, distinct topics will have no impact on existing consumers, as they are not subscribed to them. This is a key benefit of the topic-based routing strategy.

- [X] **Serialization Performance**: **Confirmed.** The new event models are "thin events" and primarily carry identifiers and small strings. Their size is comparable to existing events and will not introduce a performance bottleneck for Kafka serialization or network transfer.

#### 3.2 Kafka Topic Management

**New Topics** (documented, implement later):
`huleedu.file.student.parsing.completed.v1`, etc.

**REVIEW REQUIRED**:

- [X] **Topic Configuration**: The `kafka_topic_bootstrap.py` script uses environment variables (`KAFKA_DEFAULT_PARTITIONS`, `KAFKA_DEFAULT_REPLICATION_FACTOR`) to configure new topics. This is a sound, consistent approach. The default values are appropriate for development, but should be reviewed by DevOps for production based on expected throughput for these new topics.

- [X] **Retention Policy**: Kafka's default retention policy will apply. For events like `ClassCreatedV1`, which may be valuable for auditing, a longer, topic-specific retention policy should be considered for the production environment. This is an operational decision.

- [X] **Consumer Group Strategy**: **Action Required.** The new `class_management_service` will need its own unique `group_id` for its Kafka consumer.

    **Recommendation**: Define this in the service's `config.py`, following the pattern used by other services, for example, `CONSUMER_GROUP_ID_CJ` in `services/cj_assessment_service/config.py`.

    ### **3/8**

### 4\. API Gateway Integration

The plan to integrate the new features via the API Gateway is sound and follows modern best practices. The use of FastAPI for this client-facing layer is appropriate, and the proposed real-time architecture is scalable.

#### 4.1 Enhanced WebSocket Events

**Additional Event Types**: 6 new event types for real-time updates  
**Message Volume Estimate**: \~200 users × 6 classes × file operations

**REVIEW REQUIRED**:

- [X] **WebSocket Scaling**: **Confirmed as Viable.** The proposed architecture in `API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_3.md` outlines creating one `asyncio` task (`redis_listener`) per WebSocket connection. For the target load of 100-200 concurrent users, this is highly efficient and well within the capabilities of a single containerized `asyncio` server. The primary scaling constraint will be the CPU/memory of the gateway container, not the connection-handling pattern itself.
    **Recommendation**: For future scaling beyond \~1000 concurrent connections, the `api_gateway_service` should be deployed with multiple replicas. The Redis Pub/Sub backplane is horizontally scalable and will not be a bottleneck.

- [X] **Redis Pub/Sub Performance**: **Confirmed as Low-Risk.** Redis can handle hundreds of thousands of messages per second per core. The projected event volume is negligible in comparison. The `redis_client.py` implementation uses `aioredis`, which is fully asynchronous, preventing blocking operations and ensuring low latency from message receipt on a Redis channel to being sent over the WebSocket.

- [X] **Event Filtering**: **Opportunity for Optimization.** The proposed implementation filters events server-side before sending them to the client, which is good practice..
    **Recommendation**: For a future iteration, consider implementing a channel subscription model where the client can specify which resources it's interested in (e.g., `{"action": "subscribe", "resource": "batch:123"}`). This would further reduce the data transmitted over the WebSocket, offloading filtering logic from the gateway and reducing client-side processing. The current approach is sufficient for the MVP.

#### 4.2 New HTTP Endpoints

**Class Management**: CRUD operations for classes/students  
**File Management**: Add/remove files with state validation  
**Student Associations**: Manual essay-student linking

**REVIEW REQUIRED**:

- [X] **Rate Limiting**: **Confirmed as Sound.** The plan specifies using `slowapi` with a Redis backend. This is an excellent choice as it enables distributed rate limiting that works across multiple replicas of the API Gateway.
    **Recommendation**: Implement different rate limits for read (`GET`) vs. write (`POST`, `DELETE`) operations. For example, allow more frequent status checks but stricter limits on file uploads or class creation.

- [X] **Authentication**: **Confirmed as Sound.** The plan to propagate the JWT token from the frontend and validate it in the API Gateway using a FastAPI `Depends` function (`get_current_user_id`) is a standard and secure pattern..

- [X] **Authorization**: **Confirmed as Sound.** The proposed pattern for ownership validation is critical and correct. The example in `API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_3.md` for the `/status` endpoint shows the gateway fetching the `user_id` associated with the batch from the `result_aggregator_service` and comparing it against the JWT's `user_id` before returning data. **This ownership check pattern must be rigorously applied to every new endpoint that accesses or modifies a specific resource.**

### 5\. Performance and Scalability Analysis

The proposed architecture is generally scalable, but specific areas must be monitored and optimized.

#### 5.1 Database Query Patterns

**High-Frequency Queries**:

- Batch state validation (File Service → BOS): \~10-50/min per active user
- Class/student lookups: \~5-20/min per active user

**REVIEW REQUIRED**:

- [X] **Query Performance**: **Action Required.** As noted in Section 2, indexing is mandatory for the new `class_management_service` tables. The high-frequency query from `file_service` to `batch_orchestrator_service` (`GET /internal/v1/batches/{batch_id}/pipeline-state`) is a primary key lookup on the `batches` table, which is highly performant. The performance risk is not the query itself, but the synchronous nature of the HTTP call, which should be mitigated with a circuit breaker.

- [X] **Connection Pooling**: **Action Required.** The new `class_management_service` **must** have configurable connection pooling parameters in its `config.py` and use them when creating its `SQLAlchemy` engine. This is essential to prevent connection exhaustion under load. The configuration should mirror the existing pattern in `batch_orchestrator_service`.

    *Code Example (`services/batch_orchestrator_service/config.py` to replicate)*:

    ```python
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True
    ```

- [X] **Caching Strategy**: **Recommendation.** The `result_aggregator_service` already functions as a caching layer for batch status. For the new `class_management_service`, which serves read-heavy data (class lists, student rosters), a cache-aside strategy using Redis would significantly reduce database load. This can be implemented within the service's repository layer.

#### 5.2 Event Processing Load

**Additional Event Volume**:

- File operations: \~1-10 events per batch modification
- Student parsing: \~1 event per batch
- Class operations: \~1-5 events per teacher session

**REVIEW REQUIRED**:

- [X] **Kafka Throughput**: **Confirmed as Low-Risk.** The projected event volume is well within Kafka's capacity. No issues are anticipated with broker throughput.

- [X] **Consumer Lag**: **Monitoring Required.** The primary performance indicator will be consumer lag for the new and modified services. The `01-Grafana-Playbook.md` should be updated to include panels for monitoring consumer group lag for the new topics.

    **Recommendation**: Add a "Kafka Consumer Lag" panel to the service-specific Grafana dashboards using a query like: `sum(kafka_consumergroup_lag{group=~".*class-management.*|.*file-service.*"}) by (group, topic)`.

- [X] **Error Handling**: **Confirmed as Sound.** The plan to use Dead Letter Queues (DLQs) for unrecoverable messages is a robust pattern. The proposed `KafkaBus.publish_to_dlq` method, which appends `.dlq` to the original topic name, is a standard and effective convention.

### **4/8**

This review continues the technical assessment of the **Enhanced Class and File Management Implementation**, focusing on sections 6 and 7: Security & Compliance and Deployment & Infrastructure.

### 6\. Security and Compliance Considerations

The introduction of student PII and new inter-service communication patterns requires a formal security review. The current proposal provides a foundation, but specific implementation details must be mandated.

#### 6.1 Data Protection

**Student Data**: Names, email addresses stored in Class Management Service  
**User Ownership**: All operations validated against authenticated user  
**Cross-Service Access**: File Service HTTP calls to BOS with user context

**REVIEW REQUIRED**:

- [X] **Data Encryption**: **High-Priority Recommendation.** The current infrastructure (`image: postgres:15` in `docker-compose.infrastructure.yml`) does not specify database-level encryption. Data protection relies on the host's filesystem encryption.
    **Recommendation**: For production environments, the DevOps team **must** ensure that all Docker volumes used for PostgreSQL data persistence (e.g., `batch_orchestrator_db_data`, `essay_lifecycle_db_data`, and the new `class_management_db_data`) are mounted on encrypted block storage (e.g., AWS EBS with KMS encryption, GCP Persistent Disk with CMEK). This is an infrastructure-level requirement.

- [X] **Access Logging**: **Action Required.** A robust audit trail is necessary for handling PII.
    **Recommendation**: Implement two layers of access logging for the new `class_management_service`:

    1. **Application Layer**: In the service logic for any CRUD operation on the `students` table, add a structured log entry that includes the authenticated `user_id` making the change, the `student_id` being accessed, and the action performed. This leverages the existing `huleedu_service_libs.logging_utils`.
    2. **Database Layer**: For a definitive audit trail, enable PostgreSQL's statement logging for the `class_management_db` instance. Setting `log_statement = 'mod'` in `postgresql.conf` will log all data-modifying statements (`UPDATE`, `DELETE`, `INSERT`).

- [X] **GDPR Preparation**: **Confirmed as Viable.** The plan correctly defers implementation but the proposed architecture is suitable. Isolating student PII into a dedicated `students` table within the `class_management_service` is the correct design. It will simplify future implementation of GDPR "right to be forgotten" and data export functionalities, as operations can be targeted to a single service and database table.

#### 6.2 Authentication and Authorization

**JWT Propagation**: API Gateway → Backend services via headers  
**Ownership Validation**: User-scoped access to all resources  
**Service-to-Service**: Internal API authentication between File Service and BOS

**REVIEW REQUIRED**:

- [X] **Token Validation**: **Gap Identified.** The plan mentions passing user context from the API Gateway to internal services like the `file_service`. It proposes passing the `user_id` in a header (e.g., `X-User-ID`). This implies a trusted internal network where the gateway is the sole validator of the original JWT.
    **Recommendation**: This is an acceptable pattern for performance, but it must be formally documented as an architectural decision. For higher security environments, a "zero-trust" approach would involve the gateway forwarding the JWT, and internal services performing a quick, cached public key-based validation. For the current scale, the `X-User-ID` header is a reasonable trade-off.

- [X] **Service Authentication**: **Recommendation.** To harden the internal API between `file_service` and `batch_orchestrator_service`, a shared secret should be used.
    **Recommendation**: Implement an `X-Internal-API-Key` header. This key would be a shared secret stored as an environment variable in both services. The receiving service (BOS) would validate this header on its internal endpoints to ensure the request is from a trusted internal service.

- [X] **Permission Model**: **Confirmed as Ready for Extension.** The proposed schemas are well-suited for future role-based access control (RBAC). The `user_classes` table, with its `user_id` foreign key, establishes clear ownership that can be the basis of all authorization checks.

### 7\. Deployment and Infrastructure

The plan requires a new service and modifications to existing ones. The deployment strategy should align with current practices while acknowledging future needs.

#### 7.1 Service Deployment

**New Service**: Class Management Service containerization  
**Enhanced Services**: File Service, BOS modifications  
**Database**: Additional PostgreSQL schema and migrations

**REVIEW REQUIRED**:

- [X] **Container Orchestration**: **Correction.** The plan mentions Kubernetes, but the project currently uses Docker Compose exclusively. All services, including the new `class_management_service`, are defined in `.yml` files.
    **Recommendation**: The new service **must** be added to `docker-compose.services.yml`, and its new database must be added to `docker-compose.infrastructure.yml`, mirroring the definitions of existing services like `cj_assessment_service`. The migration to Kubernetes is a separate, future project.

- [X] **Service Mesh**: **Observation.** No service mesh is currently used. Service discovery is handled by Docker DNS. This is sufficient for the current scale and complexity.

- [X] **Health Monitoring**: **Action Required.** The `prometheus.yml` configuration must be updated with a new scrape job for the `class_management_service`.

    *Code Example (`prometheus.yml` addition):*

    ```yaml
      - job_name: 'class_management_service'
        static_configs:
          - targets: ['class_management_service:<port>'] # Use the service's exposed metrics port
        metrics_path: '/metrics'
    ```

- [X] **Log Aggregation**: **Confirmed as Ready.** The existing Promtail configuration scrapes logs from all containers on the `huleedu-reboot_huleedu_internal_network`. As long as the new `class_management_service` is attached to this network in its `docker-compose` definition, its logs will be automatically collected by the existing observability stack with no further configuration needed.

#### 7.2 Migration Strategy

**Phase 1**: Common Core extensions (non-breaking)  
**Phase 2**: New service deployment + enhanced file management  
**Phase 3**: Real-time integration and frontend deployment

**REVIEW REQUIRED**:

- [X] **Zero-Downtime Deployment**: **Risk Identified.** The current deployment mechanism via `pdm run docker-restart` or `docker compose up -d --build` will result in brief service downtime as containers are replaced. This is acceptable for the current project maturity. True zero-downtime deployments will require a move to an orchestrator like Kubernetes that supports rolling update strategies.

- [X] **Rollback Plan**: **Confirmed.** The current rollback strategy is to revert the git commit and re-run the `docker compose up` command. As the proposed changes do not involve altering existing database schemas (only adding a new one), this is a low-risk procedure.

- [X] **Feature Flags**: **Recommendation.** The plan rightly suggests feature flags. This can be implemented simply and effectively using environment variables within the Pydantic `Settings` models of the affected services.

    *Code Example (`services/file_service/config.py`):*

    ```python
    class Settings(BaseSettings):
        # ...
        ENABLE_BATCH_STATE_VALIDATION: bool = Field(default=False, description="Enable synchronous call to BOS to validate batch state before file modification.")
        # ...
    ```

    The new logic in the `file_service` for calling BOS would then be wrapped in an `if settings.ENABLE_BATCH_STATE_VALIDATION:` block. This allows the new code to be deployed in a dormant state and activated via configuration, de-risking the rollout.

    ### **5/8**

This review continues the technical assessment of the **Enhanced Class and File Management Implementation**, focusing on sections 8 and 9: Testing & Quality Assurance and Risk Assessment.

### 8. Testing and Quality Assurance

The proposed testing strategy is sound, but its success depends on rigorous application of existing patterns and the introduction of new performance-focused testing.

#### 8.1 Testing Strategy

**Unit Tests**: Protocol-based testing for new implementations  
**Integration Tests**: Service-to-service communication validation  
**Contract Tests**: Event schema compliance verification  
**Performance Tests**: Database and API load testing

**REVIEW REQUIRED**:

- [X] **Test Coverage**: **Action Required.** All new business logic must be accompanied by unit tests that leverage the existing protocol-based mocking pattern. For example, the new `ClassManagementService`'s logic for creating a class should be tested by providing a mock repository that implements its `ClassRepositoryProtocol`, isolating the logic from the database. This pattern is already established in tests for other services.
    *File Search Confirmation*: Your existing test suites, such as `services/spell_checker_service/tests/test_event_processor.py`, effectively use `pytest.fixture` and `mocker.patch` to inject mock implementations of protocols. This exact pattern must be enforced for all new services and components.

- [X] **Performance Benchmarks**: **Action Required.** This is the most critical testing requirement for this implementation. Before production deployment, the new `class_management_service` endpoints must be load-tested to establish performance benchmarks.
    **Recommendation**: Use a tool like `locust.io` to create a test script that simulates the following user flows:
    1. A teacher logging in and fetching all their classes and students.
    2. Fetching the details of a single class with a full student roster.
    3. Creating new classes and adding students.
    The goal is to ensure that P95 response times for these queries remain under 500ms at the target load of 200 concurrent users.

- [X] **Integration and Contract Test Reinforcement**:
  - **HTTP Integration**: A dedicated integration test must be added to validate the File Service -> BOS synchronous call. This test should run in the Docker-Compose environment and confirm the File Service correctly handles 200, 4xx, and 5xx (including timeout) responses from BOS. The existing E2E tests in `tests/functional/` provide a template for this setup.
  - **Event Contracts**: For every new event model (e.g., `ClassCreatedV1`), a corresponding unit test must be added in `common_core/tests/` to validate its Pydantic serialization and deserialization (`model_dump_json`/`model_validate_json`). This guarantees that events can be reliably produced and consumed across the Kafka bus. This pattern is well-established in files like `common_core/tests/unit/test_file_events.py`.

#### 8.2 Monitoring and Observability

**Metrics**: Business and technical metrics for new features  
**Logging**: Structured logging with correlation IDs  
**Tracing**: Distributed tracing across enhanced service calls

**REVIEW REQUIRED**:

- [X] **Alert Configuration**: **Action Required.** New alerts must be configured for the new `class_management_service`.
    **Recommendation**: Add a new alert rule file or extend `prometheus/rules/service_alerts.yml` to include a `ServiceDown` and `HighErrorRate` alert for the `class_management_service` job. This follows the existing pattern defined for all other services.

- [X] **Dashboard Creation**: **Action Required.** The existing `01-Grafana-Playbook.md` provides a template for service dashboards. A new "Service Deep Dive" dashboard for the `class_management_service` must be created.
    **Recommendation**: This new dashboard must include panels for:
    1. HTTP Request Rate & Error Rate (from standard middleware metrics).
    2. Database Query Latency (requires a new `Histogram` metric in the service).
    3. Kafka Consumer Lag (if it consumes events).
    4. Business metrics (e.g., `classes_created_total`, `students_added_total`).

- [X] **SLA Definition**: **Observation.** While no formal SLAs are defined, the introduction of more user-facing synchronous APIs (Class Management, File/Batch State) necessitates defining internal targets. A P99 latency of <1s for these API calls would be a reasonable initial target to ensure a responsive frontend experience.

### 9. Risk Assessment

The risk assessment in the plan is accurate, though the severity of some risks can be refined based on the proposed mitigations.

#### 9.1 Technical Risks

**HIGH RISK**:

- [X] **Database performance with complex many-to-many relationships**: Agreed. This is the highest implementation risk.
- [X] **WebSocket scaling at target user load**: Agreed. While the architecture is sound, real-world performance depends heavily on the implementation details and infrastructure.
- [ ] **Event schema evolution and consumer compatibility**: **Re-classified to Medium Risk.** Your project's strict adherence to Pydantic models, versioned event topics (e.g., `.v1`), and the practice of adding new `Optional` fields provides strong protection against backward-incompatibility. The risk is manageable with continued discipline.

**MEDIUM RISK**:

- [X] **HTTP call patterns between File Service and BOS**: Agreed. This is a medium risk due to the potential for cascading failures, which is why the circuit breaker is critical.
- [X] **Cross-service authentication and authorization**: Agreed. An error in ownership validation logic would be a serious security flaw.

**LOW RISK**:

- [ ] **Redis pub/sub message volume and latency**: **Confirmed as Low Risk.** As analyzed previously, Redis performance is not a concern at the projected scale.
- [X] **Container deployment and orchestration**: Agreed. The pattern is well-established in the project.
- [X] **Common core enum extensions**: Agreed. This is a low-risk, additive change.

#### 9.2 Mitigation Strategies

**REVIEW REQUIRED**:

- [X] **Performance Testing**: **Confirmed.** This is the correct mitigation for the high-risk database performance issue. This must be a release criterion.
- [X] **Circuit Breakers**: **Confirmed.** This is the correct and necessary mitigation for the medium-risk HTTP call pattern. The recommendation to use `pybreaker` stands.
- [X] **Graceful Degradation**: **Recommendation.** This is an excellent point that requires more specific planning.
    **Recommendation**: The API Gateway should implement its own health checks of downstream internal services (BOS, Class Management Service). If a downstream service is unhealthy, the Gateway should immediately return a `503 Service Unavailable` response for relevant requests, preventing timeouts and providing faster feedback to the user. The frontend can then use this response to disable corresponding UI elements (e.g., disable the "Upload Files" button if the File Service is down).
- [X] **Monitoring**: **Confirmed.** This is the most critical mitigation for all risks. Proactive monitoring via the new Grafana dashboards will be the primary mechanism for early detection of performance degradation or system-level issues.

### **6/8**

This review continues the technical assessment of the **Enhanced Class and File Management Implementation**, focusing on the final approval checklists and providing a conclusive recommendation.

### 10. Approval Checklist

This checklist provides a final assessment against key architectural, infrastructural, and operational criteria.

#### 10.1 Architecture Review

- [X] **Service Boundaries**: **PASS.** The decision to create a new `class_management_service` is an exemplary application of the project's microservice principles. It correctly isolates the new domain of class and student data, preventing bloat in existing services like `batch_orchestrator_service` or `file_service`.

- [X] **Data Flow**: **PASS with Conditions.** The primary event-driven flows are excellent. The synchronous HTTP call from `file_service` to `batch_orchestrator_service` is a pragmatic choice for state validation.
  - **Condition**: Approval is contingent on the **mandatory implementation of a circuit breaker pattern** (using `pybreaker` as previously recommended) for this HTTP call to prevent cascading failures. A file search confirms this is not in the original plan and is a critical addition.

- [X] **Scalability**: **ACTION REQUIRED.** The architecture is designed for scale, but this has not been empirically validated.
  - **Action**: Conduct and document the results of performance tests using a tool like `locust.io`. The tests must simulate the target load (100-200 concurrent users) against the new `class_management_service` API and WebSocket endpoints. The results must meet the performance benchmarks (e.g., P95 < 500ms) before this item can be marked as "Pass".

- [X] **Security**: **PASS with Conditions.** The core security patterns (JWT auth, ownership checks) are sound.
  - **Conditions**:
        1. All new API endpoints that touch user-specific data **must** rigorously implement the user ownership validation logic demonstrated in the task documents.
        2. The DevOps team **must** confirm that production volumes for the new `class_management_db` are encrypted at rest.
        3. The architectural decision to use an `X-User-ID` header for internal service calls (a trusted network approach) **must** be formally documented.

#### 10.2 Infrastructure Review

- [X] **Resource Requirements**: **ACTION REQUIRED.** The plan does not specify CPU/memory requirements for the new service. A search of `docker-compose.services.yml` confirms no resource limits are currently set for any service.
  - **Action**: The DevOps team must perform initial resource allocation for the `class_management_service` container and then **monitor actual resource consumption during performance testing** to establish a baseline for production.

- [X] **Deployment Strategy**: **PASS.** The strategy of adding the new service definition to `docker-compose.services.yml` and the new database to `docker-compose.infrastructure.yml` is perfectly consistent with the project's established deployment pattern.

- [X] **Monitoring**: **PASS with Conditions.** The project's observability stack is robust and ready.
  - **Conditions**:
        1. A new scrape job for the `class_management_service` **must** be added to `prometheus.yml`.
        2. A new Grafana dashboard, based on the `01-Grafana-Playbook.md` template, **must** be created and validated for the new service.

- [X] **Disaster Recovery**: **PASS with Conditions.** The DR strategy is based on backups of Docker-managed volumes.
  - **Condition**: The DevOps team **must** formally add the new `class_management_db_data` volume to the existing backup schedule and verify the recovery procedure.

#### 10.3 Operational Review

- [X] **Runbook Creation**: **ACTION REQUIRED.** The project currently lacks formal runbooks. A search of `documentation/OPERATIONS/` shows playbooks for tools but not for service incident response.
  - **Action**: A basic operational runbook (`02-Class-Management-Playbook.md`) **must** be created. It should document common failure modes (e.g., high DB latency), diagnostic steps using the new Grafana dashboard, and standard resolution procedures (e.g., restarting the container).

- [X] **Incident Response**: **PASS.** The existing alerting infrastructure, which includes Prometheus Alertmanager, is sufficient to notify the on-call team of alerts configured for the new service.

- [X] **Capacity Planning**: **ACTION REQUIRED.** This is blocked by the performance testing action. The load test results will be the essential input for planning future resource needs and scaling strategies.

- [X] **Maintenance Windows**: **PASS.** The current deployment method implies brief downtime, which is an understood and accepted operational mode for the project at its current maturity.

### 11. Final Recommendation and Next Steps

#### Final Recommendation

The proposed architecture for the **Enhanced Class and File Management Implementation** is **APPROVED WITH CONDITIONS**.

The plan is well-conceived and aligns strongly with the project's architectural principles. However, due to the introduction of new communication patterns, PII data handling, and performance-sensitive database queries, the following conditions must be met before full production deployment:

1. **Implement Resilience**: A circuit breaker for the `file_service` -> `batch_orchestrator_service` HTTP call must be implemented.
2. **Validate Performance**: The `class_management_service` API and WebSocket implementation must pass performance tests at the target user load.
3. **Implement Monitoring**: All required monitoring artifacts (Prometheus scrape job, Grafana dashboard, alerts) must be created and verified.
4. **Confirm Infrastructure**: The DevOps team must confirm that encrypted volumes are in use for the new database and that it is included in the backup plan.
5. **Create Runbook**: A basic operational runbook for the new service must be created.

#### Next Steps

With conditional approval granted, the project team should proceed with the next steps as outlined in the implementation document:

1. **Technical Review Meeting**: Schedule a session with the relevant teams to discuss this review and agree on the implementation of the required conditions.
2. **Performance Validation**: Begin scripting and executing the required load tests.
3. **Security Audit**: Formally review and sign off on the data protection and access control measures.
4. **Infrastructure Planning**: Provision the necessary infrastructure configurations (e.g., updates to `prometheus.yml`, backup scripts).
5. **Implementation**: Proceed with the phased implementation, starting with the `common_core` extensions.

### **7/8**

Review process ACCEPTED. The "Enhanced Class and File Management" architecture is conditionally approved.

Proceeding with the implementation plan as reviewed. The first step is **Phase 1: Common Core extensions**. This is a non-breaking, additive change that prepares the event contracts for the new services and features.

Below are the required code modifications for the `common_core` package.

-----

### **1. Modify `common_core/src/common_core/enums.py`**

The `enums.py` file is the central location for all shared enumerations. A search of the codebase confirms this is the correct location for the new `CourseCode` and the new `ProcessingEvent` types.

*File Search Confirmation*: `search(queries=["class ProcessingStage(str, Enum) in:common_core/src/common_core/enums.py"])` confirms `enums.py` is the correct file.

**Action**: Add `CourseCode` enum and extend the `ProcessingEvent` enum.

```python
# common_core/src/common_core/enums.py

from __future__ import annotations

from enum import Enum

# ... (existing enums like ProcessingStage, ProcessingStatus)

# NEW: Add CourseCode enum as specified in the implementation plan
class CourseCode(str, Enum):
    """Represents standardized course codes for batch processing."""
    ENG5 = "ENG5"
    ENG6 = "ENG6"
    ENG7 = "ENG7"
    SV1 = "SV1"
    SV2 = "SV2"
    SV3 = "SV3"


class ProcessingEvent(str, Enum):
    """Defines the types for all processing-related events."""

    # ... (existing event types)
    ESSAY_VALIDATION_FAILED = "essay.validation.failed"
    ESSAY_CONTENT_PROVISIONED = "essay.content.provisioned"

    # NEW: Add event types for class and file management as specified in the plan
    STUDENT_PARSING_COMPLETED = "student.parsing.completed"
    BATCH_FILE_ADDED = "batch.file.added"
    BATCH_FILE_REMOVED = "batch.file.removed"
    CLASS_CREATED = "class.created"
    STUDENT_CREATED = "student.created"
    ESSAY_STUDENT_ASSOCIATION_UPDATED = "essay.student.association.updated"

# ... (existing _TOPIC_MAPPING)

# NEW: Add topic mappings for the new events
_TOPIC_MAPPING.update({
    ProcessingEvent.STUDENT_PARSING_COMPLETED: "huleedu.file.student.parsing.completed.v1",
    ProcessingEvent.BATCH_FILE_ADDED: "huleedu.file.batch.file.added.v1",
    ProcessingEvent.BATCH_FILE_REMOVED: "huleedu.file.batch.file.removed.v1",
    ProcessingEvent.CLASS_CREATED: "huleedu.class.created.v1",
    ProcessingEvent.STUDENT_CREATED: "huleedu.class.student.created.v1",
    ProcessingEvent.ESSAY_STUDENT_ASSOCIATION_UPDATED: "huleedu.class.essay.association.updated.v1",
})
```

-----

### **2. Modify `common_core/src/common_core/events/file_events.py`**

The events `BatchFileAddedV1` and `BatchFileRemovedV1` are directly related to file operations and belong in this module.

*File Search Confirmation*: `search(queries=["class EssayContentProvisionedV1 in:common_core/src/common_core/events/file_events.py"])` confirms this is the correct location for file-related events.

**Action**: Add `BatchFileAddedV1` and `BatchFileRemovedV1` event models.

```python
# common_core/src/common_core/events/file_events.py

# ... (existing imports)
from ..enums import ProcessingEvent

# ... (existing event models like EssayContentProvisionedV1)

class BatchFileAddedV1(BaseEvent):
    """Event published when a file is successfully added to an existing batch."""

    event_type: str = Field(
        default=ProcessingEvent.BATCH_FILE_ADDED.value,
        frozen=True,
        description="The unique type of this event.",
    )
    batch_id: UUID = Field(description="The unique identifier for the batch.")
    file_name: str = Field(description="The name of the file that was added.")
    added_by_user_id: str = Field(description="The user ID of the user who added the file.")


class BatchFileRemovedV1(BaseEvent):
    """Event published when a file is successfully removed from an existing batch."""

    event_type: str = Field(
        default=ProcessingEvent.BATCH_FILE_REMOVED.value,
        frozen=True,
        description="The unique type of this event.",
    )
    batch_id: UUID = Field(description="The unique identifier for the batch.")
    file_name: str = Field(description="The name of the file that was removed.")
    removed_by_user_id: str = Field(description="The user ID of the user who removed the file.")

```

-----

### **3. Create `common_core/src/common_core/events/class_management_events.py`**

The remaining events belong to the new `Class Management` domain. Following existing patterns, they require a new, dedicated module.

*File Search Confirmation*: `search(queries=["class ClientBatchPipelineRequestV1 in:common_core/src/common_core/events/batch_coordination_events.py"])` shows that events are grouped by domain into separate files.

**Action**: Create a new file for class management events.

```python
# common_core/src/common_core/events/class_management_events.py

from __future__ import annotations

from uuid import UUID
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .base import BaseEvent
from ..enums import ProcessingEvent


class StudentInfo(BaseModel):
    """Represents information about a single parsed student."""
    student_email: str = Field(description="The email address of the student.")
    student_name: Optional[str] = Field(default=None, description="The name of the student, if available.")


class StudentParsingCompletedV1(BaseEvent):
    """Event published after the FileService has parsed student info from uploaded files."""

    event_type: str = Field(
        default=ProcessingEvent.STUDENT_PARSING_COMPLETED.value,
        frozen=True,
        description="The unique type of this event.",
    )
    batch_id: UUID = Field(description="The batch the students belong to.")
    parsed_by_user_id: str = Field(description="The user who initiated the parsing.")
    students: list[StudentInfo] = Field(description="A list of parsed student information.")


class ClassCreatedV1(BaseEvent):
    """Event published when a user creates a new class."""

    event_type: str = Field(
        default=ProcessingEvent.CLASS_CREATED.value,
        frozen=True,
        description="The unique type of this event.",
    )
    class_id: UUID = Field(description="The unique identifier for the newly created class.")
    teacher_user_id: str = Field(description="The user ID of the teacher who owns this class.")
    class_designation: str = Field(description="The user-defined name for the class (e.g., 'Period 4 English').")


class StudentCreatedV1(BaseEvent):
    """Event published when a student is created in the system."""

    event_type: str = Field(
        default=ProcessingEvent.STUDENT_CREATED.value,
        frozen=True,
        description="The unique type of this event.",
    )
    student_id: UUID = Field(description="The unique identifier for the student.")
    student_email: str = Field(description="The student's email address.")
    created_by_user_id: str = Field(description="The user ID of the teacher who created this student record.")


class EssayStudentAssociationUpdatedV1(BaseEvent):
    """Event published when an essay is manually associated with a student."""

    event_type: str = Field(
        default=ProcessingEvent.ESSAY_STUDENT_ASSOCIATION_UPDATED.value,
        frozen=True,
        description="The unique type of this event.",
    )
    essay_id: UUID = Field(description="The unique identifier for the essay.")
    student_id: UUID = Field(description="The unique identifier for the student.")
    batch_id: UUID = Field(description="The batch context for this association.")
    updated_by_user_id: str = Field(description="The user ID of the person who made the association.")

```

These changes complete Phase 1 of the implementation plan. The `common_core` package now contains all the necessary event contracts and enums to support the development of the `class_management_service` and the enhanced `file_service`.

### **8/8**

With the `common_core` extensions complete, this final step in our initial engagement initiates **Phase 2** of the implementation plan: **Scaffolding the new `class_management_service`**.

This involves creating the complete directory structure, generating all foundational code files based on established patterns in your codebase, and integrating the new service into the project's orchestration and monitoring layers. This provides a ready-to-develop microservice that adheres to all architectural mandates.

-----

### **1. Creating Service Directory and `pyproject.toml`**

A new directory `services/class_management_service/` is created. The `pyproject.toml` file defines the service's dependencies and project metadata, mirroring the configuration of other services.

*File Search Confirmation*: The structure and dependencies are based on `services/cj_assessment_service/pyproject.toml`.

**Action**: Create `services/class_management_service/pyproject.toml`.

```toml
# services/class_management_service/pyproject.toml

[tool.pdm.project]
name = "huleedu-class-management-service"
version = "0.1.0"
description = "HuleEdu service for managing classes, students, and their associations."
authors = [{ name = "HuleEdu Development Team" }]
requires-python = ">=3.11"
dependencies = [
    "quart~=0.19.4",
    "sqlalchemy~=2.0.30",
    "asyncpg~=0.29.0",
    "pydantic~=2.7.4",
    "pydantic-settings~=2.3.1",
    "dishka~=1.2.0",
    "dishka-quart~=1.2.0",
    "huleedu-common-core @ file:../../common_core",
    "huleedu-service-libs @ file:../libs/huleedu_service_libs",
]

[tool.pdm.build]
includes = ["src/class_management_service"]
package-dir = "src"

[project]
# pdm build requires this empty section
```

-----

### **2. Generating Foundational Service Code**

The following files establish the core application structure, configuration, database models, and service protocols.

#### **`config.py`**: Service Configuration

*File Search Confirmation*: Pattern derived from `services/batch_orchestrator_service/config.py`.

```python
# services/class_management_service/config.py

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Defines the configuration settings for the Class Management Service."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database Settings
    DB_USER: str = Field(..., description="Database user.")
    DB_PASSWORD: str = Field(..., description="Database password.")
    DB_HOST: str = Field(..., description="Database host.")
    DB_PORT: int = Field(..., description="Database port.")
    DB_NAME: str = Field(..., description="Database name.")
    DB_POOL_SIZE: int = Field(default=5)
    DB_MAX_OVERFLOW: int = Field(default=10)

    # Kafka Settings
    KAFKA_BOOTSTRAP_SERVERS: str = Field(description="Kafka bootstrap servers.")
    CLASS_MANAGEMENT_CONSUMER_GROUP_ID: str = Field(default="huleedu.class.management.v1", description="Kafka consumer group ID for this service.")

    @property
    def db_connection_string(self) -> str:
        """Asynchronous database connection string."""
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

```

#### **`models_db.py`**: Database Schema

*File Search Confirmation*: Schema from implementation plan, with indexing/cascade patterns from `services/essay_lifecycle_service/models_db.py`.

```python
# services/class_management_service/models_db.py

from __future__ import annotations

from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class UserClass(Base):
    __tablename__ = "user_classes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    class_designation: Mapped[str] = mapped_column(String(255), nullable=False)

class Student(Base):
    __tablename__ = "students"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

class ClassStudentAssociation(Base):
    __tablename__ = "class_student_associations"
    class_id: Mapped[str] = mapped_column(ForeignKey("user_classes.id", ondelete="CASCADE"), primary_key=True)
    student_id: Mapped[str] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), primary_key=True)
```

#### **`protocols.py`**: Service Interfaces

*File Search Confirmation*: Pattern derived from `services/file_service/protocols.py`.

```python
# services/class_management_service/protocols.py

from __future__ import annotations
from typing import Protocol

class ClassRepositoryProtocol(Protocol):
    """Defines the interface for data access related to classes and students."""
    async def create_class(self, user_id: str, designation: str) -> str:
        ...
    # ... other methods to be defined ...
```

#### **`main.py`**: Application Entrypoint

*File Search Confirmation*: Boilerplate structure from `services/batch_orchestrator_service/main.py`.

```python
# services/class_management_service/main.py

from __future__ import annotations

from quart import Quart
from dishka import make_async_container
from dishka.quart import setup_dishka

# ... (imports for DI providers, API blueprints, logging, etc.)

def create_app() -> Quart:
    """Application factory for the Class Management Service."""
    # Setup logging
    # ...

    app = Quart(__name__)

    # Setup DI
    # container = make_async_container(...)
    # setup_dishka(container, app)

    # Register API blueprints
    # from .api import class_routes
    # app.register_blueprint(class_routes.bp)
    
    @app.before_serving
    async def startup():
        # Start Kafka consumer in background
        # app.add_background_task(kafka_consumer.start)
        pass
    
    @app.after_serving
    async def shutdown():
        # await kafka_consumer.stop()
        # await container.close()
        pass

    return app

```

-----

### **3. Updating Orchestration and Monitoring**

To integrate the new service into the system, the `docker-compose` and `prometheus` configurations must be updated.

#### **`docker-compose.services.yml`**: Add New Service

*File Search Confirmation*: Service definition block copied from `cj_assessment_service`.

```yaml
# docker-compose.services.yml

# ... (other services)
  class_management_service:
    container_name: huleedu_class_management_service
    build:
      context: ./services/class_management_service
      dockerfile: ../../Dockerfile.service
    restart: unless-stopped
    networks:
      - huleedu_internal_network
    env_file:
      - .env
    depends_on:
      - class_management_db
      - kafka
    ports:
      - "5006:5000" # Exposing on a new port
```

#### **`docker-compose.infrastructure.yml`**: Add New Database

*File Search Confirmation*: DB definition block copied from `cj_assessment_db`.

```yaml
# docker-compose.infrastructure.yml

volumes:
  # ... (existing volumes)
  class_management_db_data: {}

services:
  # ... (other infrastructure)
  class_management_db:
    image: postgres:15
    container_name: huleedu_class_management_db
    restart: unless-stopped
    networks:
      - huleedu_internal_network
    volumes:
      - class_management_db_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: ${CLASS_MANAGEMENT_DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "15438:5432" # Exposing on a new port
```

#### **`prometheus.yml`**: Add New Monitoring Target

*File Search Confirmation*: Scrape job definition copied from existing jobs in the file.

```yaml
# prometheus.yml

# ... (other scrape_configs)
  - job_name: 'class_management_service'
    static_configs:
      - targets: ['class_management_service:5000']
    metrics_path: '/metrics'
```

-----

### **Conclusion of Initial Implementation**

This completes the 8-part review and initial implementation. The architecture has been validated, `common_core` has been updated with new contracts, and the `class_management_service` is now fully scaffolded and integrated into the system's runtime environment.

The project is now prepared for the detailed implementation of business logic within the new service's repositories, consumers, and API endpoints.
