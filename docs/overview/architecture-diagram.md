# HuleEdu System Architecture Diagrams

This document provides visual representations of the HuleEdu platform architecture, showing service topology, event flows, and integration points.

## System Topology Overview

```mermaid
graph TB
    subgraph "External Clients"
        USER[Teacher/Educator]
        BROWSER[Web Browser]
    end

    subgraph "Client Interface Layer"
        APIGW[API Gateway Service<br/>Port: 8000<br/>FastAPI]
        WSM[WebSocket Manager<br/>Port: 8001<br/>FastAPI/Starlette]
    end

    subgraph "Orchestration Layer"
        BOS[Batch Orchestrator<br/>Port: 8010<br/>Quart]
        BCS[Batch Conductor<br/>Port: 8011<br/>Quart]
        ELS[Essay Lifecycle<br/>Port: 8020<br/>Quart]
    end

    subgraph "Processing Services"
        FS[File Service<br/>Port: 8030<br/>Quart]
        CS[Content Service<br/>Port: 8040<br/>Quart]
        NLP[NLP Service<br/>Port: 8050<br/>Quart]
        SC[Spellchecker<br/>Port: 8060<br/>Quart]
        LT[Language Tool<br/>Port: 8061<br/>Quart+Java]
        CJ[CJ Assessment<br/>Port: 8070<br/>Quart]
        LPS[LLM Provider<br/>Port: 8080<br/>Quart]
    end

    subgraph "Support Services"
        CM[Class Management<br/>Port: 8090<br/>Quart]
        RAS[Result Aggregator<br/>Port: 8100<br/>Quart]
        ENT[Entitlements<br/>Port: 8110<br/>Quart]
        EMAIL[Email Service<br/>Port: 8120<br/>Quart]
        ID[Identity Service<br/>Port: 8130<br/>FastAPI]
    end

    subgraph "Infrastructure Services"
        KAFKA[Apache Kafka<br/>Port: 9092<br/>Event Bus]
        ZOOKEEPER[Zookeeper<br/>Port: 2181<br/>Kafka Coordination]
        REDIS[Redis<br/>Port: 6379<br/>Cache & Dedup]
    end

    subgraph "Data Persistence"
        PG_BOS[(PostgreSQL<br/>huleedu_batch_orchestrator)]
        PG_ELS[(PostgreSQL<br/>huleedu_essay_lifecycle)]
        PG_FS[(PostgreSQL<br/>huleedu_file)]
        PG_CS[(PostgreSQL<br/>huleedu_content)]
        PG_CM[(PostgreSQL<br/>huleedu_class_management)]
        PG_CJ[(PostgreSQL<br/>huleedu_cj_assessment)]
        PG_RAS[(PostgreSQL<br/>huleedu_result_aggregator)]
        PG_ENT[(PostgreSQL<br/>huleedu_entitlements)]
        PG_ID[(PostgreSQL<br/>huleedu_identity)]
    end

    subgraph "External Integrations"
        OPENAI[OpenAI API<br/>GPT-4]
        ANTHROPIC[Anthropic API<br/>Claude]
        SMTP[SMTP Server<br/>Email Delivery]
    end

    USER -->|HTTPS| BROWSER
    BROWSER -->|REST API| APIGW
    BROWSER -.->|WebSocket| WSM

    APIGW -->|Events| KAFKA
    APIGW -->|Queries| BOS
    APIGW -->|Queries| RAS
    WSM -.->|Subscribe| KAFKA

    BOS <-->|Events| KAFKA
    BCS <-->|Events| KAFKA
    ELS <-->|Events| KAFKA
    FS <-->|Events| KAFKA
    CS <-->|Events| KAFKA
    NLP <-->|Events| KAFKA
    SC <-->|Events| KAFKA
    LT <-->|Events| KAFKA
    CJ <-->|Events| KAFKA
    LPS <-->|Events| KAFKA
    CM <-->|Events| KAFKA
    RAS <-->|Events| KAFKA
    ENT <-->|Events| KAFKA
    EMAIL <-->|Events| KAFKA

    BOS --> PG_BOS
    ELS --> PG_ELS
    FS --> PG_FS
    CS --> PG_CS
    CM --> PG_CM
    CJ --> PG_CJ
    RAS --> PG_RAS
    ENT --> PG_ENT
    ID --> PG_ID

    BOS --> REDIS
    LPS --> REDIS
    CJ --> REDIS
    ELS --> REDIS

    LPS -->|API Calls| OPENAI
    LPS -->|API Calls| ANTHROPIC
    EMAIL -->|SMTP| SMTP

    KAFKA --> ZOOKEEPER

    style KAFKA fill:#f9f,stroke:#333,stroke-width:3px
    style REDIS fill:#ff9,stroke:#333,stroke-width:2px
    style APIGW fill:#9f9,stroke:#333,stroke-width:3px
    style WSM fill:#9f9,stroke:#333,stroke-width:3px
```

