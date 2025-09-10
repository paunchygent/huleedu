# TASK-052E — NLP Client Integration & Resilience

## Objective

Replace the `LanguageToolServiceClient` skeleton with a production HTTP client that calls Language Tool Service, maps results to enhanced `GrammarError`, and adds resilience with CircuitBreaker and retry patterns.

## Boundary Objects & Contracts

### Client Interface
```python
async def check_grammar(
    text: str, 
    http_session: ClientSession, 
    correlation_id: UUID, 
    language: str = "auto"
) -> GrammarAnalysis
```

### HTTP API Contract
- **Endpoint**: `POST http://language_tool_service:8085/v1/check`
- **Request**: `GrammarCheckRequest` from `common_core.api_models.language_tool`
- **Response**: `GrammarCheckResponse` with serialized `GrammarError` objects
- **Headers**: 
  - `X-Correlation-ID: str(correlation_id)` (required)
  - `Content-Type: application/json`
- **Timeout**: 30 seconds (`aiohttp.ClientTimeout(total=30)`)

### Event Integration
- `EssayNlpCompletedV1` includes `GrammarAnalysis` field
- Processing metadata can include `grammar_category_counts` and `grammar_rule_counts`

## Shared Libraries

- `aiohttp.ClientSession` with `ClientTimeout`
- `huleedu_service_libs.resilience.CircuitBreaker`
- `huleedu_service_libs.error_handling.factories.raise_external_service_error`
- `huleedu_service_libs.logging_utils.create_service_logger`

## Detailed Implementation Steps

### 1. Fix Configuration (config.py)
```python
# Update default port from 8080 to 8085
LANGUAGE_TOOL_SERVICE_URL: str = Field(
    default="http://language_tool_service:8085",  # Fix port
    description="Language Tool Service URL for grammar checking",
)

# Add circuit breaker settings
LANGUAGE_TOOL_CIRCUIT_BREAKER_ENABLED: bool = True
LANGUAGE_TOOL_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
LANGUAGE_TOOL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30  # seconds
LANGUAGE_TOOL_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = 2
LANGUAGE_TOOL_REQUEST_TIMEOUT: int = 30  # seconds
LANGUAGE_TOOL_MAX_RETRIES: int = 3
LANGUAGE_TOOL_RETRY_DELAY: float = 0.5  # seconds (exponential backoff base)
```

### 2. Update DI Provider (di.py)
```python
@provide(scope=Scope.APP)
def provide_language_tool_client(
    self,
    settings: Settings,
) -> LanguageToolClientProtocol:
    """Provide Language Tool Service client with optional circuit breaker."""
    client = LanguageToolServiceClient(settings.LANGUAGE_TOOL_SERVICE_URL)
    
    if settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_ENABLED:
        from huleedu_service_libs.resilience import CircuitBreaker
        from datetime import timedelta
        
        circuit_breaker = CircuitBreaker(
            name="language_tool_service",
            failure_threshold=settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=timedelta(
                seconds=settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_RECOVERY_TIMEOUT
            ),
            success_threshold=settings.LANGUAGE_TOOL_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
            expected_exception=HuleEduError,
        )
        # Wrap client methods with circuit breaker
        client._circuit_breaker = circuit_breaker
    
    return client
```

### 3. Implement HTTP Client (language_tool_client_impl.py)

#### Core HTTP Logic
```python
async def _make_request(
    self,
    text: str,
    http_session: aiohttp.ClientSession,
    correlation_id: UUID,
    language: str,
) -> dict:
    """Make HTTP request to Language Tool Service."""
    url = f"{self.service_url}/v1/check"
    
    # Map language format if needed
    if language == "auto":
        request_language = "auto"
    elif language in ["en", "sv"]:
        # Convert to full format expected by service
        request_language = f"{language}-{language.upper()}"
    else:
        request_language = language
    
    payload = {
        "text": text,
        "language": request_language,
    }
    
    headers = {
        "X-Correlation-ID": str(correlation_id),
        "Content-Type": "application/json",
    }
    
    async with http_session.post(
        url,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=self.timeout_seconds),
    ) as response:
        response_text = await response.text()
        
        if response.status != 200:
            raise_external_service_error(
                service="nlp_service",
                operation="check_grammar",
                external_service="language_tool_service",
                message=f"Language Tool Service returned {response.status}: {response_text}",
                correlation_id=correlation_id,
                status_code=response.status,
            )
        
        return await response.json()
```

#### Retry Logic with Exponential Backoff
```python
async def _with_retry(self, func, *args, **kwargs):
    """Execute function with retry logic."""
    last_error = None
    
    for attempt in range(self.max_retries):
        try:
            return await func(*args, **kwargs)
        except HuleEduError as e:
            last_error = e
            # Don't retry on 4xx errors (client errors)
            if hasattr(e.detail, 'details') and \
               e.detail.details.get('status_code', 500) < 500:
                raise
            
            if attempt < self.max_retries - 1:
                delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"Retry {attempt + 1}/{self.max_retries} after {delay}s",
                    extra={"error": str(e)}
                )
                await asyncio.sleep(delay)
            else:
                raise
    
    raise last_error
```

