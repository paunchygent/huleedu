# Changelog

All notable changes to the HuleEdu microservices platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-01-30

### 🎉 Sprint 1 (Phase 1.2) Complete - Walking Skeleton Production Ready

This release marks the completion of Sprint 1 with a fully functional walking skeleton that demonstrates end-to-end essay processing capabilities across all microservices.

### Added

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

### Changed

#### **Event Schema Evolution**

- **Breaking**: Replaced `EssayContentReady` events with `EssayContentProvisionedV1`
- **Enhanced**: Event envelope structure with proper correlation ID support
- **Improved**: Batch readiness events now use `List[EssayProcessingInputRefV1]` structure

#### **Service Architecture**

- **Refactored**: All services now use clean dependency injection patterns
- **Standardized**: Consistent Blueprint structure for HTTP services
- **Optimized**: Docker Compose configuration with proper health checks and dependencies

### Fixed

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

### Documentation

- **Architecture Documentation**: Updated service interaction patterns and event flows
- **API Documentation**: Comprehensive endpoint documentation for all HTTP services
- **Deployment Guide**: Docker Compose setup and configuration documentation
- **Testing Guide**: E2E testing procedures and validation scripts

---

## [0.1.0] - 2025-01-15

### Added

- Initial microservices architecture setup
- Basic service implementations
- Docker containerization
- Kafka event infrastructure
- Core spell checking functionality

### Infrastructure

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