## Event Bus Architecture

```mermaid
graph LR
    subgraph "Event Producers"
        BOS_P[Batch Orchestrator]
        ELS_P[Essay Lifecycle]
        FS_P[File Service]
        CJ_P[CJ Assessment]
        LPS_P[LLM Provider]
    end

    subgraph "Kafka Topics"
        T_REG[batch.registration.v1]
        T_CONTENT[essay.content.v1]
        T_LIFECYCLE[essay.lifecycle.v1]
        T_CJ_REQ[cj.assessment.request.v1]
        T_CJ_RESP[cj.assessment.response.v1]
        T_LLM_REQ[llm.comparison.request.v1]
        T_LLM_RESP[llm.comparison.response.v1]
    end

    subgraph "Event Consumers"
        BOS_C[Batch Orchestrator]
        ELS_C[Essay Lifecycle]
        CJ_C[CJ Assessment]
        LPS_C[LLM Provider]
        RAS_C[Result Aggregator]
    end

    BOS_P -->|Publish| T_REG
    FS_P -->|Publish| T_CONTENT
    ELS_P -->|Publish| T_LIFECYCLE
    CJ_P -->|Publish| T_CJ_REQ
    LPS_P -->|Publish| T_LLM_RESP

    T_REG -->|Consume| ELS_C
    T_CONTENT -->|Consume| ELS_C
    T_LIFECYCLE -->|Consume| BOS_C
    T_CJ_REQ -->|Consume| LPS_C
    T_LLM_RESP -->|Consume| CJ_C
    T_CJ_RESP -->|Consume| RAS_C

    style T_REG fill:#ffd,stroke:#333
    style T_CONTENT fill:#ffd,stroke:#333
    style T_LIFECYCLE fill:#ffd,stroke:#333
    style T_CJ_REQ fill:#ffd,stroke:#333
    style T_CJ_RESP fill:#ffd,stroke:#333
    style T_LLM_REQ fill:#ffd,stroke:#333
    style T_LLM_RESP fill:#ffd,stroke:#333
```

## Database Isolation Pattern

```mermaid
graph TB
    subgraph "Service 1: Batch Orchestrator"
        BOS[BOS Service]
        BOS_DB[(huleedu_batch_orchestrator)]
        BOS --> BOS_DB
    end

    subgraph "Service 2: Essay Lifecycle"
        ELS[ELS Service]
        ELS_DB[(huleedu_essay_lifecycle)]
        ELS --> ELS_DB
    end

    subgraph "Service 3: CJ Assessment"
        CJ[CJ Service]
        CJ_DB[(huleedu_cj_assessment)]
        CJ --> CJ_DB
    end

    subgraph "Service 4: Result Aggregator"
        RAS[RAS Service]
        RAS_DB[(huleedu_result_aggregator)]
        RAS --> RAS_DB
    end

    KAFKA[Kafka Event Bus]

    BOS -.->|Events| KAFKA
    ELS -.->|Events| KAFKA
    CJ -.->|Events| KAFKA
    RAS -.->|Events| KAFKA

    KAFKA -.->|Events| BOS
    KAFKA -.->|Events| ELS
    KAFKA -.->|Events| CJ
    KAFKA -.->|Events| RAS

    style BOS_DB fill:#9cf,stroke:#333
    style ELS_DB fill:#9cf,stroke:#333
    style CJ_DB fill:#9cf,stroke:#333
    style RAS_DB fill:#9cf,stroke:#333
    style KAFKA fill:#f9f,stroke:#333,stroke-width:2px
```

