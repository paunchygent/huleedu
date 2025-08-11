# Frontend API Reference

Comprehensive TypeScript types, interfaces, and API documentation for HuleEdu frontend integration.

## Core Types

### Authentication Types

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
  roles?: string[];   // User roles
  permissions?: string[]; // User permissions
}

interface AuthHeaders {
  'Authorization': string;
  'X-Correlation-ID'?: string;
  'Content-Type'?: string;
}

interface LoginCredentials {
  email: string;
  password: string;
}

interface UserContext {
  userId: string;
  roles?: string[];
  permissions?: string[];
}
```

### API Response Types

```typescript
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: ApiError;
  correlationId?: string;
}

interface ApiError {
  message: string;
  detail?: string;
  statusCode: number;
  correlationId?: string;
  timestamp: string;
}

interface ValidationError {
  field: string;
  message: string;
  code: string;
}

interface ErrorResponse {
  error: {
    message: string;
    detail?: string;
    validation_errors?: ValidationError[];
  };
  correlation_id: string;
  timestamp: string;
}
```

### Batch Management Types

```typescript
interface Batch {
  id: string;
  status: BatchStatus;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  user_id: string;
  file_count: number;
  current_phase?: string;
  error_message?: string;
  progress?: BatchProgress;
}

type BatchStatus = 'pending' | 'processing' | 'completed' | 'failed';

interface BatchProgress {
  current_step: number;
  total_steps: number;
  percentage: number;
  phase: string;
  estimated_completion?: string;
}

interface BatchStatusResponse {
  batch_id: string;
  status: BatchStatus;
  details: {
    progress?: BatchProgress;
    files_processed?: number;
    total_files?: number;
    error_details?: string;
  };
}

interface BatchPipelineRequest {
  batch_id: string;
  pipeline_config?: {
    enable_ocr?: boolean;
    quality_threshold?: number;
    output_format?: 'json' | 'csv' | 'xlsx';
  };
}

interface BatchCreateRequest {
  file_count: number;
  title?: string;
  description?: string;
  class_id?: string;
  due_date?: string;
}
```

### File Upload Types

```typescript
interface FileUploadRequest {
  batch_id: string;
  files: File[];
}

interface FileUploadResponse {
  success: boolean;
  uploaded_files: UploadedFile[];
  failed_files: FailedFile[];
  batch_id: string;
}

interface UploadedFile {
  filename: string;
  size: number;
  content_type: string;
  upload_url?: string;
  file_id: string;
}

interface FailedFile {
  filename: string;
  error: string;
  reason: 'size_exceeded' | 'invalid_type' | 'upload_failed' | 'validation_error';
}

interface FileValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
  file: File;
}

interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  speed?: number; // bytes per second
  remainingTime?: number; // seconds
  file?: File;
}
```

### WebSocket Types

```typescript
interface WebSocketMessage {
  type: 'notification' | 'heartbeat' | 'error' | 'connection_ack';
  data?: any;
  timestamp: string;
  correlation_id?: string;
}

interface TeacherNotification {
  notification_id: string;
  notification_type: NotificationType;
  category: WebSocketEventCategory;
  priority: NotificationPriority;
  title: string;
  message: string;
  timestamp: string;
  batch_id?: string;
  file_id?: string;
  user_id: string;
  payload?: NotificationPayload;
  read: boolean;
  expires_at?: string;
}

type NotificationType = 
  | 'batch_processing_started'
  | 'batch_processing_completed' 
  | 'batch_processing_failed'
  | 'batch_processing_progress'
  | 'file_upload_completed'
  | 'file_upload_failed'
  | 'file_processing_started'
  | 'file_processing_completed'
  | 'file_processing_failed'
  | 'assessment_results_ready'
  | 'assessment_results_failed'
  | 'class_assignment_created'
  | 'class_assignment_updated'
  | 'student_submission_received'
  | 'system_maintenance_scheduled';

type WebSocketEventCategory = 
  | 'batch_progress'
  | 'processing_results'
  | 'file_operations'
  | 'class_management'
  | 'student_workflow'
  | 'system_alerts';

type NotificationPriority = 'critical' | 'immediate' | 'high' | 'standard' | 'low';

interface NotificationPayload {
  batch_id?: string;
  file_id?: string;
  progress_percentage?: number;
  pipeline_phase?: string;
  error_message?: string;
  results_url?: string;
  class_id?: string;
  assignment_id?: string;
  student_id?: string;
  maintenance_window?: {
    start_time: string;
    end_time: string;
    affected_services: string[];
  };
}
```

### Error Types

```typescript
class NetworkError extends Error {
  constructor(
    message: string,
    public originalError?: Error,
    public correlationId?: string
  ) {
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
    public validationErrors: ValidationError[],
    public correlationId?: string
  ) {
    super(message);
    this.name = 'ValidationError';
  }
}

class AuthenticationError extends Error {
  constructor(
    message: string,
    public shouldRedirectToLogin = true,
    public correlationId?: string
  ) {
    super(message);
    this.name = 'AuthenticationError';
  }
}

