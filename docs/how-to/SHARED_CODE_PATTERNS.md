# Shared Code Patterns Reference

Canonical implementations of common patterns used across HuleEdu frontend integration. Reference this file instead of duplicating code across documentation.

## Table of Contents
- [Authentication Patterns](#authentication-patterns)
- [API Client Implementations](#api-client-implementations)  
- [WebSocket Connection Management](#websocket-connection-management)
- [File Upload Patterns](#file-upload-patterns)
- [Error Handling & Retry Logic](#error-handling--retry-logic)
- [Utility Functions](#utility-functions)

---

## Authentication Patterns

### JWT Token Management
```typescript
// Standard JWT token interface
interface JWTToken {
  access_token: string;
  token_type: "Bearer";
  expires_in?: number;
}

interface JWTPayload {
  sub: string;        // User ID (required)
  exp: number;        // Expiration timestamp (required)  
  iat: number;        // Issued at timestamp
  roles?: string[];   // User roles
}

// Token storage utilities
class TokenManager {
  private static readonly TOKEN_KEY = 'huledu_access_token';
  
  static store(token: string): void {
    // For production: use httpOnly cookies
    localStorage.setItem(this.TOKEN_KEY, token);
  }
  
  static retrieve(): string | null {
    return localStorage.getItem(this.TOKEN_KEY);
  }
  
  static clear(): void {
    localStorage.removeItem(this.TOKEN_KEY);
  }
  
  static isExpired(token: string): boolean {
    try {
      const payload = JSON.parse(atob(token.split('.')[1])) as JWTPayload;
      return payload.exp * 1000 < Date.now();
    } catch {
      return true;
    }
  }
}
```

### Authentication Headers
```typescript
// Standard auth headers generation
async function createAuthHeaders(): Promise<Record<string, string>> {
  const token = TokenManager.retrieve();
  
  if (!token || TokenManager.isExpired(token)) {
    throw new Error('No valid authentication token');
  }
  
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json',
    'X-Correlation-ID': crypto.randomUUID()
  };
}
```

---

## API Client Implementations

### Base API Client
```typescript
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    message: string;
    detail?: string;
    statusCode?: number;
    correlationId?: string;
  };
}

class BaseApiClient {
  constructor(protected baseUrl: string = 'http://localhost:4001/v1') {}

  protected async request<T>(
    endpoint: string, 
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      const headers = await createAuthHeaders();
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers: { ...headers, ...options.headers }
      });

      const data = response.ok ? await response.json() : null;
      const correlationId = response.headers.get('X-Correlation-ID') || undefined;

      if (!response.ok) {
        return {
          success: false,
          error: {
            message: `Request failed: ${response.status}`,
            statusCode: response.status,
            correlationId
          }
        };
      }

      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: {
          message: error instanceof Error ? error.message : 'Unknown error'
        }
      };
    }
  }
}
```

### Authentication Client
```typescript
class AuthClient extends BaseApiClient {
  async login(credentials: { email: string; password: string }): Promise<ApiResponse<JWTToken>> {
    return this.request<JWTToken>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials)
    });
  }

  async refresh(): Promise<ApiResponse<JWTToken>> {
    return this.request<JWTToken>('/auth/refresh', { method: 'POST' });
  }

  async logout(): Promise<ApiResponse<void>> {
    const result = await this.request<void>('/auth/logout', { method: 'POST' });
    TokenManager.clear();
    return result;
  }
}
```

### Batch Management Client
```typescript
interface BatchCreateRequest {
  file_count: number;
  title?: string;
  description?: string;
  class_id?: string;
}

interface BatchStatusResponse {
  batch_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  details: {
    progress?: { percentage: number; phase: string };
    files_processed?: number;
    total_files?: number;
    error_details?: string;
  };
}

class BatchClient extends BaseApiClient {
  async createBatch(request: BatchCreateRequest): Promise<ApiResponse<{ batch_id: string }>> {
    return this.request('/batches', {
      method: 'POST',
      body: JSON.stringify(request)
    });
  }

  async getBatchStatus(batchId: string): Promise<ApiResponse<BatchStatusResponse>> {
    return this.request(`/batches/${batchId}/status`);
  }

  async processBatch(batchId: string): Promise<ApiResponse<void>> {
    return this.request(`/batches/${batchId}/process`, { method: 'POST' });
  }
}
```

---

## WebSocket Connection Management

### WebSocket Client with Reconnection
```typescript
interface WebSocketConfig {
  maxReconnectAttempts?: number;
  reconnectDelay?: number;
  maxReconnectDelay?: number;
  heartbeatInterval?: number;
}

class HuleEduWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private connectionState: 'disconnected' | 'connecting' | 'connected' | 'error' = 'disconnected';
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private eventHandlers = new Map<string, Array<(data: any) => void>>();
  
  constructor(
    private token: string,
    private config: WebSocketConfig = {}
  ) {}

  async connect(): Promise<void> {
    if (this.connectionState === 'connected') return;
    
    this.connectionState = 'connecting';
    const wsUrl = `ws://localhost:8080/ws?token=${encodeURIComponent(this.token)}`;
    
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(wsUrl);
      
      this.ws.onopen = () => {
        this.connectionState = 'connected';
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        this.emit('connected', { timestamp: new Date().toISOString() });
        resolve();
      };
      
      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.emit('message', message);
          this.emit(message.type || message.notification_type, message);
        } catch (error) {
          console.error('WebSocket message parse error:', error);
        }
      };
      
      this.ws.onclose = (event) => {
        this.connectionState = 'disconnected';
        this.stopHeartbeat();
        this.emit('disconnected', event);
        
        if (event.code !== 1000 && event.code !== 1001) {
          this.attemptReconnect();
        }
      };
      
      this.ws.onerror = (error) => {
        this.connectionState = 'error';
        this.emit('error', error);
        reject(error);
      };
    });
  }

  private attemptReconnect(): void {
    const maxAttempts = this.config.maxReconnectAttempts ?? 5;
    if (this.reconnectAttempts >= maxAttempts) {
      this.emit('maxReconnectAttemptsReached', { attempts: this.reconnectAttempts });
      return;
    }
    
    this.reconnectAttempts++;
    const baseDelay = (this.config.reconnectDelay ?? 1000) * Math.pow(2, this.reconnectAttempts - 1);
    const jitter = Math.random() * 1000;
    const delay = Math.min(baseDelay + jitter, this.config.maxReconnectDelay ?? 30000);
    
    setTimeout(() => {
      this.connect().catch(() => this.attemptReconnect());
    }, delay);
  }

  private startHeartbeat(): void {
    const interval = this.config.heartbeatInterval ?? 30000;
    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, interval);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  disconnect(): void {
    this.stopHeartbeat();
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    this.connectionState = 'disconnected';
  }

  on(eventType: string, handler: (data: any) => void): void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, []);
    }
    this.eventHandlers.get(eventType)!.push(handler);
  }

  private emit(eventType: string, data: any): void {
    const handlers = this.eventHandlers.get(eventType) || [];
    handlers.forEach(handler => handler(data));
  }

  getConnectionState(): string {
    return this.connectionState;
  }
}
```

---

## File Upload Patterns

### File Upload Manager with Progress
```typescript
interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  speed?: number;
  remainingTime?: number;
}