**Key Principle**: Each service owns its database exclusively. No direct database access between services. All data sharing occurs via events or HTTP queries.

## Batch Processing Flow

```mermaid
sequenceDiagram
    participant Teacher
    participant APIGW as API Gateway
    participant BOS as Batch Orchestrator
    participant ELS as Essay Lifecycle
    participant FS as File Service
    participant CS as Content Service
    participant Kafka

    Teacher->>APIGW: POST /batches/register
    APIGW->>Kafka: BatchRegistrationCommand
    Kafka->>BOS: BatchRegistrationCommand
    BOS->>Kafka: BatchEssaysRegistered

    Teacher->>APIGW: POST /files/upload
    APIGW->>FS: Upload files
    FS->>CS: Store text content
    CS-->>FS: text_storage_id
    FS->>Kafka: EssayContentReady (for each essay)

    Kafka->>ELS: BatchEssaysRegistered
    Kafka->>ELS: EssayContentReady (x N)

    Note over ELS: Aggregate content readiness<br/>(wait for all N essays)

    ELS->>Kafka: BatchEssaysReady
    Kafka->>BOS: BatchEssaysReady

    Note over BOS: Batch ready for pipeline execution

    Teacher->>APIGW: POST /batches/{id}/pipelines
    APIGW->>Kafka: ClientBatchPipelineRequest
    Kafka->>BOS: ClientBatchPipelineRequest
    BOS->>Kafka: PipelineInitiateCommands
```

## CJ Assessment Pipeline

```mermaid
sequenceDiagram
    participant BOS as Batch Orchestrator
    participant ELS as Essay Lifecycle
    participant CJ as CJ Assessment
    participant LPS as LLM Provider
    participant OpenAI
    participant Kafka

    BOS->>Kafka: CJAssessmentInitiateCommand
    Kafka->>ELS: CJAssessmentInitiateCommand
    ELS->>Kafka: ELS_CJAssessmentRequest
    Kafka->>CJ: ELS_CJAssessmentRequest

    Note over CJ: Generate pairwise comparisons<br/>Apply randomization<br/>Track budget

    loop For each comparison pair
        CJ->>Kafka: LLMComparisonRequest
        Kafka->>LPS: LLMComparisonRequest

        alt Using OpenAI
            LPS->>OpenAI: API call
            OpenAI-->>LPS: Comparison result
        else Using Anthropic
            LPS->>Anthropic: API call
            Anthropic-->>LPS: Comparison result
        end

        LPS->>Kafka: LLMComparisonResponse
        Kafka->>CJ: LLMComparisonResponse

        Note over CJ: Persist comparison<br/>Check completion threshold
    end

    Note over CJ: Calculate BT-scores<br/>Project grades (if anchors)

    CJ->>Kafka: CJAssessmentCompleted
    Kafka->>ELS: CJAssessmentCompleted
    ELS->>Kafka: BatchPhaseCompleted
```

## Service Dependencies and Data Flow

