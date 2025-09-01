# Rule 085: Frontend Development Utilities Standards

## **ULTRATHINK: Development-First Frontend Integration**

### **Core Principle**
Development utilities MUST be environment-gated, Svelte 5-optimized, and production-isolated.

## **Development Endpoints**

### **Mandatory Mock Endpoints**
```typescript
/dev/mock/classes          // Svelte 5 $state() compatible class data
/dev/mock/students/{id}    // Student roster with realistic variations
/dev/mock/essays/{status}  // Essay processing states (use EssayStatus enum)
/dev/mock/batches          // Batch data covering all BatchStatus states
/dev/mock/reactive-state   // Svelte 5 runes patterns ($state, $derived, $effect)
/dev/mock/websocket/trigger // WebSocket notification simulation
/dev/auth/test-token       // Configurable JWT generation
```

### **Endpoint Requirements**
- **MUST** use existing Pydantic models for data structure validation
- **MUST** include metadata with generation timestamps and counts
- **MUST** provide realistic data variations for different UI states
- **MUST** support Svelte 5 reactive patterns in data structure

## **CORS Configuration**

### **Development Ports Priority**
```python
CORS_ORIGINS: list[str] = Field(default=[
    "http://localhost:5173",  # Vite dev server (PRIMARY)
    "http://localhost:4173",  # Vite preview server
    "http://localhost:3000",  # Legacy/backup port
])
```

### **Service Harmonization**
- **API Gateway** and **WebSocket Service** CORS MUST match exactly
- **NEVER** use React-specific ports without Vite ports
- **ALWAYS** prioritize Vite development ports (5173, 4173)

## **Environment Isolation**

### **Development Gating**
```python
# Route registration
if settings.ENV_TYPE.lower() in ["development", "dev", "local"]:
    app.include_router(dev_routes.router, prefix="/dev", tags=["Development"])

# Middleware activation  
if is_development_environment():
    app.add_middleware(DevelopmentMiddleware, settings=settings)
```

### **Security Requirements**
- **NEVER** expose development endpoints in production
- **ALWAYS** validate environment before route registration
- **MUST** use proper environment detection utilities

## **Development Middleware**

### **Debug Headers (Development Only)**
```
X-HuleEdu-Environment: development
X-HuleEdu-Dev-Mode: enabled
X-HuleEdu-CORS-Origins: {comma-separated origins}
X-HuleEdu-Service: {service-name}
```

### **Middleware Features**
- Environment detection and gating
- Request debugging and logging
- CORS origin information
- Service identification

## **Mock Data Patterns**

### **Svelte 5 Optimization**
```typescript
// Data structure for reactive patterns
{
  "app_state": {
    "user": { /* user object */ },
    "loading_states": { /* $state booleans */ },
    "error_states": { /* error tracking */ }
  },
  "reactive_counters": { /* $derived calculations */ },
  "real_time_updates": { /* WebSocket status */ }
}
```

### **Data Generation Rules**
- **MUST** use datetime.now(timezone.utc) for timestamps
- **MUST** include realistic variations (different states, counts, statuses)
- **MUST** provide enum-compliant status values
- **SHOULD** include pagination metadata where applicable

## **Test Token Generation**

### **Configuration Options**
```python
user_type: Literal["teacher", "student", "admin"] = "teacher"
expires_minutes: int = 60  # 1-1440 range
class_id: str | None = None
custom_claims: dict[str, Any] | None = None
```

### **Token Requirements**
- **MUST** generate realistic JWT payload with proper claims
- **MUST** work with existing authentication middleware
- **MUST** include usage examples in response
- **SHOULD** provide curl examples for testing

## **Documentation Standards**

### **Frontend Integration Updates**
- **MUST** update `docs/SVELTE_INTEGRATION_GUIDE.md` when adding utilities
- **MUST** include TypeScript examples for new endpoints
- **MUST** document environment-specific features
- **SHOULD** provide practical usage patterns

### **Code Comments**
```python
# Development routes (only in development environment)
# Mock data endpoints optimized for Svelte 5 + Vite frontend development
# Only available in development environment for security isolation
```

## **Testing Requirements**

### **Validation Checklist**
- [ ] CORS works with Vite dev server (port 5173) without errors
- [ ] Mock endpoints return valid data matching API schemas  
- [ ] Test tokens validate with existing auth middleware
- [ ] Development features completely isolated from production
- [ ] WebSocket mock notifications trigger correctly

### **Integration Testing**
```bash
# Required tests after implementation
curl -i -H "Origin: http://localhost:5173" http://localhost:8080/dev/mock/classes
curl -s http://localhost:8080/dev/auth/test-token -X POST -H "Content-Type: application/json" -d '{}'
```

## **Implementation Notes**

- **Environment Utils**: Use `utils/cors_utils.py` for environment-specific CORS management
- **Route Prefix**: Always use `/dev/` prefix for development endpoints
- **Error Handling**: Follow structured error handling patterns with proper HTTP status codes
- **Logging**: Use service-specific loggers for development endpoint usage

## **Violations**

❌ **NEVER** expose development routes in production  
❌ **NEVER** hardcode CORS origins without environment consideration  
❌ **NEVER** create mock data that doesn't match existing schemas  
❌ **NEVER** implement development features without proper environment gating

---
*Rule 085 establishes standards for development utilities that enhance frontend integration while maintaining production security and code quality.*
