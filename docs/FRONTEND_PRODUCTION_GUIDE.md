# Frontend Production Integration Guide

Production-ready error handling, resilience patterns, circuit breakers, and offline handling for HuleEdu frontend applications.

## Overview

This guide covers advanced patterns for production deployment including comprehensive error handling, retry strategies, circuit breakers, offline support, and monitoring integration.

## Error Types & Classification

```typescript
// Enhanced error types with metadata
class NetworkError extends Error {
  constructor(message: string, public isOffline: boolean = false) {
    super(message);
    this.name = 'NetworkError';
  }
}

class RateLimitError extends Error {
  constructor(
    message: string,
    public retryAfter?: number,
    public correlationId?: string
  ) {
    super(message);
    this.name = 'RateLimitError';
  }
}

class ValidationError extends Error {
  constructor(
    message: string,
    public field?: string,
    public correlationId?: string
  ) {
    super(message);
    this.name = 'ValidationError';
  }
}

class AuthenticationError extends Error {
  constructor(message: string, public correlationId?: string) {
    super(message);
    this.name = 'AuthenticationError';
  }
}

class AuthorizationError extends Error {
  constructor(message: string, public correlationId?: string) {
    super(message);
    this.name = 'AuthorizationError';
  }
}

class ApiError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public correlationId?: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
```

## Retry Logic & Error Handler

Production-grade retry mechanism with exponential backoff and intelligent error classification.

```typescript
class ApiErrorHandler {
  private static readonly RETRY_STATUS_CODES = [408, 429, 500, 502, 503, 504];
  private static readonly MAX_RETRY_DELAY = 30000; // 30 seconds
  
  static async withRetry<T>(
    operation: () => Promise<T>,
    options: {
      maxRetries?: number;
      baseDelay?: number;
      maxDelay?: number;
      retryCondition?: (error: Error) => boolean;
      onRetry?: (attempt: number, error: Error) => void;
    } = {}
  ): Promise<T> {
    const {
      maxRetries = 3,
      baseDelay = 1000,
      maxDelay = this.MAX_RETRY_DELAY,
      retryCondition = this.defaultRetryCondition,
      onRetry
    } = options;

    let lastError: Error;
    
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await operation();
      } catch (error) {
        lastError = error as Error;
        
        // Don't retry if condition fails
        if (!retryCondition(lastError)) {
          throw lastError;
        }
        
        if (attempt === maxRetries) {
          break;
        }

        // Handle rate limiting with server-specified delay
        if (lastError instanceof RateLimitError && lastError.retryAfter) {
          const delay = Math.min(lastError.retryAfter * 1000, maxDelay);
          onRetry?.(attempt + 1, lastError);
          await new Promise(resolve => setTimeout(resolve, delay));
          continue;
        }
        
        // Exponential backoff with jitter
        const exponentialDelay = baseDelay * Math.pow(2, attempt);
        const jitter = Math.random() * 1000;
        const delay = Math.min(exponentialDelay + jitter, maxDelay);
        
        onRetry?.(attempt + 1, lastError);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
    
    throw lastError!;
  }

  private static defaultRetryCondition(error: Error): boolean {
    // Don't retry authentication/authorization errors
    if (error instanceof AuthenticationError || error instanceof AuthorizationError) {
      return false;
    }

    // Don't retry validation errors
    if (error instanceof ValidationError) {
      return false;
    }

    // Retry network errors
    if (error instanceof NetworkError) {
      return true;
    }

    // Retry rate limit errors
    if (error instanceof RateLimitError) {
      return true;
    }

    // Retry specific HTTP status codes
    if (error instanceof ApiError && error.statusCode) {
      return this.RETRY_STATUS_CODES.includes(error.statusCode);
    }

    return false;
  }
  
  static handleError(error: unknown): Error {
    if (error instanceof Error) {
      return error;
    }
    
    return new ApiError('An unknown error occurred');
  }

  // Parse API error responses with correlation ID propagation
  static parseApiError(response: Response, correlationId?: string): Error {
    const statusCode = response.status;

    if (statusCode === 401) {
      return new AuthenticationError('Authentication required', correlationId);
    }

    if (statusCode === 403) {
      return new AuthorizationError('Access forbidden', correlationId);
    }

    if (statusCode === 429) {
      const retryAfter = response.headers.get('Retry-After');
      return new RateLimitError(
        'Rate limit exceeded',
        retryAfter ? parseInt(retryAfter) : undefined,
        correlationId
      );
    }

    if (statusCode >= 400 && statusCode < 500) {
      return new ValidationError('Client error', undefined, correlationId);
    }

    if (statusCode >= 500) {
      return new ApiError('Server error', statusCode, correlationId);
    }

    return new ApiError(`HTTP ${statusCode}`, statusCode, correlationId);
  }
}
```

