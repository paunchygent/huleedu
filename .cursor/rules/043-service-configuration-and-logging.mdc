---
description: Defines configuration management and logging standards for all services.
globs: 
alwaysApply: false
---
# 043: Service Configuration and Logging

## 1. Purpose
Defines configuration management and logging standards for all services.

**See also**: [040-service-implementation-guidelines.mdc](mdc:040-service-implementation-guidelines.mdc) for core stack requirements.

## 2. Configuration Management

### 2.1. Standardized Pydantic Settings Pattern
- **MUST** use `pydantic-settings` for all service configuration
- **MUST** create `config.py` at service root with this pattern:

```python
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Configuration settings for the [Service Name]."""
    LOG_LEVEL: str = "INFO"
    # Add typed fields with defaults
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="[SERVICE_NAME]_",
    )

settings = Settings()
```

### 2.2. Configuration Usage
- Import settings: `from .config import settings`
- Use `settings.FIELD_NAME` instead of `os.getenv()`
- Sensitive info **MUST NEVER** be hardcoded

### 2.3. DATABASE_URL Naming Standards
- **MANDATORY**: Database configuration **MUST** use UPPERCASE `DATABASE_URL` pattern
- **Environment Variables**: `DATABASE_URL`, `SERVICE_DATABASE_URL`, `DATABASE_URL_CJ`
- **Settings Access**: `settings.DATABASE_URL` (not `settings.database_url`)
- **Code Examples**: `create_async_engine(settings.DATABASE_URL)`

**Correct Pattern**:
```python
class Settings(BaseSettings):
    # Environment-aware DATABASE_URL property (preferred)
    @property
    def DATABASE_URL(self) -> str:
        if self.ENVIRONMENT == "production":
            # Production: External database
            return f"postgresql+asyncpg://{user}:{password}@{prod_host}:{port}/{db_name}"
        else:
            # Development: Docker container
            return f"postgresql+asyncpg://{user}:{password}@localhost:{port}/{db_name}"
    
    # Simple string field (for services without environment separation)
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/db"
```

**Anti-Patterns**:
```python
# ❌ FORBIDDEN - Lowercase field names
database_url: str  # Wrong - use DATABASE_URL

# ❌ FORBIDDEN - Missing settings prefix
create_async_engine(DATABASE_URL)  # Wrong - use settings.DATABASE_URL

# ❌ FORBIDDEN - Mixed case
Database_URL: str  # Wrong - use DATABASE_URL
```

## 3. Logging

### 3.1. Centralized Logging Utility
- **MUST** use `huleedu_service_libs.logging_utils` for all logging
- **FORBIDDEN**: Standard library `logging` module in services
- **Pattern**:
```python
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

# Service initialization
configure_service_logging("service-name", log_level=settings.LOG_LEVEL)
logger = create_service_logger("component-name")
```

### 3.2. Mandatory Correlation IDs
- For any operation chain (request/event), a `correlation_id` **MUST** be established or propagated
- This `correlation_id` **MUST** be in all log messages across all involved services
- Use `log_event_processing()` for EventEnvelope processing

### 3.3. CorrelationContext Middleware (Quart)
- **Purpose**: Normalize inbound correlation to a canonical `UUID` while preserving the original string for logs and responses
- **Library**: `huleedu_service_libs.error_handling.correlation`
- **Middleware**: `setup_correlation_middleware(app)` attaches `g.correlation_context`

```python
# app.py
from huleedu_service_libs.middleware.frameworks.quart_correlation_middleware import (
    setup_correlation_middleware,
)

setup_correlation_middleware(app)  # call early in app setup
```

```python
# CorrelationContext
from huleedu_service_libs.error_handling.correlation import CorrelationContext

ctx: CorrelationContext = g.correlation_context
ctx.original  # original header/query value (str)
ctx.uuid      # canonical UUID (parsed or uuid5 of original)
```

### 3.4. Correlation in Errors + Events
- **Error factories**: Pass `ctx.uuid` to `correlation_id`; include `original_correlation_id=ctx.original` in details
- **Success responses**: Echo `ctx.original` back to clients
- **Events**: Use `ctx.uuid` for `envelope.correlation_id`; optionally include `original_correlation_id` in metadata

### 3.3. Consistent Log Levels & Clear Messages
- Use appropriate levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- Log messages **MUST** be clear, concise, and contextual