```mermaid
graph TB
    subgraph "Entry Points"
        APIGW[API Gateway<br/>HTTP Entry]
    end

    subgraph "Orchestration"
        BOS[Batch Orchestrator<br/>Pipeline Control]
        BCS[Batch Conductor<br/>Dependency Resolution]
        ELS[Essay Lifecycle<br/>State Tracking]
    end

    subgraph "Content Pipeline"
        FS[File Service<br/>Upload & Extract]
        CS[Content Service<br/>Storage]
    end

    subgraph "Student Matching (Phase 1)"
        NLP_P1[NLP Service<br/>Name Extraction]
        CM[Class Management<br/>Student Roster]
    end

    subgraph "Processing Pipeline (Phase 2)"
        SC[Spellchecker]
        NLP_P2[NLP Service<br/>Text Analysis]
        CJ[CJ Assessment]
        LPS[LLM Provider]
    end

    subgraph "Results"
        RAS[Result Aggregator<br/>Query Surface]
    end

    APIGW -->|Commands| BOS
    BOS -->|Batch Control| ELS
    BCS -->|Phase Dependencies| ELS

    ELS -->|Content Request| FS
    FS -->|Store Text| CS
    CS -->|text_storage_id| FS

    ELS -->|Phase 1: Student Matching| NLP_P1
    NLP_P1 -->|Match Suggestions| CM
    CM -->|Confirmations| ELS

    ELS -->|Phase 2: Spellcheck| SC
    ELS -->|Phase 2: NLP Analysis| NLP_P2
    ELS -->|Phase 2: CJ Assessment| CJ
    CJ -->|LLM Requests| LPS

    SC -->|Results| RAS
    NLP_P2 -->|Results| RAS
    CJ -->|Results| RAS

    RAS -->|Query Results| APIGW

    style APIGW fill:#9f9,stroke:#333,stroke-width:2px
    style BOS fill:#fcf,stroke:#333,stroke-width:2px
    style ELS fill:#fcf,stroke:#333,stroke-width:2px
    style RAS fill:#ff9,stroke:#333,stroke-width:2px
```

## External Integration Points

```mermaid
graph LR
    subgraph "HuleEdu Platform"
        LPS[LLM Provider Service]
        EMAIL[Email Service]
        ID[Identity Service]
    end

    subgraph "External LLM Providers"
        OPENAI[OpenAI API<br/>gpt-4-turbo<br/>gpt-4o]
        ANTHROPIC[Anthropic API<br/>claude-sonnet-4-5<br/>claude-opus-4]
    end

    subgraph "External Services"
        SMTP[SMTP Server<br/>Email Delivery]
        OAUTH[OAuth Provider<br/>Optional Future]
    end

    LPS -->|HTTP/REST| OPENAI
    LPS -->|HTTP/REST| ANTHROPIC
    EMAIL -->|SMTP Protocol| SMTP
    ID -.->|Future| OAUTH

    style OPENAI fill:#fcc,stroke:#333,stroke-dasharray: 5 5
    style ANTHROPIC fill:#fcc,stroke:#333,stroke-dasharray: 5 5
    style SMTP fill:#fcc,stroke:#333,stroke-dasharray: 5 5
    style OAUTH fill:#ccc,stroke:#333,stroke-dasharray: 5 5
```

**Note**: External integrations are isolated within specific services (LPS, Email, Identity) to centralize configuration, rate limiting, and error handling.

## Observability Stack

```mermaid
graph TB
    subgraph "HuleEdu Services"
        SVC1[Service 1]
        SVC2[Service 2]
        SVC3[Service N]
    end

    subgraph "Metrics Collection"
        PROM[Prometheus<br/>Port: 9090<br/>Metrics Storage]
        PROM_EXP[Prometheus Exporters<br/>Per-service /metrics]
    end

    subgraph "Distributed Tracing"
        JAEGER[Jaeger<br/>Port: 16686<br/>Trace Collection]
        JAEGER_AGENT[Jaeger Agent<br/>Per-service tracer]
    end

    subgraph "Centralized Logging"
        LOKI[Grafana Loki<br/>Port: 3100<br/>Log Aggregation]
        PROMTAIL[Promtail<br/>Log Shipper]
    end

    subgraph "Visualization"
        GRAFANA[Grafana<br/>Port: 3000<br/>Dashboards & Alerts]
    end

    SVC1 -->|Metrics| PROM_EXP
    SVC2 -->|Metrics| PROM_EXP
    SVC3 -->|Metrics| PROM_EXP
    PROM_EXP -->|Scrape| PROM

    SVC1 -->|Spans| JAEGER_AGENT
    SVC2 -->|Spans| JAEGER_AGENT
    SVC3 -->|Spans| JAEGER_AGENT
    JAEGER_AGENT -->|Export| JAEGER

    SVC1 -->|Logs| PROMTAIL
    SVC2 -->|Logs| PROMTAIL
    SVC3 -->|Logs| PROMTAIL
    PROMTAIL -->|Push| LOKI

    PROM -->|Data Source| GRAFANA
    JAEGER -->|Data Source| GRAFANA
    LOKI -->|Data Source| GRAFANA

    style PROM fill:#fdd,stroke:#333
    style JAEGER fill:#dfd,stroke:#333
    style LOKI fill:#ddf,stroke:#333
    style GRAFANA fill:#ffd,stroke:#333,stroke-width:3px
```

