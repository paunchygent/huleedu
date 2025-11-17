# HuleEdu Service Library Middleware

This directory contains middleware implementations for adding cross-cutting concerns like distributed tracing to HuleEdu services.

## Architecture

The middleware is organized in a framework-agnostic way:

```
middleware/
├── __init__.py                    # Framework-agnostic entry point
├── frameworks/                    # Framework-specific implementations
│   ├── __init__.py
│   ├── quart_middleware.py       # Quart/async implementation
│   └── fastapi_middleware.py     # FastAPI/Starlette implementation
└── README.md                     # This file
```

## Usage

### For Quart Services

```python
from huleedu_service_libs import init_tracing
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware

# In your startup_setup.py
async def initialize_services(app: Quart, settings: Settings) -> None:
    # Initialize tracing
    app.tracer = init_tracing("your_service_name")
    setup_tracing_middleware(app, app.tracer)
```

### For FastAPI Services

```python
from huleedu_service_libs import init_tracing
from huleedu_service_libs.middleware.frameworks.fastapi_middleware import setup_tracing_middleware

# In your startup function
def setup_observability(app: FastAPI) -> None:
    # Initialize tracer
    tracer = init_tracing("your_service_name")
    
    # Store tracer in app state if needed
    app.state.tracer = tracer
    
    # Setup automatic HTTP request tracing
    setup_tracing_middleware(app, tracer)
```

## Benefits of This Pattern

1. **Framework Independence**: The service library doesn't force any framework dependencies
2. **Explicit Imports**: Services explicitly import what they need, making dependencies clear
3. **Easy Extension**: New frameworks can be added without modifying existing code
4. **Zero Cognitive Load**: Services using different frameworks don't pay for unused dependencies
5. **Future-Proof**: Services can add observability when ready without library changes

## Adding Support for New Frameworks

To add support for a new framework:

1. Create a new file in `middleware/frameworks/` (e.g., `aiohttp_middleware.py`)
2. Implement the framework-specific middleware following the same pattern
3. Document the usage in this README
4. Services can immediately start using it with explicit imports

## Common Interface

All middleware implementations follow these patterns:

1. A `TracingMiddleware` class that integrates with the framework
2. A `setup_tracing_middleware(app, tracer)` convenience function
3. Automatic span creation for HTTP requests
4. Trace context propagation via headers
5. Error handling and status code mapping

The specific implementation details vary by framework, but the high-level API remains consistent.
