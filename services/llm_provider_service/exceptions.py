"""Service-specific exceptions for LLM Provider Service."""

from common_core.error_enums import ErrorCode


class LLMProviderServiceError(Exception):
    """Base exception for LLM Provider Service."""

    def __init__(self, message: str, error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR):
        self.error_code = error_code
        super().__init__(message)


class LLMProviderNotFoundError(LLMProviderServiceError):
    """Raised when requested LLM provider is not found."""

    def __init__(self, message: str):
        super().__init__(message, ErrorCode.RESOURCE_NOT_FOUND)


class LLMProviderConfigurationError(LLMProviderServiceError):
    """Raised when LLM provider is misconfigured."""

    def __init__(self, message: str):
        super().__init__(message, ErrorCode.CONFIGURATION_ERROR)


class LLMProviderTimeoutError(LLMProviderServiceError):
    """Raised when LLM provider request times out."""

    def __init__(self, message: str):
        super().__init__(message, ErrorCode.TIMEOUT)


class LLMProviderRateLimitError(LLMProviderServiceError):
    """Raised when LLM provider rate limit is exceeded."""

    def __init__(self, message: str):
        super().__init__(message, ErrorCode.RATE_LIMIT)


class LLMProviderAuthenticationError(LLMProviderServiceError):
    """Raised when LLM provider authentication fails."""

    def __init__(self, message: str):
        super().__init__(message, ErrorCode.AUTHENTICATION_ERROR)


class LLMResponseValidationError(LLMProviderServiceError):
    """Raised when LLM response fails validation."""

    def __init__(self, message: str):
        super().__init__(message, ErrorCode.PARSING_ERROR)


class CacheError(LLMProviderServiceError):
    """Base exception for cache-related errors."""

    def __init__(self, message: str, error_code: ErrorCode = ErrorCode.EXTERNAL_SERVICE_ERROR):
        super().__init__(message, error_code)


class CacheConnectionError(CacheError):
    """Raised when cache connection fails."""

    def __init__(self, message: str):
        super().__init__(message, ErrorCode.CONNECTION_ERROR)


class CircuitBreakerOpenError(LLMProviderServiceError):
    """Raised when circuit breaker is open for a provider."""

    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(message, ErrorCode.CIRCUIT_BREAKER_OPEN)
