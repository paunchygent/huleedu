# Changelog

All notable changes to the HuleEdu microservices platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### **GrammarError Contract Enhancement**

- **Enhanced GrammarError model** with context fields for improved error analysis
  - Added `category_id` and `category_name` for detailed grammar categorization
  - Added `context` and `context_offset` for surrounding text visibility
  - Enables richer AI feedback generation and analytics
  - Part of Language Tool Service integration (TASK-052A)

## [0.3.0] - 2025-01-31

### 🎉 BCS Integration Complete - Intelligent Pipeline Orchestration

This release completes the implementation and integration of the **Batch Conductor Service (BCS)** for intelligent pipeline dependency resolution, marking a major milestone in dynamic pipeline orchestration capabilities.

### Added

#### **Batch Conductor Service (BCS) - Full Implementation**

- **Production-Ready Architecture**: Complete Quart-based internal microservice with 24/24 tests passing
  - Event-driven batch state projection via Kafka (eliminates ELS polling)
  - Atomic Redis operations with WATCH/MULTI/EXEC pattern for race condition safety
  - DLQ production for pipeline resolution failures with comprehensive error metadata
  - Exponential backoff retry logic with graceful fallback mechanisms

- **Intelligent Pipeline Resolution Engine**: 
  - Dependency rules engine with prerequisite validation (ai_feedback → spellcheck, cj_assessment → spellcheck)
  - Batch state-aware optimization with completed step pruning
  - Real-time state projection consuming `SpellcheckResultDataV1` and `CJAssessmentResultDataV1` events

- **Comprehensive Error Handling & Observability**:
  - Prometheus metrics: `bcs_pipeline_resolutions_total{status="success"|"failure"}`
  - Structured logging with correlation ID tracking across events and requests
  - DLQ topics following `<base_topic>.DLQ` pattern for failure replay capability

#### **BOS ↔ BCS HTTP Integration**

- **HTTP Client Integration**: `BatchConductorClientProtocol` and implementation for BOS
- **Pipeline Resolution Workflow**: BOS calls BCS `/internal/v1/pipelines/define` API for intelligent pipeline construction
- **E2E Validation**: Complete workflow testing from client requests through BCS pipeline resolution to execution

### Changed

#### **Enhanced Service Architecture**

- **BOS Dependencies**: Updated to include BCS HTTP client integration with proper error handling
- **Documentation**: Comprehensive updates across README files reflecting BCS integration status
- **Service Discovery**: Added BCS to main service architecture documentation

#### **Pipeline Orchestration Evolution**

- **Dynamic Resolution**: BOS now leverages BCS for intelligent, state-aware pipeline construction
- **Dependency Management**: Centralized pipeline dependency logic in BCS reduces coupling
- **State Management**: Real-time batch state tracking without synchronous service calls

### Fixed

#### **Architecture Completeness**

- **Service Integration**: Resolved missing BCS documentation across project documentation
- **Rule Index**: Added BCS architecture rule to development standards index
- **Status Reporting**: Updated development status to reflect completed BCS integration

### Technical Implementation

#### **Event-Driven Architecture**

- **Real-Time State Projection**: BCS maintains current batch state via Kafka event consumption
- **Decoupled Design**: Eliminates synchronous API dependencies between BCS and ELS
- **Resilient Processing**: Comprehensive error boundaries with DLQ production for replay

#### **Production Resilience**

- **Atomic Operations**: Redis WATCH/MULTI/EXEC prevents race conditions in concurrent processing
- **Retry Mechanisms**: Exponential backoff with configurable retry limits (up to 5 attempts)
- **Graceful Degradation**: Fallback to non-atomic operations when atomic retries exhausted

### Performance & Reliability

- **High Throughput**: Redis-cached state management for fast pipeline resolution
- **Error Isolation**: Failed pipeline resolutions don't impact other batch operations
- **Monitoring**: Production-ready observability with metrics and structured logging

### Documentation

- **Service READMEs**: Updated BCS, BOS, and main project documentation with integration details
- **Architecture Rules**: Added BCS to development standards and rule index
- **Implementation Status**: Comprehensive status updates reflecting production-ready implementation

---

## [0.2.0] - 2025-01-30

### 🎉 Sprint 1 (Phase 1.2) Complete - Walking Skeleton Production Ready

This release marks the completion of Sprint 1 with a fully functional walking skeleton that demonstrates end-to-end essay processing capabilities across all microservices.

### Added in Sprint 1

#### **CI/CD Infrastructure**

- **GitHub Actions Smoke Test**: Comprehensive CI pipeline that validates walking skeleton functionality
  - Docker Compose service startup validation
  - Health check endpoint verification for all HTTP services
  - Prometheus metrics endpoint validation
  - Kafka infrastructure connectivity testing
  - Basic API connectivity validation
  - Automatic log collection on failures
  - 15-minute timeout with proper cleanup