## Network Communication Patterns

### Asynchronous (Kafka Events)
- **Use case**: State changes, pipeline orchestration, cross-service notifications
- **Pattern**: Fire-and-forget with at-least-once delivery
- **Examples**: `BatchEssaysRegistered`, `EssayContentReady`, `CJAssessmentCompleted`

### Synchronous (HTTP Queries)
- **Use case**: Immediate data retrieval, file upload proxying
- **Pattern**: Request-response with timeout handling
- **Examples**: API Gateway → RAS queries, File upload → File Service

### WebSocket (Real-time Updates)
- **Use case**: Client-side real-time notifications
- **Pattern**: Server-push from Kafka event subscriptions
- **Examples**: Batch status changes, essay processing progress

## Service Scaling Patterns

```mermaid
graph TB
    subgraph "Stateless Services (Horizontal Scaling)"
        FS[File Service<br/>Multiple Instances]
        SC[Spellchecker<br/>Multiple Instances]
        NLP[NLP Service<br/>Multiple Instances]
    end

    subgraph "Stateful Services (Careful Scaling)"
        LPS[LLM Provider<br/>Queue Coordination]
        CJ[CJ Assessment<br/>Batch State Management]
    end

    subgraph "Singleton Services"
        BOS[Batch Orchestrator<br/>Single Instance]
        ELS[Essay Lifecycle<br/>Single Instance]
    end

    LB[Load Balancer]
    KAFKA[Kafka<br/>Partitioned Topics]
    REDIS[Redis<br/>Coordination]

    LB -->|Round Robin| FS
    LB -->|Round Robin| SC
    LB -->|Round Robin| NLP

    LPS -->|Deduplication| REDIS
    CJ -->|Locking| REDIS

    FS -->|Events| KAFKA
    SC -->|Events| KAFKA
    NLP -->|Events| KAFKA
    LPS -->|Events| KAFKA
    CJ -->|Events| KAFKA
    BOS -->|Events| KAFKA
    ELS -->|Events| KAFKA

    style FS fill:#9f9,stroke:#333
    style SC fill:#9f9,stroke:#333
    style NLP fill:#9f9,stroke:#333
    style LPS fill:#ff9,stroke:#333
    style CJ fill:#ff9,stroke:#333
    style BOS fill:#f99,stroke:#333
    style ELS fill:#f99,stroke:#333
```

**Scaling Guidance**:
- **Stateless services**: Scale horizontally based on CPU/memory metrics
- **Stateful services**: Require Redis coordination for distributed state
- **Singleton services**: Currently designed for single instance (future: leader election)

## Key Architectural Properties

### 1. Loose Coupling
Services communicate via events and never import from other services. All contracts defined in `libs/common_core`.

### 2. Database Per Service
Each service owns its database schema and data. No shared databases or cross-service queries.

### 3. Event Sourcing Lite
Critical state transitions published as events to Kafka for audit trail and downstream processing.

### 4. Circuit Breaker Pattern
External integrations (LLM APIs, SMTP) protected by circuit breakers with fallback behavior.

### 5. Idempotency
All event consumers use correlation_id-based deduplication via Redis to safely handle duplicate events.

### 6. Observability First
Metrics, traces, and logs built into every service from day one, not retrofitted later.

## Reference Documentation

- **Service Architectures**: `.claude/rules/020.x-*-architecture.md`
- **Event Standards**: `.claude/rules/052-event-contract-standards.md`
- **Processing Flows**: `.claude/rules/035-complete-processing-flow-overview.md`
- **Testing Patterns**: `.claude/rules/075-test-creation-methodology.md`
- **Docker Setup**: `.claude/rules/081.1-docker-development-workflow.md`
