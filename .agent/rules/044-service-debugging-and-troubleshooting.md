---
id: "044-service-debugging-and-troubleshooting"
type: "operational"
created: 2025-06-06
last_updated: 2025-11-17
scope: "all"
child_rules: ["044.1-circuit-breaker-observability", "044.2-redis-kafka-state-debugging"]
---
# 044: Service Debugging and Troubleshooting

## 1. Purpose

Systematic debugging approach for HuleEdu microservice issues, prioritizing service configuration validation over code patterns.

**Key Insight**: Import errors and dependency issues often mask underlying service configuration problems.

## 2. Debugging Priority Order

### 2.1. Service Configuration (Priority 1)

**Check these FIRST before investigating code patterns**:

1. **Dependency Injection Container Usage**
   - Verify services get dependencies from DI container, not manual instantiation
   - Check for constructor signature mismatches indicating DI bypass
   - Validate protocol implementations are registered in DI providers

2. **Docker Environment and Health Checks**
   - Validate `PYTHONPATH=/app` in service Dockerfiles
   - Verify health check ports match actual service ports
   - Check environment variable naming matches Pydantic `env_prefix` patterns

3. **Web Server Configuration**
   - Test framework configuration methods (avoid "magic" like `config.from_object()`)
   - Validate port binding and network configuration
   - Confirm configuration objects receive expected values

4. **Database and External Service Connectivity**
   - Verify connection strings and credentials
   - Check service discovery and network routing
   - Validate async connection pooling configuration

### 2.2. Code Patterns (Priority 2)

**Only after service configuration is validated**:

1. Import patterns and module structure
2. Type annotation and protocol conformance
3. Code organization and architectural compliance

## 3. Common Configuration Anti-Patterns

### 3.1. Manual Dependency Instantiation

**❌ FORBIDDEN**:

```python
# Bypassing DI container
event_publisher = DefaultEventPublisher(kafka_producer)
service = MyService(event_publisher, db_connection)
```

**✅ REQUIRED**:

```python
# Using DI container
service = await container.get(MyServiceProtocol)
```

### 3.2. Framework Configuration Shortcuts

**❌ AVOID**:

```python
# Unreliable framework "magic"
config.from_object(config_module)
```

**✅ PREFER**:

```python
# Explicit configuration
config.bind = [f"{settings.HOST}:{settings.PORT}"]
config.workers = settings.WEB_CONCURRENCY
```

### 3.3. Misaligned Health Checks

**❌ COMMON ERROR**:

```yaml
# Health check port doesn't match service port
healthcheck:
  test: ["CMD-SHELL", "curl -f http://localhost:5000/healthz || exit 1"]
# Service actually runs on port 8000
```

**✅ CORRECT**:

```yaml
# Health check port matches service configuration
healthcheck:
  test: ["CMD-SHELL", "curl -f http://localhost:8000/healthz || exit 1"]
```

## 4. Diagnostic Commands

### 4.1. Service Configuration Validation

```bash
# Check container environment
docker exec <container> env | grep -E "PORT|PATH|SERVICE"

# Test health endpoints
curl -s http://localhost:<port>/healthz

# Check service logs for configuration loading
docker compose logs <service> | grep -i "config\|port\|bind"
```

### 4.2. Dependency Injection Validation

```python
# Add temporary debug output to see DI resolution
container = make_async_container(ServiceProvider())
async with container() as request_container:
    service = await request_container.get(ServiceProtocol)
    print(f"DEBUG: Got service instance: {type(service)}")
```

### 4.3. Docker Service Health

```bash
# Check service status and dependencies
docker compose ps
docker compose logs <service> --tail=20

# Test internal health checks
docker exec <container> curl -f http://localhost:<internal_port>/healthz
```

## 5. Debugging Workflow

### 5.1. Initial Assessment

1. **Container Status**: `docker compose ps` - identify failing services
2. **Log Analysis**: Look for configuration loading, not just error messages
3. **Health Check Validation**: Test endpoints manually
4. **Environment Variables**: Verify naming patterns and values

### 5.2. Configuration Deep Dive

1. **DI Container**: Verify all dependencies resolve correctly
2. **Web Server**: Check bind addresses, ports, and worker configuration
3. **Database**: Test connections and pool settings
4. **External Services**: Validate service discovery and routing

### 5.3. Code Pattern Review (Last Resort)

1. Import patterns and module organization
2. Protocol conformance and type safety
3. Async pattern compliance

## 6. Prevention Guidelines

### 6.1. Development Practices

- **ALWAYS** use DI container for dependency resolution
- **VALIDATE** configuration loading with debug output during development
- **TEST** health endpoints during service development
- **ALIGN** docker-compose environment variables with Pydantic settings

### 6.2. Code Review Focus

- Verify DI container usage over manual instantiation
- Check health check configurations match service ports
- Validate environment variable naming patterns
- Confirm explicit configuration over framework defaults

## 7. Rule Priority Update

**CHANGED**: Import pattern rules are now secondary to service configuration validation.

**When debugging container failures**:

1. ✅ **First**: Check service configuration (DI, Docker, web server)
2. ✅ **Second**: Validate code patterns and imports

**Import errors often indicate service configuration problems, not import pattern issues.**