#### Response Mapping
```python
def _map_response_to_grammar_analysis(
    self, 
    response_data: dict,
    processing_time_ms: int,
) -> GrammarAnalysis:
    """Map HTTP response to GrammarAnalysis model."""
    errors = []
    
    for error_dict in response_data.get("errors", []):
        # Map to GrammarError with all required fields
        grammar_error = GrammarError(
            rule_id=error_dict.get("rule_id", ""),
            message=error_dict.get("message", ""),
            short_message=error_dict.get("short_message", ""),
            offset=error_dict.get("offset", 0),
            length=error_dict.get("length", 0),
            replacements=error_dict.get("replacements", []),
            category=error_dict.get("category", "unknown"),
            severity=error_dict.get("severity", "info"),
            # Enhanced fields (required by TASK-052A)
            category_id=error_dict.get("category_id", "UNKNOWN"),
            category_name=error_dict.get("category_name", "Unknown"),
            context=error_dict.get("context", ""),
            context_offset=error_dict.get("context_offset", 0),
        )
        errors.append(grammar_error)
    
    return GrammarAnalysis(
        error_count=response_data.get("total_grammar_errors", len(errors)),
        errors=errors,
        language=response_data.get("language", "unknown"),
        processing_time_ms=processing_time_ms,
        # Optional: Store category/rule counts for analytics
        grammar_category_counts=response_data.get("grammar_category_counts"),
        grammar_rule_counts=response_data.get("grammar_rule_counts"),
    )
```

#### Circuit Breaker Integration
```python
async def check_grammar(self, ...) -> GrammarAnalysis:
    """Check grammar with circuit breaker protection."""
    try:
        if hasattr(self, '_circuit_breaker'):
            # Use circuit breaker if configured
            response_data = await self._circuit_breaker.call(
                self._with_retry,
                self._make_request,
                text, http_session, correlation_id, language
            )
        else:
            # Direct call with retry
            response_data = await self._with_retry(
                self._make_request,
                text, http_session, correlation_id, language
            )
        
        return self._map_response_to_grammar_analysis(
            response_data, 
            int((time.time() - start_time) * 1000)
        )
        
    except CircuitBreakerError as e:
        # Circuit is open - degrade gracefully
        logger.warning(
            f"Circuit breaker open for Language Tool Service: {str(e)}",
            extra={"correlation_id": str(correlation_id)}
        )
        return self._empty_grammar_analysis(language)
    
    except Exception as e:
        # Other failures - degrade gracefully
        logger.error(
            f"Failed to check grammar: {str(e)}",
            extra={"correlation_id": str(correlation_id)}
        )
        return self._empty_grammar_analysis(language)

def _empty_grammar_analysis(self, language: str) -> GrammarAnalysis:
    """Return empty analysis for graceful degradation."""
    return GrammarAnalysis(
        error_count=0,
        errors=[],
        language=language if language != "auto" else "en",
        processing_time_ms=0,
    )
```

### 4. Error Handling Strategy

- **2xx**: Success - process normally
- **4xx**: Client errors - don't retry, raise immediately
- **5xx**: Server errors - retry with exponential backoff
- **Timeout**: Retry up to max_retries
- **Circuit Open**: Return empty GrammarAnalysis immediately
- **Connection Error**: Retry, then degrade gracefully

## Acceptance Tests

### Unit Tests
```python
# test_language_tool_client_unit.py
- test_successful_grammar_check
- test_empty_text_handling  
- test_language_mapping (en -> en-US, sv -> sv-SE)
- test_response_mapping_with_all_fields
- test_4xx_error_no_retry
- test_5xx_error_with_retry
- test_timeout_with_retry
- test_circuit_breaker_open_degradation
- test_empty_response_handling
```

### Integration Tests
```python
# test_language_tool_client_integration.py
- test_real_http_call_success
- test_circuit_breaker_trips_after_failures
- test_circuit_breaker_recovery
- test_concurrent_requests_during_circuit_open
- test_handler_continues_on_grammar_service_failure
```

## Deliverables

1. **Updated Files**:
   - `services/nlp_service/implementations/language_tool_client_impl.py` - Full HTTP implementation
   - `services/nlp_service/config.py` - Add circuit breaker and retry settings
   - `services/nlp_service/di.py` - Add circuit breaker wrapping

2. **New Test Files**:
   - `services/nlp_service/tests/unit/test_language_tool_client.py`
   - `services/nlp_service/tests/integration/test_language_tool_resilience.py`

3. **Documentation**:
   - Update service README with Language Tool integration details
   - Document circuit breaker thresholds and behavior

