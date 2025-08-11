# HuleEdu Frontend Integration Guide

## Overview

This guide provides comprehensive documentation for integrating Svelte/SvelteKit frontends with the HuleEdu API Gateway. It covers authentication patterns, API usage, real-time communication, and best practices.

## Table of Contents

- [Authentication & Authorization](#authentication--authorization)
- [API Client Setup](#api-client-setup)
- [WebSocket Integration](#websocket-integration)
- [File Upload Patterns](#file-upload-patterns)
- [Error Handling](#error-handling)
- [TypeScript Integration](#typescript-integration)

---

## Authentication & Authorization

### JWT Token Management

The HuleEdu API Gateway uses JWT (JSON Web Tokens) for authentication. All API endpoints except `/healthz` and `/v1/test/no-auth` require valid JWT tokens.

#### Token Structure

```typescript
interface JWTToken {
  access_token: string;
  token_type: "Bearer";
  expires_in?: number;
}

interface JWTPayload {
  sub: string;        // User ID (required, non-empty)
  exp: number;        // Expiration timestamp (required)
  iat: number;        // Issued at timestamp
  // Additional claims as needed
}
```

#### Critical Authentication Requirements

Based on the API Gateway implementation:

1. **Bearer Token Format**: Must be `Authorization: Bearer <token>`
2. **Expiration Validation**: Tokens MUST include `exp` claim and be checked client-side
3. **Subject Validation**: Tokens MUST include non-empty `sub` claim for user identification
4. **Algorithm**: Uses HS256 signing algorithm
5. **Correlation ID**: Include `X-Correlation-ID` header for request tracking

#### Authentication Flow

```typescript
// 1. Login/Registration (implement with your auth service)
async function login(credentials: LoginCredentials): Promise<JWTToken> {
  const response = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(credentials)
  });
  
  if (!response.ok) {
    throw new Error('Authentication failed');
  }
  
  return response.json();
}

// 2. Token Storage (recommended: httpOnly cookies for security)
function storeToken(token: JWTToken): void {
  // Option 1: httpOnly cookies (most secure)
  document.cookie = `access_token=${token.access_token}; HttpOnly; Secure; SameSite=Strict`;
  
  // Option 2: localStorage (less secure, but simpler for development)
  localStorage.setItem('access_token', token.access_token);
  localStorage.setItem('token_expires', (Date.now() + (token.expires_in || 3600) * 1000).toString());
}

// 3. Token Retrieval
function getToken(): string | null {
  // From localStorage
  const token = localStorage.getItem('access_token');
  const expires = localStorage.getItem('token_expires');
  
  if (!token || !expires) return null;
  
  // Check expiration
  if (Date.now() > parseInt(expires)) {
    clearToken();
    return null;
  }
  
  return token;
}

// 4. Token Refresh (implement based on your auth strategy)
async function refreshToken(): Promise<JWTToken | null> {
  try {
    const response = await fetch('/auth/refresh', {
      method: 'POST',
      credentials: 'include' // Include httpOnly cookies
    });
    
    if (!response.ok) return null;
    
    const newToken = await response.json();
    storeToken(newToken);
    return newToken;
  } catch {
    return null;
  }
}

// 5. Automatic Token Renewal
class TokenManager {
  private refreshTimer: NodeJS.Timeout | null = null;
  private isRefreshing = false;
  private refreshPromise: Promise<JWTToken | null> | null = null;

  async getValidToken(): Promise<string | null> {
    const token = getToken();
    if (!token) return null;

    // Check if token expires within 5 minutes
    const payload = this.decodeTokenPayload(token);
    if (!payload) return null;

    const expiresIn = payload.exp * 1000 - Date.now();
    const fiveMinutes = 5 * 60 * 1000;

    if (expiresIn < fiveMinutes) {
      return await this.ensureTokenRefresh();
    }

    return token;
  }

  private async ensureTokenRefresh(): Promise<string | null> {
    if (this.isRefreshing && this.refreshPromise) {
      const newToken = await this.refreshPromise;
      return newToken?.access_token || null;
    }

    this.isRefreshing = true;
    this.refreshPromise = refreshToken();

    try {
      const newToken = await this.refreshPromise;
      if (newToken) {
        this.scheduleNextRefresh(newToken);
        return newToken.access_token;
      }
      return null;
    } finally {
      this.isRefreshing = false;
      this.refreshPromise = null;
    }
  }

  private scheduleNextRefresh(token: JWTToken): void {
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
    }

    const expiresIn = (token.expires_in || 3600) * 1000;
    const refreshTime = expiresIn - (10 * 60 * 1000); // Refresh 10 minutes before expiry

    this.refreshTimer = setTimeout(() => {
      this.ensureTokenRefresh();
    }, Math.max(refreshTime, 60000)); // At least 1 minute
  }

  private decodeTokenPayload(token: string): JWTPayload | null {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(
        atob(base64)
          .split('')
          .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join('')
      );
      return JSON.parse(jsonPayload);
    } catch {
      return null;
    }
  }

  cleanup(): void {
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }
  }
}

const tokenManager = new TokenManager();
```

#### Authorization Headers

```typescript
async function createAuthHeaders(correlationId?: string): Promise<AuthHeaders> {
  const token = await tokenManager.getValidToken();
  if (!token) {
    throw new AuthenticationError('No valid authentication token available');
  }
  
  const headers: AuthHeaders = {
    'Authorization': `Bearer ${token}`
  };
  
  if (correlationId) {
    headers['X-Correlation-ID'] = correlationId;
  }
  
  return headers;
}
```

### Role-Based Access Control

#### User Ownership Validation

The API Gateway validates user ownership for batch operations. Frontend applications should implement client-side checks for better UX:

```typescript
interface UserContext {
  userId: string;
  roles?: string[];
  permissions?: string[];
}

class AuthorizationManager {
  private userContext: UserContext | null = null;

  async getCurrentUser(): Promise<UserContext | null> {
    const token = await tokenManager.getValidToken();
    if (!token) return null;

    if (!this.userContext) {
      const payload = this.decodeTokenPayload(token);
      if (payload) {
        this.userContext = {
          userId: payload.sub,
          roles: payload.roles || [],
          permissions: payload.permissions || []
        };
      }
    }

    return this.userContext;
  }

  async canAccessBatch(batchId: string): Promise<boolean> {
    const user = await this.getCurrentUser();
    if (!user) return false;

    // Check if user owns the batch (server-side validation is authoritative)
    try {
      const response = await apiClient.getBatchStatus(batchId);
      return response.success;
    } catch (error) {
      if (error instanceof ApiError && error.statusCode === 403) {
        return false;
      }
      throw error;
    }
  }

  hasRole(role: string): boolean {
    return this.userContext?.roles?.includes(role) || false;
  }

  hasPermission(permission: string): boolean {
    return this.userContext?.permissions?.includes(permission) || false;
  }

  private decodeTokenPayload(token: string): any {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(
        atob(base64)
          .split('')
          .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join('')
      );
      return JSON.parse(jsonPayload);
    } catch {
      return null;
    }
  }

  clearContext(): void {
    this.userContext = null;
  }
}

const authManager = new AuthorizationManager();
```

#### Handling 401/403 Responses

```typescript
class AuthenticationError extends Error {
  constructor(message: string, public shouldRedirectToLogin = true) {
    super(message);
    this.name = 'AuthenticationError';
  }
}

class AuthorizationError extends Error {
  constructor(message: string, public resource?: string) {
    super(message);
    this.name = 'AuthorizationError';
  }
}

function handleAuthError(error: ApiError): never {
  if (error.statusCode === 401) {
    // Clear invalid tokens
    clearToken();
    tokenManager.cleanup();
    authManager.clearContext();
    
    throw new AuthenticationError(
      'Your session has expired. Please log in again.',
      true
    );
  }
  
  if (error.statusCode === 403) {
    throw new AuthorizationError(
      'You do not have permission to access this resource.',
      error.correlationId
    );
  }
  
  throw error;
}
```

---

## API Client Setup

### HTTP Client Configuration

```typescript
import { v4 as uuidv4 } from 'uuid';

class HuleEduApiClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;
  
  constructor(baseUrl: string = 'http://localhost:4001') {
    this.baseUrl = baseUrl;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
  }
  
  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    requireAuth: boolean = true
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;
    const correlationId = uuidv4();
    
    const headers = {
      ...this.defaultHeaders,
      ...options.headers,
    };
    
    if (requireAuth) {
      const authHeaders = createAuthHeaders(correlationId);
      Object.assign(headers, authHeaders);
    }
    
    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });
      
      // Handle rate limiting
      if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After');
        throw new RateLimitError(`Rate limit exceeded. Retry after ${retryAfter} seconds`);
      }
      
      // Handle authentication errors
      if (response.status === 401) {
        // Try to refresh token
        const newToken = await refreshToken();
        if (newToken) {
          // Retry the request with new token
          return this.request(endpoint, options, requireAuth);
        } else {
          // Redirect to login
          window.location.href = '/login';
          throw new AuthenticationError('Authentication required');
        }
      }
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new ApiError(errorData.detail || 'Request failed', response.status, correlationId);
      }
      
      const data = await response.json();
      return { data, success: true };
      
    } catch (error) {
      if (error instanceof ApiError || error instanceof RateLimitError) {
        throw error;
      }
      
      return {
        error: {
          detail: error instanceof Error ? error.message : 'Unknown error',
          correlation_id: correlationId
        },
        success: false
      };
    }
  }
  
  // API Methods
  async getBatchStatus(batchId: string): Promise<ApiResponse<BatchStatusResponse>> {
    return this.request<BatchStatusResponse>(`/v1/batches/${batchId}/status`);
  }
  
  async requestPipeline(batchId: string, request: BatchPipelineRequest): Promise<ApiResponse<void>> {
    return this.request<void>(`/v1/batches/${batchId}/pipelines`, {
      method: 'POST',
      body: JSON.stringify(request)
    });
  }
  
  async uploadFiles(formData: FormData): Promise<ApiResponse<any>> {
    return this.request<any>('/v1/files/batch', {
      method: 'POST',
      body: formData,
      headers: {} // Don't set Content-Type for FormData
    });
  }
}

// Custom Error Classes
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

class RateLimitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RateLimitError';
  }
}

class AuthenticationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AuthenticationError';
  }
}
```

---

## WebSocket Integration

The HuleEdu WebSocket Service provides real-time notifications for teachers. It runs on **port 8081** and requires JWT authentication via query parameter.

### Connection URL

```text
ws://localhost:8081/ws?token=<JWT_TOKEN>
```

### Production-Ready Connection Management

The WebSocket integration requires robust connection management for production applications. This section provides comprehensive patterns for connection establishment, lifecycle management, and error handling.

### TypeScript Interfaces

```typescript
// Core notification structure
interface TeacherNotification {
  teacher_id: string;
  notification_type: NotificationType;
  category: WebSocketEventCategory;
  priority: NotificationPriority;
  payload: Record<string, any>;
  action_required: boolean;
  deadline_timestamp?: string;
  correlation_id: string;
  batch_id?: string;
  class_id?: string;
  timestamp: string;
}

// WebSocket message wrapper
interface WebSocketMessage {
  type: 'teacher_notification';
  data: TeacherNotification;
}

// Event categories
type WebSocketEventCategory = 
  | 'batch_progress'
  | 'processing_results'
  | 'file_operations'
  | 'class_management'
  | 'student_workflow'
  | 'system_alerts';

// Notification priorities
type NotificationPriority = 
  | 'critical'    // Requires action within 24 hours
  | 'immediate'   // Requires prompt attention (errors, failures)
  | 'high'        // Important but not urgent (processing complete)
  | 'standard'    // Normal priority (progress updates)
  | 'low';        // Informational only (status changes)

// All 15+ notification types
type NotificationType =
  // File Operations
  | 'batch_files_uploaded'
  | 'batch_file_removed'
  | 'batch_validation_failed'
  // Batch Processing
  | 'batch_processing_started'
  | 'batch_processing_completed'
  | 'batch_processing_failed'
  // Assessment Results
  | 'batch_results_ready'
  | 'batch_assessment_completed'
  | 'batch_spellcheck_completed'
  | 'batch_cj_assessment_completed'
  // Class Management
  | 'class_created'
  | 'student_added_to_class'
  | 'validation_timeout_processed'
  | 'student_associations_confirmed'
  // Student Workflow
  | 'student_matching_confirmation_required';
```

### Connection Management

```typescript
class HuleEduWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1 second
  private maxReconnectDelay = 30000; // Max 30 seconds
  private messageHandlers = new Map<NotificationType, (notification: TeacherNotification) => void>();
  private categoryHandlers = new Map<WebSocketEventCategory, (notification: TeacherNotification) => void>();
  private priorityHandlers = new Map<NotificationPriority, (notification: TeacherNotification) => void>();
  private connectionState: 'disconnected' | 'connecting' | 'connected' | 'error' = 'disconnected';
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private connectionTimeout: NodeJS.Timeout | null = null;
  private eventEmitter = new EventTarget();
  
  constructor(
    private wsUrl: string = 'ws://localhost:8081',
    private options: {
      maxReconnectAttempts?: number;
      reconnectDelay?: number;
      maxReconnectDelay?: number;
      heartbeatInterval?: number;
      connectionTimeout?: number;
    } = {}
  ) {
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? 5;
    this.reconnectDelay = options.reconnectDelay ?? 1000;
    this.maxReconnectDelay = options.maxReconnectDelay ?? 30000;
  }
  
  async connect(): Promise<void> {
    return new Promise(async (resolve, reject) => {
      // Clear any existing connection
      this.disconnect();
      
      const token = await tokenManager.getValidToken();
      if (!token) {
        reject(new Error('No authentication token available'));
        return;
      }
      
      this.connectionState = 'connecting';
      const wsUrlWithAuth = `${this.wsUrl}/ws?token=${encodeURIComponent(token)}`;
      
      // Set connection timeout
      this.connectionTimeout = setTimeout(() => {
        if (this.connectionState === 'connecting') {
          this.ws?.close();
          reject(new Error('Connection timeout'));
        }
      }, this.options.connectionTimeout ?? 10000);
      
      this.ws = new WebSocket(wsUrlWithAuth);
      
      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.connectionState = 'connected';
        this.reconnectAttempts = 0;
        this.reconnectDelay = this.options.reconnectDelay ?? 1000;
        
        // Clear connection timeout
        if (this.connectionTimeout) {
          clearTimeout(this.connectionTimeout);
          this.connectionTimeout = null;
        }
        
        // Start heartbeat
        this.startHeartbeat();
        
        // Emit connection event
        this.emit('connected', { timestamp: new Date().toISOString() });
        
        resolve();
      };
      
      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };
      
      this.ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        this.connectionState = 'disconnected';
        
        // Stop heartbeat
        this.stopHeartbeat();
        
        // Clear connection timeout
        if (this.connectionTimeout) {
          clearTimeout(this.connectionTimeout);
          this.connectionTimeout = null;
        }
        
        // Emit disconnection event
        this.emit('disconnected', { 
          code: event.code, 
          reason: event.reason,
          timestamp: new Date().toISOString()
        });
        
        // Handle different close codes
        if (event.code === 1008 || event.code === 4001) {
          // Policy violation or authentication error
          try {
            const errorData = JSON.parse(event.reason);
            console.error('WebSocket auth error:', errorData);
            this.connectionState = 'error';
            this.emit('authError', errorData);
            reject(new Error(`Authentication failed: ${errorData.message}`));
          } catch {
            this.attemptReconnect();
          }
        } else if (event.code === 4000) {
          // Connection limit exceeded
          console.error('Connection limit exceeded');
          this.connectionState = 'error';
          this.emit('connectionLimitExceeded', { code: event.code });
        } else if (event.code === 1000 || event.code === 1001) {
          // Normal closure - don't reconnect
          console.log('WebSocket closed normally');
        } else {
          this.attemptReconnect();
        }
      };
      
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.connectionState = 'error';
        reject(error);
      };
    });
  }
  
  private startHeartbeat(): void {
    const interval = this.options.heartbeatInterval ?? 30000; // 30 seconds default
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
  
  private emit(eventType: string, data: any): void {
    const event = new CustomEvent(eventType, { detail: data });
    this.eventEmitter.dispatchEvent(event);
  }
  
  addEventListener(eventType: string, listener: EventListener): void {
    this.eventEmitter.addEventListener(eventType, listener);
  }
  
  removeEventListener(eventType: string, listener: EventListener): void {
    this.eventEmitter.removeEventListener(eventType, listener);
  }
  
  private handleMessage(message: WebSocketMessage): void {
    // Handle pong responses
    if (message.type === 'pong') {
      return; // Heartbeat response, no action needed
    }
    
    if (message.type === 'teacher_notification') {
      const notification = message.data;
      
      // Emit raw message event
      this.emit('message', notification);
      
      // Call specific type handler if registered
      const typeHandler = this.messageHandlers.get(notification.notification_type);
      if (typeHandler) {
        typeHandler(notification);
      }
      
      // Call category handler if registered
      const categoryHandler = this.categoryHandlers.get(notification.category);
      if (categoryHandler) {
        categoryHandler(notification);
      }
      
      // Call priority handler if registered
      const priorityHandler = this.priorityHandlers.get(notification.priority);
      if (priorityHandler) {
        priorityHandler(notification);
      }
      
      // Default notification display (if no specific handlers)
      if (!typeHandler && !categoryHandler && !priorityHandler) {
        this.displayNotification(notification);
      }
    }
  }
  
  private displayNotification(notification: TeacherNotification): void {
    const message = this.formatNotificationMessage(notification);
    
    switch (notification.priority) {
      case 'critical':
        // Show modal with action required
        this.showCriticalAlert(notification, message);
        break;
      case 'immediate':
        // Show urgent toast/banner
        this.showToast(message, 'error', { persistent: true });
        break;
      case 'high':
        // Show prominent toast
        this.showToast(message, 'warning', { duration: 8000 });
        break;
      case 'standard':
        // Show normal toast
        this.showToast(message, 'info', { duration: 5000 });
        break;
      case 'low':
        // Show subtle notification
        this.showToast(message, 'success', { duration: 3000 });
        break;
    }
  }
  
  private formatNotificationMessage(notification: TeacherNotification): string {
    const { notification_type, payload, batch_id, class_id } = notification;
    
    switch (notification_type) {
      // File Operations
      case 'batch_files_uploaded':
        return `Files uploaded successfully for batch ${batch_id} (${payload.file_count} files)`;
      case 'batch_file_removed':
        return `File removed from batch ${batch_id}: ${payload.filename}`;
      case 'batch_validation_failed':
        return `File validation failed for batch ${batch_id}: ${payload.error_message}`;
      
      // Batch Processing
      case 'batch_processing_started':
        return `Processing started for batch ${batch_id} (${payload.pipeline_phase})`;
      case 'batch_processing_completed':
        return `Processing completed for batch ${batch_id}. Results are ready for review.`;
      case 'batch_processing_failed':
        return `Processing failed for batch ${batch_id}: ${payload.error_message}`;
      
      // Assessment Results
      case 'batch_results_ready':
        return `Results are ready for batch ${batch_id}. ${payload.essay_count} essays processed.`;
      case 'batch_assessment_completed':
        return `Assessment completed for batch ${batch_id}. Review the results.`;
      case 'batch_spellcheck_completed':
        return `Spellcheck completed for batch ${batch_id}. ${payload.corrections_count} corrections found.`;
      case 'batch_cj_assessment_completed':
        return `CJ Assessment completed for batch ${batch_id}.`;
      
      // Class Management
      case 'class_created':
        return `New class created: ${payload.class_name} (${payload.student_count} students)`;
      case 'student_added_to_class':
        return `Student ${payload.student_name} added to class ${payload.class_name}`;
      case 'validation_timeout_processed':
        return `Validation timeout processed for class ${class_id}`;
      case 'student_associations_confirmed':
        return `Student associations confirmed for class ${class_id}`;
      
      // Student Workflow
      case 'student_matching_confirmation_required':
        return `Student matching requires your confirmation for batch ${batch_id}`;
      
      default:
        return `Notification: ${notification_type}`;
    }
  }
  
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      this.connectionState = 'error';
      this.emit('maxReconnectAttemptsReached', {
        attempts: this.reconnectAttempts,
        timestamp: new Date().toISOString()
      });
      return;
    }
    
    this.reconnectAttempts++;
    // Exponential backoff with jitter
    const baseDelay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    const jitter = Math.random() * 1000; // Add up to 1 second of jitter
    const delay = Math.min(baseDelay + jitter, this.maxReconnectDelay);
    
    console.log(`Attempting to reconnect in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    this.emit('reconnectAttempt', {
      attempt: this.reconnectAttempts,
      maxAttempts: this.maxReconnectAttempts,
      delay: Math.round(delay),
      timestamp: new Date().toISOString()
    });
    
    setTimeout(() => {
      this.connect().catch((error) => {
        console.error('Reconnection failed:', error);
        this.emit('reconnectFailed', {
          attempt: this.reconnectAttempts,
          error: error.message,
          timestamp: new Date().toISOString()
        });
      });
    }, delay);
  }
  
  // Register notification handlers
  onNotification(type: NotificationType, handler: (notification: TeacherNotification) => void): void {
    this.messageHandlers.set(type, handler);
  }
  
  // Remove notification handler
  offNotification(type: NotificationType): void {
    this.messageHandlers.delete(type);
  }
  
  // Register handlers by category
  onCategory(category: WebSocketEventCategory, handler: (notification: TeacherNotification) => void): void {
    this.categoryHandlers.set(category, handler);
  }
  
  // Remove category handler
  offCategory(category: WebSocketEventCategory): void {
    this.categoryHandlers.delete(category);
  }
  
  // Register handlers by priority
  onPriority(priority: NotificationPriority, handler: (notification: TeacherNotification) => void): void {
    this.priorityHandlers.set(priority, handler);
  }
  
  // Remove priority handler
  offPriority(priority: NotificationPriority): void {
    this.priorityHandlers.delete(priority);
  }
  
  // Clear all handlers
  clearHandlers(): void {
    this.messageHandlers.clear();
    this.categoryHandlers.clear();
    this.priorityHandlers.clear();
  }
  
  getConnectionState(): string {
    return this.connectionState;
  }
  
  disconnect(): void {
    // Stop heartbeat
    this.stopHeartbeat();
    
    // Clear connection timeout
    if (this.connectionTimeout) {
      clearTimeout(this.connectionTimeout);
      this.connectionTimeout = null;
    }
    
    // Close WebSocket connection
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    
    this.connectionState = 'disconnected';
    this.reconnectAttempts = 0;
  }
  
  // Get connection statistics
  getConnectionStats(): {
    state: string;
    reconnectAttempts: number;
    maxReconnectAttempts: number;
    isConnected: boolean;
    hasHandlers: boolean;
  } {
    return {
      state: this.connectionState,
      reconnectAttempts: this.reconnectAttempts,
      maxReconnectAttempts: this.maxReconnectAttempts,
      isConnected: this.connectionState === 'connected',
      hasHandlers: this.messageHandlers.size > 0 || this.categoryHandlers.size > 0 || this.priorityHandlers.size > 0
    };
  }
  
  private showCriticalAlert(notification: TeacherNotification, message: string): void {
    // Show modal for critical notifications that require action
    if (notification.action_required) {
      const deadline = notification.deadline_timestamp ? 
        new Date(notification.deadline_timestamp).toLocaleString() : 'No deadline';
      
      const fullMessage = `${message}\n\nAction Required: Yes\nDeadline: ${deadline}`;
      
      // In a real app, show a proper modal
      if (confirm(`${fullMessage}\n\nWould you like to take action now?`)) {
        // Navigate to appropriate page based on notification type
        this.handleNotificationAction(notification);
      }
    } else {
      alert(message);
    }
  }
  
  private handleNotificationAction(notification: TeacherNotification): void {
    // Navigate to appropriate page based on notification type
    switch (notification.notification_type) {
      case 'student_matching_confirmation_required':
        window.location.href = `/batches/${notification.batch_id}/matching`;
        break;
      case 'batch_results_ready':
        window.location.href = `/batches/${notification.batch_id}/results`;
        break;
      case 'batch_processing_failed':
        window.location.href = `/batches/${notification.batch_id}/status`;
        break;
      default:
        console.log(`No specific action defined for ${notification.notification_type}`);
    }
  }
  
  private showToast(
    message: string, 
    type: 'success' | 'error' | 'warning' | 'info',
    options: { duration?: number; persistent?: boolean } = {}
  ): void {
    // Implement your toast notification system
    const { duration = 5000, persistent = false } = options;
    console.log(`[${type.toUpperCase()}] ${message} (duration: ${persistent ? 'persistent' : duration + 'ms'})`);
    
    // In a real implementation, you'd integrate with your toast library
    // Example with a hypothetical toast library:
    // toast[type](message, { duration: persistent ? 0 : duration });
  }
}
```

### Comprehensive Notification Handling Patterns

Based on the 15 notification types from `TeacherNotificationRequestedV1`, here are production-ready patterns for handling real-time notifications:

#### 2.2.1 WebSocket Connection Management ✅

The above `HuleEduWebSocketClient` provides:
- **Connection establishment with JWT authentication**
- **Reconnection strategies with exponential backoff and jitter**
- **Message parsing and event routing**
- **Connection lifecycle management with heartbeat**

#### 2.2.2 Notification Handling Patterns

```typescript
// Notification Manager for UI Integration
class NotificationManager {
  private notifications: TeacherNotification[] = [];
  private unreadCount = 0;
  private wsClient: HuleEduWebSocketClient;
  
  constructor(wsClient: HuleEduWebSocketClient) {
    this.wsClient = wsClient;
    this.setupNotificationHandlers();
  }
  
  private setupNotificationHandlers(): void {
    // Handle all notifications for storage and UI updates
    this.wsClient.addEventListener('message', (event) => {
      const notification = event.detail as TeacherNotification;
      this.addNotification(notification);
    });
    
    // Priority-based handlers
    this.wsClient.onPriority('critical', (notification) => {
      this.handleCriticalNotification(notification);
    });
    
    this.wsClient.onPriority('immediate', (notification) => {
      this.handleImmediateNotification(notification);
    });
    
    // Category-based handlers
    this.wsClient.onCategory('batch_progress', (notification) => {
      this.updateBatchProgress(notification);
    });
    
    this.wsClient.onCategory('processing_results', (notification) => {
      this.handleProcessingResults(notification);
    });
    
    this.wsClient.onCategory('system_alerts', (notification) => {
      this.handleSystemAlert(notification);
    });
  }
  
  private addNotification(notification: TeacherNotification): void {
    this.notifications.unshift(notification);
    this.unreadCount++;
    
    // Limit stored notifications to prevent memory issues
    if (this.notifications.length > 100) {
      this.notifications = this.notifications.slice(0, 100);
    }
    
    // Emit event for UI updates
    this.emit('notificationAdded', notification);
    this.emit('unreadCountChanged', this.unreadCount);
  }
  
  // Critical notifications require immediate user attention
  private handleCriticalNotification(notification: TeacherNotification): void {
    // Show modal dialog
    this.showModal({
      title: 'Critical Action Required',
      message: this.formatNotificationMessage(notification),
      type: 'error',
      persistent: true,
      actions: [
        {
          label: 'Take Action',
          primary: true,
          onClick: () => this.navigateToAction(notification)
        },
        {
          label: 'Remind Me Later',
          onClick: () => this.scheduleReminder(notification, 30) // 30 minutes
        }
      ]
    });
    
    // Play sound alert
    this.playNotificationSound('critical');
    
    // Show browser notification if permission granted
    this.showBrowserNotification(notification, { requireInteraction: true });
  }
  
  // Immediate notifications need prompt attention but aren't blocking
  private handleImmediateNotification(notification: TeacherNotification): void {
    // Show persistent toast
    this.showToast({
      message: this.formatNotificationMessage(notification),
      type: 'error',
      persistent: true,
      actions: [
        {
          label: 'View',
          onClick: () => this.navigateToAction(notification)
        },
        {
          label: 'Dismiss',
          onClick: () => this.markAsRead(notification.correlation_id)
        }
      ]
    });
    
    // Play sound alert
    this.playNotificationSound('immediate');
    
    // Show browser notification
    this.showBrowserNotification(notification);
  }
  
  // Update batch progress in real-time
  private updateBatchProgress(notification: TeacherNotification): void {
    const { batch_id, notification_type, payload } = notification;
    
    switch (notification_type) {
      case 'batch_processing_started':
        this.emit('batchProgressUpdate', {
          batchId: batch_id,
          status: 'processing',
          phase: payload.pipeline_phase,
          message: `Processing started: ${payload.pipeline_phase}`
        });
        break;
        
      case 'batch_processing_completed':
        this.emit('batchProgressUpdate', {
          batchId: batch_id,
          status: 'completed',
          message: 'Processing completed successfully'
        });
        
        // Show success notification
        this.showToast({
          message: `Batch ${batch_id} processing completed`,
          type: 'success',
          duration: 5000
        });
        break;
        
      case 'batch_processing_failed':
        this.emit('batchProgressUpdate', {
          batchId: batch_id,
          status: 'failed',
          error: payload.error_message,
          message: `Processing failed: ${payload.error_message}`
        });
        break;
    }
  }
  
  // Handle processing results notifications
  private handleProcessingResults(notification: TeacherNotification): void {
    const { notification_type, batch_id, payload } = notification;
    
    switch (notification_type) {
      case 'batch_results_ready':
        // Show prominent notification with action
        this.showToast({
          message: `Results ready for batch ${batch_id} (${payload.essay_count} essays)`,
          type: 'success',
          duration: 8000,
          actions: [
            {
              label: 'View Results',
              primary: true,
              onClick: () => this.navigateToAction(notification)
            }
          ]
        });
        
        // Update batch status in UI
        this.emit('batchResultsReady', {
          batchId: batch_id,
          essayCount: payload.essay_count
        });
        break;
        
      case 'batch_spellcheck_completed':
        this.showToast({
          message: `Spellcheck completed: ${payload.corrections_count} corrections found`,
          type: 'info',
          duration: 5000
        });
        break;
        
      case 'batch_cj_assessment_completed':
        this.showToast({
          message: `Assessment completed for batch ${batch_id}`,
          type: 'info',
          duration: 5000
        });
        break;
    }
  }
  
  // Handle system alerts
  private handleSystemAlert(notification: TeacherNotification): void {
    const { notification_type, payload } = notification;
    
    switch (notification_type) {
      case 'validation_timeout_processed':
        this.showToast({
          message: 'Validation timeout processed - please review results',
          type: 'warning',
          duration: 8000
        });
        break;
        
      default:
        // Generic system alert handling
        this.showToast({
          message: this.formatNotificationMessage(notification),
          type: 'info',
          duration: 5000
        });
    }
  }
  
  // Format notification messages for display - All 15 notification types
  private formatNotificationMessage(notification: TeacherNotification): string {
    const { notification_type, payload, batch_id, class_id } = notification;
    
    switch (notification_type) {
      // File Operations
      case 'batch_files_uploaded':
        return `✅ Files uploaded successfully (${payload.file_count} files)`;
      case 'batch_file_removed':
        return `🗑️ File removed: ${payload.filename}`;
      case 'batch_validation_failed':
        return `❌ File validation failed: ${payload.error_message}`;
      
      // Batch Processing
      case 'batch_processing_started':
        return `🔄 Processing started: ${payload.pipeline_phase}`;
      case 'batch_processing_completed':
        return `✅ Processing completed successfully`;
      case 'batch_processing_failed':
        return `❌ Processing failed: ${payload.error_message}`;
      
      // Assessment Results
      case 'batch_results_ready':
        return `📊 Results ready (${payload.essay_count} essays processed)`;
      case 'batch_assessment_completed':
        return `✅ Assessment completed - review results`;
      case 'batch_spellcheck_completed':
        return `📝 Spellcheck completed (${payload.corrections_count} corrections)`;
      case 'batch_cj_assessment_completed':
        return `🎯 Content judgment assessment completed`;
      
      // Class Management
      case 'class_created':
        return `🏫 New class created: ${payload.class_name} (${payload.student_count} students)`;
      case 'student_added_to_class':
        return `👤 Student added: ${payload.student_name} → ${payload.class_name}`;
      case 'validation_timeout_processed':
        return `⏰ Validation timeout processed - review required`;
      case 'student_associations_confirmed':
        return `✅ Student associations confirmed`;
      
      // Student Workflow
      case 'student_matching_confirmation_required':
        return `🔍 Student matching requires your confirmation`;
      
      default:
        return `📢 ${notification_type.replace(/_/g, ' ')}`;
    }
  }
  
  // Navigation helper for notification actions
  private navigateToAction(notification: TeacherNotification): void {
    const { notification_type, batch_id, class_id } = notification;
    
    const routes: Record<string, string> = {
      'student_matching_confirmation_required': `/batches/${batch_id}/matching`,
      'batch_results_ready': `/batches/${batch_id}/results`,
      'batch_processing_failed': `/batches/${batch_id}/status`,
      'batch_assessment_completed': `/batches/${batch_id}/results`,
      'class_created': `/classes/${class_id}`,
      'student_added_to_class': `/classes/${class_id}/students`,
      'validation_timeout_processed': `/classes/${class_id}/validation`,
      'batch_files_uploaded': `/batches/${batch_id}/files`,
      'batch_validation_failed': `/batches/${batch_id}/files`
    };
    
    const route = routes[notification_type];
    if (route) {
      // Use your router navigation method
      window.location.href = route;
    } else {
      console.warn(`No route defined for notification type: ${notification_type}`);
    }
  }
  
  // Utility methods for UI integration
  getNotifications(): TeacherNotification[] {
    return [...this.notifications];
  }
  
  getUnreadCount(): number {
    return this.unreadCount;
  }
  
  markAsRead(correlationId: string): void {
    const notification = this.notifications.find(n => n.correlation_id === correlationId);
    if (notification && !notification.read) {
      notification.read = true;
      this.unreadCount = Math.max(0, this.unreadCount - 1);
      this.emit('unreadCountChanged', this.unreadCount);
    }
  }
  
  markAllAsRead(): void {
    this.notifications.forEach(n => n.read = true);
    this.unreadCount = 0;
    this.emit('unreadCountChanged', 0);
  }
  
  clearNotifications(): void {
    this.notifications = [];
    this.unreadCount = 0;
    this.emit('notificationsCleared');
    this.emit('unreadCountChanged', 0);
  }
  
  // Event emitter for UI updates
  private eventEmitter = new EventTarget();
  
  private emit(eventType: string, data: any): void {
    const event = new CustomEvent(eventType, { detail: data });
    this.eventEmitter.dispatchEvent(event);
  }
  
  addEventListener(eventType: string, listener: EventListener): void {
    this.eventEmitter.addEventListener(eventType, listener);
  }
  
  removeEventListener(eventType: string, listener: EventListener): void {
    this.eventEmitter.removeEventListener(eventType, listener);
  }
  
  // Placeholder methods for UI integration (implement based on your UI library)
  private showModal(options: any): void {
    console.log('Show modal:', options);
    // Implement with your modal library
  }
  
  private showToast(options: any): void {
    console.log('Show toast:', options);
    // Implement with your toast library
  }
  
  private playNotificationSound(type: string): void {
    console.log('Play sound:', type);
    // Implement sound notifications
  }
  
  private showBrowserNotification(notification: TeacherNotification, options: any = {}): void {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(this.formatNotificationMessage(notification), {
        icon: '/notification-icon.png',
        badge: '/notification-badge.png',
        ...options
      });
    }
  }
  
  private scheduleReminder(notification: TeacherNotification, minutes: number): void {
    setTimeout(() => {
      this.handleCriticalNotification(notification);
    }, minutes * 60 * 1000);
  }
}

// Usage Example: Complete Integration
const wsClient = new HuleEduWebSocketClient();
const notificationManager = new NotificationManager(wsClient);

// Set up UI event listeners
notificationManager.addEventListener('notificationAdded', (event) => {
  const notification = event.detail;
  console.log('New notification:', notification);
  // Update notification badge in UI
});

notificationManager.addEventListener('unreadCountChanged', (event) => {
  const count = event.detail;
  // Update notification badge count
  document.querySelector('.notification-badge')?.textContent = count.toString();
});

notificationManager.addEventListener('batchProgressUpdate', (event) => {
  const progress = event.detail;
  // Update batch progress in UI
  console.log('Batch progress:', progress);
});

// Connect and start receiving notifications
wsClient.connect().then(() => {
  console.log('WebSocket connected and notification manager ready');
}).catch(console.error);
```

### Framework-Specific Integration Examples

#### Svelte 5 Component with WebSocket Notifications

```svelte
<!-- NotificationCenter.svelte -->
<script lang="ts">
  import { wsNotificationManager } from '$lib/stores/websocket.svelte';
  import type { TeacherNotification } from '../types/websocket';
  
  // Component props using $props()
  let { autoConnect = true, wsUrl }: { autoConnect?: boolean; wsUrl?: string } = $props();
  
  // Connect on mount if autoConnect is enabled
  $effect(() => {
    if (autoConnect) {
      wsNotificationManager.connect(wsUrl);
    }
    
    // Cleanup on component destroy
    return () => {
      wsNotificationManager.disconnect();
    };
  });
  
  // Helper functions
  function formatNotificationTime(timestamp: string): string {
    return new Date(timestamp).toLocaleTimeString();
  }
  
  function getNotificationIcon(type: string): string {
    const icons: Record<string, string> = {
      'batch_processing_completed': '✅',
      'batch_processing_failed': '❌',
      'batch_files_uploaded': '📁',
      'student_matching_confirmation_required': '🔍',
      'class_created': '🏫'
    };
    return icons[type] || '📢';
  }
  
  function handleNotificationClick(notification: TeacherNotification): void {
    wsNotificationManager.markAsRead(notification.correlation_id);
    // Navigate to relevant page based on notification type
    if (notification.batch_id) {
      window.location.href = `/batches/${notification.batch_id}`;
    }
  }
</script>

<div class="notification-center">
  <div class="header">
    <h3>Notifications</h3>
    <div class="status">
      <span class="connection-status" class:connected={wsNotificationManager.isConnected}>
        {wsNotificationManager.connectionState}
      </span>
      {#if wsNotificationManager.unreadCount > 0}
        <span class="unread-badge">{wsNotificationManager.unreadCount}</span>
      {/if}
    </div>
  </div>
  
  <div class="notification-list">
    {#each wsNotificationManager.notifications as notification (notification.correlation_id)}
      <div 
        class="notification-item" 
        class:unread={!notification.read}
        class:critical={notification.priority === 'critical'}
        onclick={() => handleNotificationClick(notification)}
      >
        <div class="notification-header">
          <span class="icon">{getNotificationIcon(notification.notification_type)}</span>
          <span class="type">{notification.notification_type.replace(/_/g, ' ')}</span>
          <span class="time">{formatNotificationTime(notification.timestamp)}</span>
        </div>
        
        <div class="notification-content">
          {notification.payload.message || 'Notification received'}
        </div>
        
        {#if notification.action_required}
          <div class="action-required">Action Required</div>
        {/if}
      </div>
    {:else}
      <div class="no-notifications">No notifications</div>
    {/each}
  </div>
  
  <div class="actions">
    <button onclick={() => wsNotificationManager.markAllAsRead()}>
      Mark All Read
    </button>
    <button onclick={() => wsNotificationManager.clearNotifications()}>
      Clear All
    </button>
  </div>
</div>

<style>
  .notification-center {
    max-width: 400px;
    border: 1px solid #ddd;
    border-radius: 8px;
    background: white;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  }
  
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    border-bottom: 1px solid #eee;
  }
  
  .connection-status {
    font-size: 0.8rem;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    background: #dc3545;
    color: white;
  }
  
  .connection-status.connected {
    background: #28a745;
  }
  
  .unread-badge {
    background: #007bff;
    color: white;
    border-radius: 50%;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    margin-left: 0.5rem;
  }
  
  .notification-list {
    max-height: 400px;
    overflow-y: auto;
  }
  
  .notification-item {
    padding: 1rem;
    border-bottom: 1px solid #eee;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  
  .notification-item:hover {
    background: #f8f9fa;
  }
  
  .notification-item.unread {
    background: #fff3cd;
    border-left: 4px solid #ffc107;
  }
  
  .notification-item.critical {
    background: #f8d7da;
    border-left: 4px solid #dc3545;
  }
  
  .notification-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  
  .icon {
    font-size: 1.2rem;
  }
  
  .type {
    font-weight: bold;
    text-transform: capitalize;
    flex: 1;
  }
  
  .time {
    font-size: 0.8rem;
    color: #666;
  }
  
  .action-required {
    margin-top: 0.5rem;
    padding: 0.25rem 0.5rem;
    background: #dc3545;
    color: white;
    border-radius: 4px;
    font-size: 0.8rem;
    display: inline-block;
  }
  
  .no-notifications {
    padding: 2rem;
    text-align: center;
    color: #666;
  }
  
  .actions {
    padding: 1rem;
    border-top: 1px solid #eee;
    display: flex;
    gap: 0.5rem;
  }
  
  .actions button {
    flex: 1;
    padding: 0.5rem;
    border: 1px solid #ddd;
    border-radius: 4px;
    background: white;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  
  .actions button:hover {
    background: #f8f9fa;
  }
</style>
```

#### Svelte 5 WebSocket Manager with Runes

```typescript
// src/lib/stores/websocket.svelte.ts
import type { TeacherNotification } from '../types/websocket';

class WebSocketNotificationManager {
  private ws: WebSocket | null = null;
  private wsClient: HuleEduWebSocketClient | null = null;
  private notificationManager: NotificationManager | null = null;
  
  // Svelte 5 runes for reactive state
  isConnected = $state(false);
  connectionState = $state<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  notifications = $state<TeacherNotification[]>([]);
  
  // Derived state using $derived
  unreadCount = $derived(() => 
    this.notifications.filter(n => !n.read).length
  );
  
  recentNotifications = $derived(() => 
    this.notifications.slice(0, 10)
  );
  
  async connect(wsUrl?: string): Promise<void> {
    try {
      this.wsClient = new HuleEduWebSocketClient(wsUrl);
      this.notificationManager = new NotificationManager(this.wsClient);
      
      // Set up event listeners
      this.wsClient.addEventListener('connected', () => {
        this.isConnected = true;
        this.connectionState = 'connected';
      });
      
      this.wsClient.addEventListener('disconnected', () => {
        this.isConnected = false;
        this.connectionState = 'disconnected';
      });
        
        this.notificationManager.addEventListener('notificationReceived', (event) => {
          const notification = event.detail;
          this.notifications = [notification, ...this.notifications.slice(0, 99)];
        });
        
        await this.wsClient.connect();
      } catch (error) {
        console.error('Failed to connect WebSocket:', error);
        this.connectionState = 'error';
      }
    }
    
    async disconnect(): Promise<void> {
      if (this.wsClient) {
        await this.wsClient.disconnect();
        this.wsClient = null;
        this.notificationManager = null;
      }
      this.isConnected = false;
      this.connectionState = 'disconnected';
    }
  
    markAsRead(correlationId: string): void {
      if (this.notificationManager) {
        this.notificationManager.markAsRead(correlationId);
      }
    }
  
    markAllAsRead(): void {
      if (this.notificationManager) {
        this.notificationManager.markAllAsRead();
      }
    }
  
    clearNotifications(): void {
      if (this.notificationManager) {
        this.notificationManager.clearNotifications();
      }
      this.notifications = [];
    }
}

// Export singleton instance
export const wsNotificationManager = new WebSocketNotificationManager();

---

## File Upload Patterns

### Enhanced File Upload with Progress Tracking

```typescript
interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  speed?: number; // bytes per second
  remainingTime?: number; // seconds
}

interface FileValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

interface UploadOptions {
  maxRetries?: number;
  chunkSize?: number;
  timeout?: number;
  validateBeforeUpload?: boolean;
}

class FileUploadManager {
  private readonly maxFileSize = 10 * 1024 * 1024; // 10MB
  private readonly allowedTypes = [
    'text/plain',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'
  ];
  private readonly allowedExtensions = ['.txt', '.pdf', '.docx', '.doc'];

  async uploadFiles(
    files: File[],
    batchId: string,
    onProgress?: (progress: UploadProgress) => void,
    options: UploadOptions = {}
  ): Promise<ApiResponse<any>> {
    
    const {
      maxRetries = 3,
      timeout = 300000, // 5 minutes
      validateBeforeUpload = true
    } = options;

    // Pre-upload validation
    if (validateBeforeUpload) {
      const validation = this.validateFiles(files);
      if (!validation.isValid) {
        throw new Error(`File validation failed: ${validation.errors.join(', ')}`);
      }
    }

    let attempt = 0;
    let lastError: Error;

    while (attempt <= maxRetries) {
      try {
        return await this.performUpload(files, batchId, onProgress, timeout);
      } catch (error) {
        lastError = error as Error;
        attempt++;
        
        if (attempt <= maxRetries) {
          // Exponential backoff
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 10000);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }

    throw lastError!;
  }

  private async performUpload(
    files: File[],
    batchId: string,
    onProgress?: (progress: UploadProgress) => void,
    timeout: number = 300000
  ): Promise<ApiResponse<any>> {
    
    const formData = new FormData();
    formData.append('batch_id', batchId);
    
    files.forEach(file => {
      formData.append('files', file);
    });

    return new Promise(async (resolve, reject) => {
      const xhr = new XMLHttpRequest();
      let startTime = Date.now();
      let lastLoaded = 0;
      let lastTime = startTime;

      // Set timeout
      xhr.timeout = timeout;

      // Progress tracking with speed calculation
      if (onProgress) {
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            const now = Date.now();
            const timeDiff = (now - lastTime) / 1000; // seconds
            const loadedDiff = event.loaded - lastLoaded;
            
            const speed = timeDiff > 0 ? loadedDiff / timeDiff : 0;
            const remainingBytes = event.total - event.loaded;
            const remainingTime = speed > 0 ? remainingBytes / speed : 0;

            const progress: UploadProgress = {
              loaded: event.loaded,
              total: event.total,
              percentage: Math.round((event.loaded / event.total) * 100),
              speed,
              remainingTime
            };
            
            onProgress(progress);
            
            lastLoaded = event.loaded;
            lastTime = now;
          }
        });
      }

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            resolve({ data: response, success: true });
          } catch {
            resolve({ data: null, success: true });
          }
        } else {
          let errorDetail = `Upload failed with status ${xhr.status}`;
          try {
            const errorResponse = JSON.parse(xhr.responseText);
            errorDetail = errorResponse.detail || errorDetail;
          } catch {
            // Use default error message
          }
          
          const error = {
            detail: errorDetail,
            status_code: xhr.status
          };
          resolve({ error, success: false });
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Upload failed due to network error'));
      });

      xhr.addEventListener('timeout', () => {
        reject(new Error('Upload timed out'));
      });

      xhr.addEventListener('abort', () => {
        reject(new Error('Upload was aborted'));
      });

      // Set headers with authentication
      try {
        const headers = await createAuthHeaders();
        Object.entries(headers).forEach(([key, value]) => {
          if (key !== 'Content-Type') { // Let browser set Content-Type for FormData
            xhr.setRequestHeader(key, value);
          }
        });
      } catch (error) {
        reject(error);
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
      return { isValid: false, errors, warnings };
    }

    if (files.length > 50) {
      errors.push('Too many files. Maximum 50 files allowed per batch');
    }

    files.forEach((file, index) => {
      const fileNumber = index + 1;
      
      // Size validation
      if (file.size === 0) {
        errors.push(`File ${fileNumber} (${file.name}) is empty`);
      } else if (file.size > this.maxFileSize) {
        errors.push(`File ${fileNumber} (${file.name}) exceeds maximum size of 10MB`);
      }

      // Type validation
      const isValidType = this.allowedTypes.includes(file.type);
      const hasValidExtension = this.allowedExtensions.some(ext => 
        file.name.toLowerCase().endsWith(ext)
      );

      if (!isValidType && !hasValidExtension) {
        errors.push(`File ${fileNumber} (${file.name}) has unsupported type: ${file.type}`);
      } else if (!isValidType && hasValidExtension) {
        warnings.push(`File ${fileNumber} (${file.name}) has unexpected MIME type but valid extension`);
      }

      // Name validation
      if (file.name.length > 255) {
        errors.push(`File ${fileNumber} name is too long (max 255 characters)`);
      }

      if (!/^[a-zA-Z0-9._\-\s]+$/.test(file.name)) {
        warnings.push(`File ${fileNumber} (${file.name}) contains special characters that may cause issues`);
      }
    });

    // Check for duplicate names
    const names = files.map(f => f.name.toLowerCase());
    const duplicates = names.filter((name, index) => names.indexOf(name) !== index);
    if (duplicates.length > 0) {
      errors.push(`Duplicate file names detected: ${[...new Set(duplicates)].join(', ')}`);
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings
    };
  }

  // Client-side file preview generation
  async generatePreview(file: File): Promise<string | null> {
    if (file.type.startsWith('image/')) {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target?.result as string);
        reader.onerror = () => resolve(null);
        reader.readAsDataURL(file);
      });
    }

    if (file.type === 'text/plain') {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          const text = e.target?.result as string;
          resolve(text.substring(0, 500) + (text.length > 500 ? '...' : ''));
        };
        reader.onerror = () => resolve(null);
        reader.readAsText(file);
      });
    }

    return null; // No preview available for this file type
  }

  // Utility method to format file sizes
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  // Utility method to format upload speed
  formatSpeed(bytesPerSecond: number): string {
    return this.formatFileSize(bytesPerSecond) + '/s';
  }

  // Utility method to format remaining time
  formatTime(seconds: number): string {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
  }
}
```

---

## Error Handling & Resilience

### Comprehensive Error Handling Strategy

```typescript
// Enhanced error types
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

// Enhanced error handling with comprehensive retry logic
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

  // Parse API error responses
  static parseApiError(response: Response, correlationId?: string): Error {
    const statusCode = response.status;

    if (statusCode === 401) {
      return new AuthenticationError('Authentication required');
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

// Offline detection and handling
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
}

const offlineManager = new OfflineManager();

// Circuit breaker pattern for failing services
class CircuitBreaker {
  private failures = 0;
  private lastFailureTime = 0;
  private state: 'CLOSED' | 'OPEN' | 'HALF_OPEN' = 'CLOSED';

  constructor(
    private failureThreshold: number = 5,
    private recoveryTimeout: number = 60000, // 1 minute
    private monitoringPeriod: number = 300000 // 5 minutes
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

  get status(): { state: string; failures: number } {
    return {
      state: this.state,
      failures: this.failures
    };
  }
}

// React Error Boundary for API errors
class ApiErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error?: ApiError }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  
  static getDerivedStateFromError(error: Error) {
    return { 
      hasError: true, 
      error: error instanceof ApiError ? error : new ApiError(error.message)
    };
  }
  
  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('API Error caught by boundary:', error, errorInfo);
    
    // Log to monitoring service
    if (error instanceof ApiError && error.correlationId) {
      console.log(`Correlation ID: ${error.correlationId}`);
    }
  }
  
  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h2>Something went wrong</h2>
          <p>{this.state.error?.message}</p>
          {this.state.error?.correlationId && (
            <p>Error ID: {this.state.error.correlationId}</p>
          )}
          <button onClick={() => this.setState({ hasError: false, error: undefined })}>
            Try again
          </button>
        </div>
      );
    }
    
    return this.props.children;
  }
}
```

---

## TypeScript Integration

### Using Generated Types

```typescript
// Import generated types
import {
  BatchStatusResponse,
  BatchPipelineRequest,
  TeacherNotification,
  ApiResponse,
  AuthHeaders
} from '../docs/api-types';

// Example React component using the API client
const BatchStatusComponent: React.FC<{ batchId: string }> = ({ batchId }) => {
  const [status, setStatus] = useState<BatchStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const apiClient = new HuleEduApiClient();
  
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        setLoading(true);
        const response = await ApiErrorHandler.withRetry(
          () => apiClient.getBatchStatus(batchId)
        );
        
        if (response.success && response.data) {
          setStatus(response.data);
        } else {
          setError(response.error?.detail || 'Failed to fetch status');
        }
      } catch (err) {
        const apiError = ApiErrorHandler.handleError(err);
        setError(apiError.message);
      } finally {
        setLoading(false);
      }
    };
    
    fetchStatus();
  }, [batchId]);
  
  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!status) return <div>No status available</div>;
  
  return (
    <div>
      <h3>Batch Status</h3>
      <p>Status: {status.status}</p>
      <pre>{JSON.stringify(status.details, null, 2)}</pre>
    </div>
  );
};
```

---

## Development Setup

### Environment Configuration

```typescript
// config/api.ts
export const API_CONFIG = {
  development: {
    apiBaseUrl: 'http://localhost:4001',
    wsBaseUrl: 'ws://localhost:8081',
    enableLogging: true,
  },
  production: {
    apiBaseUrl: process.env.REACT_APP_API_BASE_URL || 'https://api.huledu.com',
    wsBaseUrl: process.env.REACT_APP_WS_BASE_URL || 'wss://ws.huledu.com',
    enableLogging: false,
  }
};

export const getApiConfig = () => {
  const env = process.env.NODE_ENV || 'development';
  return API_CONFIG[env as keyof typeof API_CONFIG];
};
```

### CORS Configuration

The API Gateway is configured with CORS support for development:

- `http://localhost:3000` (Create React App default)
- `http://localhost:5173` (Vite default)
- `http://localhost:4173` (Vite preview)

For production, configure the `API_GATEWAY_CORS_ORIGINS` environment variable.

---

## Best Practices

1. **Always use correlation IDs** for request tracking and debugging
2. **Implement proper error boundaries** to catch and handle API errors gracefully
3. **Use exponential backoff** for retry logic on transient failures
4. **Store JWT tokens securely** (prefer httpOnly cookies over localStorage)
5. **Implement token refresh** to maintain user sessions
6. **Handle rate limiting** with appropriate retry strategies
7. **Use TypeScript types** for all API interactions to ensure type safety
8. **Implement proper loading states** for better user experience
9. **Log correlation IDs** for debugging and support purposes
10. **Test WebSocket reconnection** scenarios in your application

---

## Support

For issues or questions:

- Check correlation IDs in error responses for debugging
- Review the OpenAPI specification at `/docs` endpoint
- Consult the generated TypeScript types in `docs/api-types.ts`
- Monitor health endpoints for service status
