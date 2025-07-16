---
inclusion: always
---

# HuleEdu Project Overview

## Project Context
You are working on the HuleEdu Monorepo - a microservices-based educational platform for essay processing and assessment. This is a production-ready system with strict architectural standards.

## Core Architecture Principles
- **Domain-Driven Design (DDD)**: Each service owns a specific business domain
- **Event-Driven Architecture**: Asynchronous communication via Kafka is primary
- **Service Autonomy**: Services are independently deployable and scalable
- **Explicit Contracts**: All inter-service communication uses versioned Pydantic models
- **Clean Architecture**: Protocol-based dependency injection with Dishka

## Technology Stack
- **Python 3.11+** with async/await patterns
- **PDM** for dependency management
- **Quart** for HTTP services, **aiokafka** for event streaming
- **Pydantic v2** for data validation and contracts
- **PostgreSQL/SQLite** for persistence
- **Docker Compose** for local development
- **Prometheus/Grafana** for observability

## Project Structure
- `common_core/`: Shared Pydantic models and contracts
- `services/`: Individual microservices with clean architecture
- `services/libs/`: Shared service utilities (Kafka, logging, metrics)
- `.cursor/rules/`: Comprehensive development standards (MUST follow)
- `scripts/`: Project automation and setup tools

## Current Services (All Implemented)
- Content Service, Spell Checker Service, Batch Orchestrator Service
- Essay Lifecycle Service, File Service, CJ Assessment Service
- Class Management Service, Result Aggregator Service, LLM Provider Service
- Batch Conductor Service, API Gateway Service

## Development Standards
All code MUST adhere to the rules in `.cursor/rules/` directory. Key requirements:
- Use `huleedu_service_libs` for logging, Kafka, and metrics
- Protocol-based dependency injection with Dishka
- Comprehensive error handling and observability
- Test-driven development with unit, integration, and contract tests