## Circuit Breaker Pattern

Prevent cascading failures by temporarily disabling failing services.

```typescript
class CircuitBreaker {
  private failures = 0;
  private lastFailureTime = 0;
  private state: 'CLOSED' | 'OPEN' | 'HALF_OPEN' = 'CLOSED';

  constructor(
    private failureThreshold: number = 5,
    private recoveryTimeout: number = 60000, // 1 minute
    private monitoringWindow: number = 300000 // 5 minutes
  ) {}

  async execute<T>(operation: () => Promise<T>): Promise<T> {
    if (this.state === 'OPEN') {
      if (Date.now() - this.lastFailureTime > this.recoveryTimeout) {
        this.state = 'HALF_OPEN';
      } else {
        throw new Error('Circuit breaker is OPEN - service unavailable');
      }
    }

    try {
      const result = await operation();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private onSuccess(): void {
    this.failures = 0;
    this.state = 'CLOSED';
  }

  private onFailure(): void {
    this.failures++;
    this.lastFailureTime = Date.now();

    if (this.failures >= this.failureThreshold) {
      this.state = 'OPEN';
    }
  }

  getState(): string {
    return this.state;
  }

  getFailureCount(): number {
    return this.failures;
  }

  reset(): void {
    this.failures = 0;
    this.state = 'CLOSED';
    this.lastFailureTime = 0;
  }
}
```

## Offline Support

Handle network connectivity issues with request queuing and automatic retry.

```typescript
class OfflineManager {
  private isOnline = navigator.onLine;
  private listeners: Array<(online: boolean) => void> = [];
  private queuedRequests: Array<() => Promise<any>> = [];

  constructor() {
    window.addEventListener('online', () => {
      this.isOnline = true;
      this.notifyListeners(true);
      this.processQueuedRequests();
    });

    window.addEventListener('offline', () => {
      this.isOnline = false;
      this.notifyListeners(false);
    });
  }

  onStatusChange(callback: (online: boolean) => void): () => void {
    this.listeners.push(callback);
    return () => {
      const index = this.listeners.indexOf(callback);
      if (index > -1) {
        this.listeners.splice(index, 1);
      }
    };
  }

  private notifyListeners(online: boolean): void {
    this.listeners.forEach(callback => callback(online));
  }

  private async processQueuedRequests(): Promise<void> {
    const requests = [...this.queuedRequests];
    this.queuedRequests = [];

    for (const request of requests) {
      try {
        await request();
      } catch (error) {
        console.error('Failed to process queued request:', error);
        // Re-queue failed requests
        this.queuedRequests.push(request);
      }
    }
  }

  queueRequest(request: () => Promise<any>): void {
    if (this.isOnline) {
      request().catch(console.error);
    } else {
      this.queuedRequests.push(request);
    }
  }

  get online(): boolean {
    return this.isOnline;
  }

  get queueSize(): number {
    return this.queuedRequests.length;
  }

  clearQueue(): void {
    this.queuedRequests = [];
  }
}

export const offlineManager = new OfflineManager();
```

## Svelte 5 Production Store

Comprehensive error handling and resilience patterns integrated with Svelte 5 reactivity.

