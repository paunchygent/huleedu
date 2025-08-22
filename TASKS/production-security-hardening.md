# Production Security Hardening Task

## Task Status: 🔴 CRITICAL - NOT STARTED

**Created**: 2025-01-21  
**Priority**: CRITICAL - Must complete before production deployment  
**Estimated Effort**: 8-12 hours  
**Dependencies**: Identity Service security patterns (completed)

## Executive Summary

A comprehensive security audit revealed severe vulnerabilities across the HuleEdu monorepo that could lead to API key theft, database breaches, and system compromise. All sensitive configuration values are currently exposed as plain text in logs, error messages, and debug output.

## Critical Vulnerabilities Discovered

### 🔴 CRITICAL - Immediate Action Required

#### 1. LLM Provider Service - Exposed API Keys
**Location**: `services/llm_provider_service/config.py`
- **Exposed Secrets**:
  - `OPENAI_API_KEY` - Plain text
  - `ANTHROPIC_API_KEY` - Plain text  
  - `GOOGLE_API_KEY` - Plain text
  - `OPENROUTER_API_KEY` - Plain text
  - `LLM_ADMIN_API_KEY` - Plain text
- **Risk**: API key theft leading to massive unauthorized billing, data exfiltration
- **Impact**: $10,000+ potential financial loss per compromised key

#### 2. Database Credentials - All Services
**Location**: All `services/*/config.py` files
- **Exposed Secrets**:
  - `HULEEDU_DB_PASSWORD` - Plain text across all services
  - `HULEEDU_PROD_DB_PASSWORD` - Production database password
  - Connection strings in error messages
- **Risk**: Complete database compromise, data breach
- **Impact**: Total system compromise, GDPR violations, data loss

#### 3. Internal Service Authentication
**Location**: Multiple service configurations
- **Exposed Secrets**:
  - `HULEEDU_INTERNAL_API_KEY` - Plain text
  - Service-to-service authentication tokens
- **Risk**: Unauthorized service access, lateral movement in breach
- **Impact**: Service impersonation, data manipulation

### 🟠 HIGH PRIORITY

#### 4. API Gateway Service
**Location**: `services/api_gateway_service/config.py`
- External-facing service without proper secret management
- Missing rate limiting secrets
- No API key rotation mechanism

#### 5. Monitoring Credentials
**Location**: `.env` and various configs
- `GRAFANA_ADMIN_PASSWORD` - Plain text
- Prometheus metrics potentially exposing secrets

#### 6. Configuration String Representations
**Location**: All service configs
- Missing `__str__` and `__repr__` methods
- Default Pydantic behavior exposes all fields in logs

### 🟡 MEDIUM PRIORITY

#### 7. Environment Detection Issues
**[Detailed Task Document: environment-detection-standardization.md](./environment-detection-standardization.md)**
- 8 services use unsafe string comparison: `if self.ENVIRONMENT == "production"`
- Should use `Environment` enum from `common_core.config_enums`
- Identity Service has correct implementation as reference
- **Security Risk**: Typos or case mismatches silently disable production security

#### 8. Secret Management Infrastructure
- No centralized secret management
- Missing rotation mechanisms
- No audit trail for secret access

## Implementation Plan

### Phase 1: Critical Secret Protection (4 hours)

#### 1.1 Create Base Secure Configuration Class
```python
# libs/huleedu_service_libs/src/huleedu_service_libs/config/secure_base.py
from common_core.config_enums import Environment
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings

class SecureServiceSettings(BaseSettings):
    """Base settings with security defaults and shared configuration for all services."""
    
    # Global environment (shared across all services)
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        validation_alias="ENVIRONMENT"  # Read from global ENVIRONMENT var
    )
    
    # Database (all services use same credentials)
    DB_PASSWORD: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="HULEEDU_DB_PASSWORD",  # Read from shared env var
        description="Shared database password"
    )
    
    # Internal API authentication
    INTERNAL_API_KEY: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="HULEEDU_INTERNAL_API_KEY",  # Read from shared env var
        description="Internal service authentication key"
    )
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == Environment.PRODUCTION
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT == Environment.DEVELOPMENT
    
    def is_staging(self) -> bool:
        """Check if running in staging environment."""
        return self.ENVIRONMENT == Environment.STAGING
    
    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.ENVIRONMENT == Environment.TESTING
    
    def requires_security(self) -> bool:
        """Production and staging require full security."""
        return self.ENVIRONMENT in {Environment.PRODUCTION, Environment.STAGING}
    
    def __str__(self) -> str:
        """Secure string representation that masks all secrets."""
        return (
            f"{self.__class__.__name__}("
            f"service={getattr(self, 'SERVICE_NAME', 'unknown')}, "
            f"environment={self.ENVIRONMENT.value}, "
            f"secrets=***MASKED***)"
        )
    
    def __repr__(self) -> str:
        """Secure repr for debugging that masks sensitive data."""
        return self.__str__()
```

**Benefits of this approach:**
- Single source of truth for shared secrets and environment
- All services inherit consistent security configuration
- Environment detection helpers available to all services
- Shared secrets read from common environment variables
- Clean separation between shared and service-specific configuration

#### 1.2 Update LLM Provider Service
- Convert all API keys to `SecretStr`
- Add secure string representation
- Update all `.get_secret_value()` calls
- Test with masked logging

#### 1.3 Update Database Configurations
- Apply `SecretStr` to all DB passwords
- Update connection string builders
- Test database connections