class AuthorizationError extends Error {
  constructor(
    message: string,
    public resource?: string,
    public correlationId?: string
  ) {
    super(message);
    this.name = 'AuthorizationError';
  }
}

class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public detail?: string,
    public correlationId?: string,
    public validationErrors?: ValidationError[]
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
```

## API Endpoints

### Authentication Endpoints

```typescript
interface AuthEndpoints {
  // POST /auth/login
  login(credentials: LoginCredentials): Promise<ApiResponse<JWTToken>>;
  
  // POST /auth/refresh
  refresh(): Promise<ApiResponse<JWTToken>>;
  
  // POST /auth/logout
  logout(): Promise<ApiResponse<void>>;
  
  // GET /auth/profile
  getProfile(): Promise<ApiResponse<UserContext>>;
}
```

### Batch Management Endpoints

```typescript
interface BatchEndpoints {
  // GET /api/v1/batches
  getBatches(): Promise<ApiResponse<Batch[]>>;
  
  // POST /api/v1/batches
  createBatch(request: BatchCreateRequest): Promise<ApiResponse<Batch>>;
  
  // GET /api/v1/batches/{batch_id}
  getBatch(batchId: string): Promise<ApiResponse<Batch>>;
  
  // GET /api/v1/batches/{batch_id}/status
  getBatchStatus(batchId: string): Promise<ApiResponse<BatchStatusResponse>>;
  
  // POST /api/v1/batches/{batch_id}/process
  processBatch(batchId: string, request?: BatchPipelineRequest): Promise<ApiResponse<void>>;
  
  // DELETE /api/v1/batches/{batch_id}
  deleteBatch(batchId: string): Promise<ApiResponse<void>>;
}
```

### File Upload Endpoints

```typescript
interface FileUploadEndpoints {
  // POST /api/v1/files/upload
  uploadFiles(request: FileUploadRequest): Promise<ApiResponse<FileUploadResponse>>;
  
  // GET /api/v1/files/{file_id}
  getFile(fileId: string): Promise<ApiResponse<UploadedFile>>;
  
  // DELETE /api/v1/files/{file_id}
  deleteFile(fileId: string): Promise<ApiResponse<void>>;
  
  // GET /api/v1/files/{file_id}/download
  downloadFile(fileId: string): Promise<Blob>;
}
```

### Health Check Endpoints

```typescript
interface HealthEndpoints {
  // GET /healthz
  getHealth(): Promise<ApiResponse<{ status: 'ok' | 'degraded' | 'down' }>>;
  
  // GET /api/v1/test/no-auth
  testNoAuth(): Promise<ApiResponse<{ message: string }>>;
  
  // GET /api/v1/test/auth
  testAuth(): Promise<ApiResponse<{ message: string; user_id: string }>>;
}
```

## Configuration Types

```typescript
interface ApiConfig {
  apiBaseUrl: string;
  wsBaseUrl: string;
  enableLogging: boolean;
  timeout?: number;
  retryAttempts?: number;
  retryDelay?: number;
}

interface WebSocketConfig {
  url: string;
  maxReconnectAttempts?: number;
  reconnectDelay?: number;
  maxReconnectDelay?: number;
  heartbeatInterval?: number;
  connectionTimeout?: number;
}

interface FileUploadConfig {
  maxFileSize: number; // bytes
  maxFiles: number;
  allowedTypes: string[];
  chunkSize?: number;
  timeout?: number;
  retryAttempts?: number;
}

interface CircuitBreakerConfig {
  failureThreshold: number;
  recoveryTimeout: number;
  monitoringPeriod: number;
}
```

## Utility Types

```typescript
interface RequestOptions {
  timeout?: number;
  retryAttempts?: number;
  correlationId?: string;
  signal?: AbortSignal;
}

interface RetryConfig {
  maxAttempts: number;
  baseDelay: number;
  maxDelay: number;
  backoffFactor: number;
  jitterFactor: number;
}

interface ConnectionState {
  status: 'disconnected' | 'connecting' | 'connected' | 'error';
  lastConnected?: Date;
  reconnectAttempts: number;
  error?: string;
}

interface NotificationStore {
  notifications: TeacherNotification[];
  unreadCount: number;
  connectionState: ConnectionState;
  lastUpdate: Date;
}
```

## Environment Variables

```typescript
interface EnvironmentConfig {
  // API Configuration
  VITE_API_BASE_URL?: string;
  VITE_WS_BASE_URL?: string;
  
  // Authentication
  VITE_JWT_SECRET?: string;
  VITE_TOKEN_EXPIRY?: string;
  
  // File Upload
  VITE_MAX_FILE_SIZE?: string;
  VITE_MAX_FILES_PER_BATCH?: string;
  
  // WebSocket
  VITE_WS_HEARTBEAT_INTERVAL?: string;
  VITE_WS_RECONNECT_ATTEMPTS?: string;
  