```typescript
// lib/stores/production.svelte.ts
import { ApiErrorHandler, CircuitBreaker, offlineManager } from '../utils/resilience';

class ProductionStore {
  // Reactive state using $state()
  isOnline = $state(navigator.onLine);
  errors = $state<Error[]>([]);
  retryAttempts = $state<Map<string, number>>(new Map());
  circuitBreakerStates = $state<Map<string, string>>(new Map());
  
  // Circuit breakers for different services
  private circuitBreakers = new Map<string, CircuitBreaker>();
  
  // Derived state using $derived()
  hasErrors = $derived(this.errors.length > 0);
  criticalErrors = $derived(
    this.errors.filter(e => 
      e instanceof AuthenticationError || 
      e instanceof AuthorizationError
    )
  );
  networkErrors = $derived(
    this.errors.filter(e => e instanceof NetworkError)
  );
  
  constructor() {
    this.setupOfflineHandling();
    this.initializeCircuitBreakers();
  }
  
  private setupOfflineHandling(): void {
    offlineManager.onStatusChange((online) => {
      this.isOnline = online;
    });
  }
  
  private initializeCircuitBreakers(): void {
    // Initialize circuit breakers for different services
    const services = ['api', 'websocket', 'upload'];
    services.forEach(service => {
      const breaker = new CircuitBreaker(5, 60000, 300000);
      this.circuitBreakers.set(service, breaker);
      this.circuitBreakerStates.set(service, breaker.getState());
    });
  }
  
  async executeWithResilience<T>(
    operation: () => Promise<T>,
    options: {
      service?: string;
      maxRetries?: number;
      onRetry?: (attempt: number, error: Error) => void;
    } = {}
  ): Promise<T> {
    const { service = 'api', maxRetries = 3, onRetry } = options;
    const operationId = `${service}-${Date.now()}`;
    
    try {
      // Get circuit breaker for service
      const circuitBreaker = this.circuitBreakers.get(service);
      
      const resilientOperation = async () => {
        if (circuitBreaker) {
          return await circuitBreaker.execute(operation);
        }
        return await operation();
      };
      
      // Execute with retry logic
      const result = await ApiErrorHandler.withRetry(resilientOperation, {
        maxRetries,
        onRetry: (attempt, error) => {
          this.retryAttempts.set(operationId, attempt);
          onRetry?.(attempt, error);
        }
      });
      
      // Clear retry attempts on success
      this.retryAttempts.delete(operationId);
      
      // Update circuit breaker state
      if (circuitBreaker) {
        this.circuitBreakerStates.set(service, circuitBreaker.getState());
      }
      
      return result;
      
    } catch (error) {
      const handledError = ApiErrorHandler.handleError(error);
      this.addError(handledError);
      
      // Update circuit breaker state
      const circuitBreaker = this.circuitBreakers.get(service);
      if (circuitBreaker) {
        this.circuitBreakerStates.set(service, circuitBreaker.getState());
      }
      
      throw handledError;
    }
  }
  
  private addError(error: Error): void {
    this.errors = [error, ...this.errors.slice(0, 49)]; // Keep last 50 errors
  }
  
  clearErrors(): void {
    this.errors = [];
  }
  
  removeError(index: number): void {
    this.errors = this.errors.filter((_, i) => i !== index);
  }
  
  resetCircuitBreaker(service: string): void {
    const breaker = this.circuitBreakers.get(service);
    if (breaker) {
      breaker.reset();
      this.circuitBreakerStates.set(service, breaker.getState());
    }
  }
  
  getServiceHealth(): Record<string, any> {
    const health: Record<string, any> = {};
    
    this.circuitBreakers.forEach((breaker, service) => {
      health[service] = {
        state: breaker.getState(),
        failures: breaker.getFailureCount(),
        healthy: breaker.getState() === 'CLOSED'
      };
    });
    
    return health;
  }
}

export const productionStore = new ProductionStore();
```

## Error Boundary Component

Svelte 5 error boundary for graceful error handling in UI components.