#### **Architecture & Event-Driven Communication**

- **Essay ID Coordination Architecture**: Complete resolution of essay ID coordination between services
  - BOS-generated internal essay ID slots with ELS assignment
  - Proper event flow: File Service → Content Service → ELS coordination
  - `EssayContentProvisionedV1` event implementation replacing legacy patterns
- **EventEnvelope Schema Versioning**: Robust event contract system with proper versioning
- **Dependency Injection Protocols**: Clean architecture with `typing.Protocol` interfaces across all services

#### **Service Capabilities**

- **Spell Checker Service**: Production-ready L2 + pyspellchecker algorithm
  - 4,886 L2 error corrections with intelligent filtering
  - Comprehensive correction logging and metrics
  - Multi-language support (English, Spanish)
  - Case preservation and punctuation handling
- **Content Service**: Reliable content storage and retrieval with health monitoring
- **File Service**: File upload processing with content ingestion pipeline
- **Essay Lifecycle Service**: State management and processing orchestration
- **Batch Orchestrator Service**: Batch coordination and essay slot management

#### **Monitoring & Observability**

- **Prometheus Metrics**: Comprehensive metrics across all services
  - HTTP request/response metrics
  - Kafka consumer lag monitoring
  - Service-specific business metrics
  - Health check status tracking
- **Structured Logging**: Correlation ID propagation across service boundaries
- **Health Check Endpoints**: Standardized `/healthz` endpoints for all HTTP services

### Changed in Sprint 1

#### **Event Schema Evolution**

- **Breaking**: Replaced `EssayContentReady` events with `EssayContentProvisionedV1`
- **Enhanced**: Event envelope structure with proper correlation ID support
- **Improved**: Batch readiness events now use `List[EssayProcessingInputRefV1]` structure

#### **Service Architecture**

- **Refactored**: All services now use clean dependency injection patterns
- **Standardized**: Consistent Blueprint structure for HTTP services
- **Optimized**: Docker Compose configuration with proper health checks and dependencies

### Fixed in Sprint 1

#### **Critical Architecture Issues**

- **Essay ID Coordination**: Resolved mismatched essay ID handling between File Service and ELS
- **Event Flow**: Fixed event type misalignments in inter-service communication
- **Batch Processing**: Corrected batch readiness detection and essay slot assignment

#### **Service Reliability**

- **Kafka Topic Management**: Automated topic creation and proper bootstrap handling
- **Error Handling**: Improved error propagation and failure recovery across services
- **Resource Management**: Proper cleanup and resource management in all services

### Infrastructure

#### **Development & Testing**

- **Test Coverage**: 77 unit tests passing with comprehensive coverage
- **E2E Testing**: Walking skeleton end-to-end validation confirmed
- **Docker Compose**: Production-ready containerization with health checks
- **PDM Monorepo**: Consistent dependency management across all packages

#### **Quality Assurance**

- **Linting**: Ruff compliance across all services
- **Type Safety**: MyPy validation with proper type annotations
- **Code Standards**: Consistent Python coding standards and documentation

### Technical Debt Resolved

- **Legacy Event Types**: Removed outdated event schemas and handlers
- **Inconsistent Versioning**: Unified version management across all packages
- **Service Coupling**: Eliminated direct service dependencies through proper event-driven patterns
- **Configuration Management**: Standardized service configuration patterns

### Performance

- **Service Startup**: Optimized Docker Compose startup sequence with health check dependencies
- **Event Processing**: Efficient Kafka message processing with proper error handling
- **Resource Usage**: Optimized container resource allocation and management

### Documentation Updated

- **Architecture Documentation**: Updated service interaction patterns and event flows
- **API Documentation**: Comprehensive endpoint documentation for all HTTP services
- **Deployment Guide**: Docker Compose setup and configuration documentation
- **Testing Guide**: E2E testing procedures and validation scripts

---

## [0.1.0] - 2025-01-15

### Added during Walking Skeleton Sprint

- Initial microservices architecture setup
- Basic service implementations
- Docker containerization
- Kafka event infrastructure
- Core spell checking functionality

### Changed/Infrastructure

- PDM monorepo structure
- Basic CI/CD pipeline setup
- Service discovery and communication patterns

---

## Release Notes

### v0.2.0 Highlights

**🎯 Sprint 1 Achievement**: Complete walking skeleton with production-ready capabilities
**🔧 Architecture**: Event-driven microservices with proper service boundaries  
**📊 Monitoring**: Comprehensive metrics and health monitoring
**🧪 Testing**: Robust CI pipeline with automated validation
**📚 Documentation**: Complete architectural documentation and deployment guides

This release establishes the foundation for the HuleEdu essay processing platform with a fully functional, monitored, and tested microservices architecture ready for production deployment.