  // Development
  VITE_ENABLE_API_LOGGING?: string;
  VITE_ENABLE_DEBUG_MODE?: string;
}
```

## Constants

```typescript
export const API_CONSTANTS = {
  // File Upload Limits
  MAX_FILE_SIZE: 100 * 1024 * 1024, // 100MB
  MAX_FILES_PER_BATCH: 50,
  ALLOWED_FILE_TYPES: [
    'application/pdf',
    'text/plain',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'image/jpeg',
    'image/png',
    'image/gif'
  ],
  
  // WebSocket
  WS_HEARTBEAT_INTERVAL: 30000, // 30 seconds
  WS_CONNECTION_TIMEOUT: 10000, // 10 seconds
  WS_MAX_RECONNECT_ATTEMPTS: 5,
  WS_RECONNECT_DELAY: 1000, // 1 second
  WS_MAX_RECONNECT_DELAY: 30000, // 30 seconds
  
  // API Retry
  DEFAULT_RETRY_ATTEMPTS: 3,
  DEFAULT_RETRY_DELAY: 1000, // 1 second
  MAX_RETRY_DELAY: 10000, // 10 seconds
  RETRY_BACKOFF_FACTOR: 2,
  RETRY_JITTER_FACTOR: 0.1,
  
  // Circuit Breaker
  CIRCUIT_BREAKER_FAILURE_THRESHOLD: 5,
  CIRCUIT_BREAKER_RECOVERY_TIMEOUT: 60000, // 1 minute
  CIRCUIT_BREAKER_MONITORING_PERIOD: 300000, // 5 minutes
  
  // Token Management
  TOKEN_REFRESH_THRESHOLD: 300000, // 5 minutes
  TOKEN_REFRESH_RETRY_DELAY: 5000, // 5 seconds
} as const;

export const HTTP_STATUS_CODES = {
  OK: 200,
  CREATED: 201,
  NO_CONTENT: 204,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  UNPROCESSABLE_ENTITY: 422,
  TOO_MANY_REQUESTS: 429,
  INTERNAL_SERVER_ERROR: 500,
  BAD_GATEWAY: 502,
  SERVICE_UNAVAILABLE: 503,
  GATEWAY_TIMEOUT: 504
} as const;

export const NOTIFICATION_CATEGORIES = {
  BATCH_PROGRESS: 'batch_progress',
  PROCESSING_RESULTS: 'processing_results',
  FILE_OPERATIONS: 'file_operations',
  CLASS_MANAGEMENT: 'class_management',
  STUDENT_WORKFLOW: 'student_workflow',
  SYSTEM_ALERTS: 'system_alerts'
} as const;

export const NOTIFICATION_PRIORITIES = {
  CRITICAL: 'critical',
  IMMEDIATE: 'immediate',
  HIGH: 'high',
  STANDARD: 'standard',
  LOW: 'low'
} as const;
```

## Type Guards

```typescript
export function isApiError(error: unknown): error is ApiError {
  return error instanceof Error && error.name === 'ApiError';
}

export function isNetworkError(error: unknown): error is NetworkError {
  return error instanceof Error && error.name === 'NetworkError';
}

export function isAuthenticationError(error: unknown): error is AuthenticationError {
  return error instanceof Error && error.name === 'AuthenticationError';
}

export function isAuthorizationError(error: unknown): error is AuthorizationError {
  return error instanceof Error && error.name === 'AuthorizationError';
}

export function isValidJWTToken(token: unknown): token is JWTToken {
  return typeof token === 'object' && 
         token !== null && 
         'access_token' in token && 
         'token_type' in token &&
         typeof (token as any).access_token === 'string' &&
         (token as any).token_type === 'Bearer';
}

export function isValidBatch(batch: unknown): batch is Batch {
  return typeof batch === 'object' &&
         batch !== null &&
         'id' in batch &&
         'status' in batch &&
         'created_at' in batch &&
         typeof (batch as any).id === 'string' &&
         ['pending', 'processing', 'completed', 'failed'].includes((batch as any).status);
}

export function isWebSocketMessage(data: unknown): data is WebSocketMessage {
  return typeof data === 'object' &&
         data !== null &&
         'type' in data &&
         'timestamp' in data &&
         typeof (data as any).type === 'string' &&
         typeof (data as any).timestamp === 'string';
}
```

## Usage Examples

### Complete API Client Interface

```typescript
interface HuleEduApiClient extends 
  AuthEndpoints, 
  BatchEndpoints, 
  FileUploadEndpoints, 
  HealthEndpoints {
  
  // Configuration
  configure(config: Partial<ApiConfig>): void;
  
  // Request interceptors
  addRequestInterceptor(interceptor: (config: RequestInit) => RequestInit): void;
  addResponseInterceptor(interceptor: (response: Response) => Response): void;
  
  // Utility methods
  setCorrelationId(id: string): void;
  getCorrelationId(): string | null;
  clearCorrelationId(): void;
}
```

This comprehensive API reference provides all the TypeScript types, interfaces, and constants needed for robust HuleEdu frontend integration with full type safety and error handling.