```svelte
<!-- ErrorBoundary.svelte -->
<script lang="ts">
  import { productionStore } from '$lib/stores/production.svelte';
  
  const { 
    children,
    fallback,
    onError 
  }: {
    children: any;
    fallback?: any;
    onError?: (error: Error) => void;
  } = $props();
  
  let hasError = $state(false);
  let error = $state<Error | null>(null);
  
  function handleError(err: Error): void {
    hasError = true;
    error = err;
    onError?.(err);
    productionStore.addError(err);
  }
  
  function retry(): void {
    hasError = false;
    error = null;
  }
  
  // Monitor for critical errors
  $effect(() => {
    if (productionStore.criticalErrors.length > 0) {
      const criticalError = productionStore.criticalErrors[0];
      handleError(criticalError);
    }
  });
</script>

{#if hasError}
  {#if fallback}
    {@render fallback({ error, retry })}
  {:else}
    <div class="error-boundary">
      <div class="error-content">
        <h3>⚠️ Something went wrong</h3>
        <p class="error-message">{error?.message || 'An unexpected error occurred'}</p>
        
        {#if error instanceof AuthenticationError}
          <p class="error-hint">Please log in again to continue.</p>
          <button onclick={() => window.location.href = '/login'}>
            Go to Login
          </button>
        {:else if error instanceof NetworkError}
          <p class="error-hint">Check your internet connection and try again.</p>
          <button onclick={retry}>Retry</button>
        {:else}
          <button onclick={retry}>Try Again</button>
        {/if}
      </div>
    </div>
  {/if}
{:else}
  {@render children()}
{/if}

<style>
  .error-boundary {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 200px;
    padding: 2rem;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 8px;
  }
  
  .error-content {
    text-align: center;
    max-width: 400px;
  }
  
  .error-content h3 {
    color: #dc2626;
    margin-bottom: 1rem;
  }
  
  .error-message {
    color: #374151;
    margin-bottom: 0.5rem;
  }
  
  .error-hint {
    color: #6b7280;
    font-size: 0.875rem;
    margin-bottom: 1rem;
  }
  
  button {
    background: #3b82f6;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.875rem;
  }
  
  button:hover {
    background: #2563eb;
  }
</style>
```

## Usage Examples

### API Client with Full Resilience

```typescript
// Enhanced API client with all production patterns
class ProductionApiClient {
  private baseUrl: string;
  private circuitBreaker: CircuitBreaker;
  
  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    this.circuitBreaker = new CircuitBreaker(5, 60000);
  }
  
  async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    return await productionStore.executeWithResilience(
      async () => {
        const response = await fetch(`${this.baseUrl}${endpoint}`, {
          ...options,
          headers: {
            ...await createAuthHeaders(),
            ...options.headers
          }
        });
        
        if (!response.ok) {
          throw ApiErrorHandler.parseApiError(response);
        }
        
        return await response.json();
      },
      {
        service: 'api',
        maxRetries: 3,
        onRetry: (attempt, error) => {
          console.log(`Retry attempt ${attempt} for ${endpoint}:`, error.message);
        }
      }
    );
  }
}
```

### Component with Error Handling

```svelte
<script lang="ts">
  import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';
  import { productionStore } from '$lib/stores/production.svelte';
  
  const apiClient = new ProductionApiClient('http://localhost:4001');
  
  let data = $state(null);
  let loading = $state(false);
  
  async function loadData(): Promise<void> {
    loading = true;
    try {
      data = await apiClient.request('/v1/batches');
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      loading = false;
    }
  }
  
  // Load data on mount
  $effect(() => {
    loadData();
  });
</script>

<ErrorBoundary onError={(error) => console.error('Component error:', error)}>
  <div class="dashboard">
    <div class="status-bar">
      <span class="connection-status" class:offline={!productionStore.isOnline}>
        {productionStore.isOnline ? 'Online' : 'Offline'}
      </span>
      
      {#if productionStore.hasErrors}
        <span class="error-count">{productionStore.errors.length} errors</span>
      {/if}
    </div>
    
    {#if loading}
      <div class="loading">Loading...</div>
    {:else if data}
      <div class="content">
        <!-- Your content here -->
      </div>
    {:else}
      <div class="no-data">No data available</div>
    {/if}
  </div>
</ErrorBoundary>
```

## Production Considerations

### Monitoring & Observability
- Error tracking with correlation IDs
- Circuit breaker state monitoring
- Retry attempt metrics
- Offline queue size tracking

### Performance
- Exponential backoff prevents server overload
- Circuit breakers prevent cascading failures
- Request queuing during offline periods
- Memory-efficient error storage (50 error limit)

### Security
- Authentication error handling
- Authorization error classification
- Correlation ID propagation for audit trails
- Secure error message sanitization

### Reliability
- Network error detection and handling
- Rate limit respect with server-specified delays
- Graceful degradation during service failures
- Automatic recovery mechanisms
