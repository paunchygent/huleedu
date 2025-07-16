---
inclusion: fileMatch
fileMatchPattern: "**/services/**"
---

# Service-Specific Implementation Guidance

## Service Architecture References

When working on specific services, refer to these detailed architecture documents:

### Core Processing Services
- **Content Service**: `.cursor/rules/020.1-content-service-architecture.mdc`
- **Spell Checker Service**: `.cursor/rules/020.2-spell-checker-service-architecture.mdc`
- **Essay Lifecycle Service**: `.cursor/rules/020.5-essay-lifecycle-service-architecture.mdc`
- **File Service**: `.cursor/rules/020.6-file-service-architecture.mdc`

### Orchestration Services
- **Batch Orchestrator Service**: `.cursor/rules/020.3-batch-orchestrator-service-architecture.mdc`
- **Batch Conductor Service**: `.cursor/rules/020.8-batch-conductor-service.mdc`
- **Result Aggregator Service**: `.cursor/rules/020.12-result-aggregator-service-architecture.mdc`

### Assessment Services
- **CJ Assessment Service**: `.cursor/rules/020.7-cj-assessment-service.mdc`
- **LLM Provider Service**: `.cursor/rules/020.13-llm-provider-service-architecture.mdc`

### Management Services
- **Class Management Service**: `.cursor/rules/020.9-class-management-service.mdc`
- **API Gateway Service**: `.cursor/rules/020.10-api-gateway-and-websocket-service.mdc`

## Service Implementation Checklist

### HTTP Services (Quart-based)
- [ ] Blueprint pattern with `/api` directory structure
- [ ] `startup_setup.py` with DI and metrics initialization
- [ ] Health endpoint (`/healthz`) with dependency checks
- [ ] Metrics endpoint (`/metrics`) with Prometheus integration
- [ ] Graceful shutdown handling
- [ ] Request/response logging with correlation IDs

### Worker Services (Kafka-based)
- [ ] Signal handling for SIGTERM/SIGINT
- [ ] Event processor with protocol-based dependencies
- [ ] Manual Kafka offset commits after successful processing
- [ ] Dead letter queue handling for failed events
- [ ] Idempotency checking with Redis
- [ ] Structured error logging with context

### Database Integration
- [ ] SQLAlchemy models with proper relationships
- [ ] Repository pattern with protocol interfaces
- [ ] Database migrations with Alembic
- [ ] Connection pooling configuration
- [ ] Transaction management for consistency
- [ ] Proper error handling for database operations

### External Service Integration
- [ ] Circuit breaker patterns for resilience
- [ ] Retry logic with exponential backoff
- [ ] Timeout configuration for all HTTP calls
- [ ] Fallback mechanisms for degraded service
- [ ] Monitoring and alerting for external dependencies

## Common Service Patterns

### Service Initialization
```python
# Standard service startup pattern
async def initialize_service():
    logger.info("Starting service initialization...")
    
    # Load configuration
    config = ServiceConfig()
    
    # Setup DI container
    container = make_container(config)
    
    # Initialize external connections
    await setup_database(config.database_url)
    await setup_kafka(config.kafka_bootstrap_servers)
    
    logger.info("Service initialization complete")
    return container
```

### Error Boundary Pattern
```python
# Wrap operations with error boundaries
async def process_with_error_boundary(operation, context):
    try:
        return await operation()
    except Exception as e:
        logger.error(f"Operation failed: {e}", extra=context)
        await send_error_event(e, context)
        raise
```

### Resource Cleanup Pattern
```python
# Ensure proper resource cleanup
async def cleanup_resources():
    logger.info("Starting resource cleanup...")
    
    # Close database connections
    await database.disconnect()
    
    # Stop Kafka consumers/producers
    await kafka_bus.stop()
    
    # Close HTTP client sessions
    await http_client.aclose()
    
    logger.info("Resource cleanup complete")
```