### Phase 2: Service-Wide Security (3 hours)

#### 2.1 Update All Service Configs
Services requiring updates:
- [ ] api_gateway_service
- [ ] batch_conductor_service
- [ ] batch_orchestrator_service
- [ ] class_management_service
- [ ] content_service
- [ ] essay_lifecycle_service
- [ ] file_service
- [ ] llm_provider_service
- [ ] nlp_service
- [ ] result_aggregator_service
- [ ] spell_checker_service
- [ ] websocket_service

For each service:
1. Inherit from `SecureServiceSettings`
2. Convert service-specific secrets to `SecretStr`
3. Add/update `__str__` and `__repr__` methods
4. Update code using secrets to call `.get_secret_value()`

#### 2.2 Fix Environment Detection
- Standardize on `Environment` enum
- Use `.is_production()` helper methods
- Remove string comparisons

### Phase 3: Infrastructure Hardening (2 hours)

#### 3.1 Clean Up Environment Variables
- Remove redundant `HULEEDU_ENVIRONMENT` from .env (keep only `ENVIRONMENT`)
- Ensure all services use `validation_alias="ENVIRONMENT"` for consistent environment detection
- Document that `ENVIRONMENT` is the single source of truth for all services

#### 3.2 Update .gitignore
- Add patterns for all secret files
- Ensure no keys can be committed

#### 3.2 Create Secret Rotation Support
- Add version/rotation fields to configs
- Document rotation procedures
- Implement graceful rotation

#### 3.3 Add Security Monitoring
- Log access to `.get_secret_value()`
- Alert on potential secret exposure
- Add metrics for secret usage

### Phase 4: Testing & Validation (3 hours)

#### 4.1 Security Testing Suite
Create `tests/security/test_secret_masking.py`:
- Test all configs mask secrets
- Verify no secrets in error messages
- Check log output for leaks

#### 4.2 Integration Testing
- Test all services with new configs
- Verify service-to-service auth
- Check database connections

#### 4.3 Production Simulation
- Run with `ENVIRONMENT=production`
- Check all security features active
- Verify no regression in functionality

## Success Criteria

### Must Have (Before Production)
- [ ] All API keys use `SecretStr`
- [ ] All passwords use `SecretStr`
- [ ] All configs have secure `__str__/__repr__`
- [ ] No secrets visible in logs
- [ ] All tests passing with security updates

### Should Have
- [ ] Centralized secure config base class
- [ ] Consistent environment detection
- [ ] Secret rotation mechanism
- [ ] Security test suite

### Nice to Have
- [ ] Secret access auditing
- [ ] Automated secret scanning in CI
- [ ] Key rotation automation

## Testing Checklist

### Unit Tests
- [ ] Each service config masks secrets
- [ ] SecretStr extraction works correctly
- [ ] Environment detection consistent

### Integration Tests
- [ ] Services start with secure configs
- [ ] Database connections work
- [ ] API integrations functional

### Security Tests
- [ ] No secrets in logs
- [ ] No secrets in error messages
- [ ] No secrets in stack traces
- [ ] No secrets in monitoring

## Reference Implementation

The Identity Service provides the gold standard pattern:

```python
# From services/identity_service/config.py
class Settings(BaseSettings):
    JWT_DEV_SECRET: SecretStr = Field(
        default=SecretStr("dev-secret-change-me"),
        description="JWT signing secret"
    )
    
    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"service={self.SERVICE_NAME}, "
            f"environment={self.ENVIRONMENT.value}, "
            f"secrets=***MASKED***)"
        )
```

Usage pattern:
```python
# Accessing secrets
actual_secret = settings.JWT_DEV_SECRET.get_secret_value()
```

## Risks of Not Completing

### Immediate Risks
- **API Key Theft**: Exposed keys in logs could cost $10,000+ in unauthorized usage
- **Data Breach**: Database passwords in logs enable complete data access
- **Compliance Violations**: GDPR/privacy law violations from data exposure
- **Reputation Damage**: Security breach would damage trust irreparably

### Long-term Risks
- **Technical Debt**: Retrofitting security is harder than building it in
- **Audit Failures**: Would fail any security audit
- **Insurance Issues**: Negligent security practices void coverage

## Appendix: Affected Files

### Configuration Files Requiring Updates
```
services/api_gateway_service/config.py
services/batch_conductor_service/config.py
services/batch_orchestrator_service/config.py
services/class_management_service/config.py
services/content_service/config.py
services/essay_lifecycle_service/config.py
services/file_service/config.py
services/llm_provider_service/config.py
services/nlp_service/config.py
services/result_aggregator_service/config.py
services/spell_checker_service/config.py
services/websocket_service/config.py
```

### Implementation Files Requiring Updates
- All files using `settings.<SECRET_FIELD>` must add `.get_secret_value()`
- Database connection builders
- HTTP client initializations with API keys
- Service authentication modules

## Notes

- This task is **CRITICAL** and blocks production deployment
- Security improvements should follow Identity Service patterns exactly
- No backwards compatibility needed - we're still in development
- Test thoroughly - security bugs are worse than feature bugs

## Related Tasks
- [Identity Service Infrastructure Testing](./identity-service-comprehensive-testing.md) - Completed, provides reference patterns

---

**DO NOT DEPLOY TO PRODUCTION WITHOUT COMPLETING THIS TASK**