interface FileValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

class FileUploadManager {
  private readonly maxFileSize = 10 * 1024 * 1024; // 10MB
  private readonly allowedTypes = [
    'text/plain',
    'application/pdf', 
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'
  ];
  private readonly maxFiles = 50;

  async uploadFiles(
    files: File[],
    batchId: string,
    onProgress?: (progress: UploadProgress) => void
  ): Promise<ApiResponse<any>> {
    // Validate files first
    const validation = this.validateFiles(files);
    if (!validation.isValid) {
      return {
        success: false,
        error: { message: `Validation failed: ${validation.errors.join(', ')}` }
      };
    }

    const formData = new FormData();
    formData.append('batch_id', batchId);
    files.forEach(file => formData.append('files', file));

    return new Promise(async (resolve) => {
      const xhr = new XMLHttpRequest();
      let startTime = Date.now();
      let lastLoaded = 0;
      let lastTime = startTime;

      // Track progress
      if (onProgress) {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            const now = Date.now();
            const timeDiff = (now - lastTime) / 1000;
            const loadedDiff = event.loaded - lastLoaded;
            
            const speed = timeDiff > 0 ? loadedDiff / timeDiff : 0;
            const remainingBytes = event.total - event.loaded;
            const remainingTime = speed > 0 ? remainingBytes / speed : 0;

            onProgress({
              loaded: event.loaded,
              total: event.total,
              percentage: Math.round((event.loaded / event.total) * 100),
              speed,
              remainingTime
            });
            
            lastLoaded = event.loaded;
            lastTime = now;
          }
        });
      }

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve({ success: true, data: JSON.parse(xhr.responseText) });
          } catch {
            resolve({ success: true, data: null });
          }
        } else {
          resolve({
            success: false,
            error: {
              message: `Upload failed with status ${xhr.status}`,
              statusCode: xhr.status
            }
          });
        }
      });

      xhr.addEventListener('error', () => {
        resolve({
          success: false,
          error: { message: 'Upload failed due to network error' }
        });
      });

      // Set headers and send
      try {
        const headers = await createAuthHeaders();
        Object.entries(headers).forEach(([key, value]) => {
          if (key !== 'Content-Type') { // Let browser set Content-Type for FormData
            xhr.setRequestHeader(key, value);
          }
        });
      } catch (error) {
        resolve({
          success: false,
          error: { message: 'Authentication failed' }
        });
        return;
      }

      xhr.open('POST', 'http://localhost:4001/v1/files/batch');
      xhr.send(formData);
    });
  }

  validateFiles(files: File[]): FileValidationResult {
    const errors: string[] = [];
    const warnings: string[] = [];

    if (files.length === 0) {
      errors.push('No files selected');
    } else if (files.length > this.maxFiles) {
      errors.push(`Too many files. Maximum ${this.maxFiles} files allowed`);
    }

    files.forEach((file, index) => {
      const fileNumber = index + 1;
      
      if (file.size === 0) {
        errors.push(`File ${fileNumber} (${file.name}) is empty`);
      } else if (file.size > this.maxFileSize) {
        errors.push(`File ${fileNumber} (${file.name}) exceeds maximum size`);
      }

      if (!this.allowedTypes.includes(file.type)) {
        errors.push(`File ${fileNumber} (${file.name}) has unsupported type: ${file.type}`);
      }
    });

    return { isValid: errors.length === 0, errors, warnings };
  }
}
```

---

## Error Handling & Retry Logic

### Retry with Exponential Backoff
```typescript
interface RetryOptions {
  maxAttempts?: number;
  baseDelay?: number;
  maxDelay?: number;
  retryCondition?: (error: Error) => boolean;
}

class RetryHandler {
  static async withRetry<T>(
    operation: () => Promise<T>,
    options: RetryOptions = {}
  ): Promise<T> {
    const {
      maxAttempts = 3,
      baseDelay = 1000,
      maxDelay = 30000,
      retryCondition = this.defaultRetryCondition
    } = options;

    let lastError: Error;
    
    for (let attempt = 0; attempt <= maxAttempts; attempt++) {
      try {
        return await operation();
      } catch (error) {
        lastError = error as Error;
        
        if (attempt === maxAttempts || !retryCondition(lastError)) {
          break;
        }
        
        // Exponential backoff with jitter
        const delay = Math.min(
          baseDelay * Math.pow(2, attempt) + Math.random() * 1000,
          maxDelay
        );
        
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
    
    throw lastError!;
  }

  private static defaultRetryCondition(error: Error): boolean {
    // Retry on network errors and 5xx status codes
    const retryableMessages = [
      'fetch failed',
      'network error',
      'timeout',
      'server error'
    ];
    
    return retryableMessages.some(msg => 
      error.message.toLowerCase().includes(msg)
    );
  }
}
```

### Circuit Breaker Pattern
```typescript
class CircuitBreaker {
  private failures = 0;
  private lastFailureTime = 0;
  private state: 'CLOSED' | 'OPEN' | 'HALF_OPEN' = 'CLOSED';

  constructor(
    private failureThreshold: number = 5,
    private recoveryTimeout: number = 60000
  ) {}

  async execute<T>(operation: () => Promise<T>): Promise<T> {
    if (this.state === 'OPEN') {
      if (Date.now() - this.lastFailureTime > this.recoveryTimeout) {
        this.state = 'HALF_OPEN';
      } else {
        throw new Error('Circuit breaker is OPEN');
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
}
```

---

## Utility Functions

### File Size Formatting
```typescript
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}
```

### Time Formatting
```typescript
function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}
```

### Correlation ID Generation
```typescript
function generateCorrelationId(): string {
  return crypto.randomUUID();
}
```

### URL Utilities
```typescript
function buildApiUrl(baseUrl: string, endpoint: string, params?: Record<string, string>): string {
  const url = new URL(endpoint, baseUrl);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      url.searchParams.append(key, value);
    });
  }
  return url.toString();
}
```

---

## Usage Guidelines

### Import Patterns
```typescript
// Import specific patterns as needed
import { BaseApiClient, AuthClient, BatchClient } from './shared-code-patterns';
import { HuleEduWebSocketClient } from './shared-code-patterns'; 
import { FileUploadManager } from './shared-code-patterns';
import { RetryHandler, CircuitBreaker } from './shared-code-patterns';
```

### Extension Patterns
```typescript
// Extend base classes for specific needs
class CustomApiClient extends BaseApiClient {
  async customMethod() {
    return this.request('/custom-endpoint');
  }
}

// Compose utilities
const apiClientWithRetry = {
  async request(endpoint: string, options: RequestInit = {}) {
    return RetryHandler.withRetry(
      () => baseClient.request(endpoint, options),
      { maxAttempts: 5 }
    );
  }
};
```

This reference eliminates the need to duplicate common patterns across documentation files. Always link to specific sections instead of copying code.
