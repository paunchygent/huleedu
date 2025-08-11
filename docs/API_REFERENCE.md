# HuleEdu API Reference

Complete TypeScript types, interfaces, and API specifications for HuleEdu integration.

## Table of Contents
- [Authentication Types](#authentication-types)
- [Batch Management API](#batch-management-api)
- [File Upload API](#file-upload-api)
- [WebSocket Protocols](#websocket-protocols)
- [Error Types](#error-types)
- [Environment Configuration](#environment-configuration)

---

## Authentication Types

### JWT Token Structure
```typescript
interface JWTToken {
  access_token: string;
  token_type: "Bearer";
  expires_in?: number; // seconds
}

interface JWTPayload {
  sub: string;        // User ID (required, validated by API Gateway)
  exp: number;        // Expiration timestamp (required, validated by API Gateway)
  iat: number;        // Issued at timestamp
  roles?: string[];   // User roles (optional)
}

interface AuthHeaders {
  'Authorization': string;        // Bearer token
  'Content-Type': 'application/json';
  'X-Correlation-ID': string;     // UUID for request tracking
}
```

---

## Batch Management API

### API Endpoints
```typescript
// Base URL: http://localhost:4001
interface ApiEndpoints {
  // Health & Monitoring (no auth)
  healthCheck: '/healthz';                          // GET
  metrics: '/metrics';                              // GET (Prometheus)
  
  // Authentication Test 
  testNoAuth: '/v1/test/no-auth';                   // GET (no auth)
  testWithAuth: '/v1/test/with-auth';               // GET (auth required)
  
  // Batch Management (auth required)
  requestPipeline: '/v1/batches/:batchId/pipelines'; // POST
  getBatchStatus: '/v1/batches/:batchId/status';     // GET
  
  // File Operations (auth required) 
  uploadFiles: '/v1/files/batch';                    // POST (FormData)
  
  // Class Management Proxy (auth required)
  classManagement: '/v1/classes/*';                  // GET, POST, PUT, DELETE
}
```

### Request/Response Types
```typescript
interface PipelineRequest {
  batch_id: string;
  requested_pipeline: PipelinePhase;
  is_retry?: boolean;
  retry_reason?: string;
}

interface PipelineResponse {
  status: 'accepted';
  message: 'Pipeline execution request received';
  batch_id: string;
  correlation_id: string;
}

interface BatchStatusResponse {
  status: BatchStatus;
  details: {
    batch_id: string;
    created_at: string;
    updated_at: string;
    total_essays: number;
    processed_essays: number;
    current_phase: PipelinePhase;
    progress_percentage: number;
    estimated_completion?: string;
  };
}

type BatchStatus = 
  | 'CREATED'           // Batch created, awaiting file upload
  | 'FILES_UPLOADED'    // Files uploaded, ready for processing  
  | 'PROCESSING'        // Currently being processed through pipeline
  | 'COMPLETED'         // All processing completed successfully
  | 'FAILED'            // Processing failed with errors
  | 'CANCELLED';        // Processing cancelled by user or system
```

### Pipeline Processing
```typescript
type PipelinePhase = 
  | 'SPELLCHECK'        // Basic spelling and grammar validation
  | 'AI_FEEDBACK'       // AI-powered content quality assessment and feedback generation  
  | 'CJ_ASSESSMENT'     // Comparative judgment assessment
  | 'NLP';              // Natural language processing analysis

// Pipeline requests are handled asynchronously (HTTP 202)
interface PipelineExecutionFlow {
  1: 'Request received (202 Accepted)';
  2: 'Kafka message published';
  3: 'WebSocket notifications sent';
  4: 'Status updates via GET /v1/batches/{id}/status';
}
```

---

## File Upload API

### Upload Request
```typescript
// POST /v1/files/batch
// Content-Type: multipart/form-data
interface FileUploadFormData {
  batch_id: string;        // Required: The batch identifier
  files: File[];          // Required: Array of files to upload (max 50)
}

interface FileUploadResponse {
  status: 'success';
  message: 'Files uploaded successfully';
  batch_id: string;
  files_uploaded: number;
  total_size_bytes: number;
  correlation_id: string;
}

interface FileUploadLimits {
  maxFileSize: 50 * 1024 * 1024;     // 50MB per file
  maxTotalUpload: 100 * 1024 * 1024; // 100MB per request
  maxFilesPerBatch: 50;               // 50 files maximum
  supportedFormats: ['PDF', 'DOCX', 'TXT', 'RTF'];
  rateLimit: '5 requests per minute per user';
}
```

### File Validation
```typescript
// Validation is performed server-side with these rules:
interface ActualFileValidationRules {
  maxFileSize: 50 * 1024 * 1024;       // 50MB per file
  maxTotalSize: 100 * 1024 * 1024;     // 100MB per request  
  maxFiles: 50;                        // 50 files per batch
  supportedFormats: ['PDF', 'DOCX', 'TXT', 'RTF'];
  rateLimit: 5;                        // 5 requests per minute per user
}

interface FileValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
  validFiles: File[];
  invalidFiles: Array<{
    file: File;
    reasons: string[];
  }>;
}

interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  speed?: number;           // bytes per second
  remainingTime?: number;   // seconds
  currentFile?: string;
}
```

---

## WebSocket Protocols

### Connection Configuration
```typescript
interface WebSocketConfig {
  url: string;                    // ws://localhost:8080/ws
  token: string;                  // JWT token (query parameter)
  maxReconnectAttempts?: number;  // Default: 5
  reconnectDelay?: number;        // Default: 1000ms
  maxReconnectDelay?: number;     // Default: 30000ms
  heartbeatInterval?: number;     // Default: 30000ms
}

interface WebSocketConnectionInfo {
  url: string;
  state: WebSocketState;
  reconnectAttempts: number;
  lastConnected?: Date;
  lastDisconnected?: Date;
}

type WebSocketState = 
  | 'disconnected' 
  | 'connecting' 
  | 'connected' 
  | 'reconnecting' 
  | 'error';
```

### Notification Types
```typescript
interface NotificationEnvelope {
  notification_type: NotificationType;
  timestamp: string;
  data: NotificationData;
}

type NotificationType =
  // File Operations
  | 'batch_files_uploaded'
  | 'batch_file_removed'
  | 'batch_validation_failed'
  // Class Management
  | 'class_created'
  | 'student_added_to_class'
  | 'validation_timeout_processed'
  | 'student_associations_confirmed'
  // Processing Results
  | 'batch_spellcheck_completed'
  | 'batch_cj_assessment_completed'
  | 'batch_processing_started'
  | 'batch_results_ready'
  | 'batch_assessment_completed';

// File Operation Notification Data Types
interface BatchFilesUploadedData {
  notification_type: 'batch_files_uploaded';
  category: 'file_operations';
  priority: 'standard';
  action_required: false;
  payload: {
    batch_id: string;
    user_id: string;
    files_uploaded: number;
    total_size_bytes: number;
  };
  correlation_id: string;
}

interface BatchFileRemovedData {
  notification_type: 'batch_file_removed';
  category: 'file_operations';
  priority: 'standard';
  action_required: false;
  payload: {
    batch_id: string;
    file_id: string;
    filename: string;
  };
  correlation_id: string;
}

interface BatchValidationFailedData {
  notification_type: 'batch_validation_failed';
  category: 'system_alerts';
  priority: 'immediate';
  action_required: true;
  payload: {
    batch_id: string;
    validation_errors: string[];
    error_message: string;
  };
  correlation_id: string;
}

// Class Management Notification Data Types
interface ClassCreatedData {
  notification_type: 'class_created';
  category: 'class_management';
  priority: 'standard';
  action_required: false;
  payload: {
    class_id: string;
    class_name: string;
    teacher_id: string;
  };
  correlation_id: string;
}

interface StudentAddedToClassData {
  notification_type: 'student_added_to_class';
  category: 'class_management';
  priority: 'low';
  action_required: false;
  payload: {
    class_id: string;
    student_id: string;
    student_name: string;
  };
  correlation_id: string;
}

interface ValidationTimeoutProcessedData {
  notification_type: 'validation_timeout_processed';
  category: 'student_workflow';
  priority: 'immediate';
  action_required: false;
  payload: {
    batch_id: string;
    timeout_duration_seconds: number;
    processed_students: number;
  };
  correlation_id: string;
}

interface StudentAssociationsConfirmedData {
  notification_type: 'student_associations_confirmed';
  category: 'student_workflow';
  priority: 'high';
  action_required: false;
  payload: {
    batch_id: string;
    confirmed_associations: number;
    pending_associations: number;
  };
  correlation_id: string;
}

// Processing Result Notification Data Types
interface BatchSpellcheckCompletedData {
  notification_type: 'batch_spellcheck_completed';
  category: 'batch_progress';
  priority: 'low';
  action_required: false;
  payload: {
    batch_id: string;
    essays_processed: number;
    total_errors_found: number;
    processing_duration_seconds: number;
  };
  correlation_id: string;
}

interface BatchCjAssessmentCompletedData {
  notification_type: 'batch_cj_assessment_completed';
  category: 'batch_progress';
  priority: 'standard';
  action_required: false;
  payload: {
    batch_id: string;
    essays_assessed: number;
    average_content_score: number;
    processing_duration_seconds: number;
  };
  correlation_id: string;
}

interface BatchProcessingStartedData {
  notification_type: 'batch_processing_started';
  category: 'batch_progress';
  priority: 'low';
  action_required: false;
  payload: {
    batch_id: string;
    pipeline_phase: string;
    estimated_duration_minutes: number;
  };
  correlation_id: string;
}

interface BatchResultsReadyData {
  notification_type: 'batch_results_ready';
  category: 'processing_results';
  priority: 'high';
  action_required: false;
  payload: {
    batch_id: string;
    results_count: number;
    download_url?: string;
  };
  correlation_id: string;
}

interface BatchAssessmentCompletedData {
  notification_type: 'batch_assessment_completed';
  category: 'processing_results';
  priority: 'standard';
  action_required: false;
  payload: {
    batch_id: string;
    total_essays: number;
    completed_assessments: number;
    overall_completion_rate: number;
  };
  correlation_id: string;
}

type NotificationData = 
  // File Operations
  | BatchFilesUploadedData
  | BatchFileRemovedData
  | BatchValidationFailedData
  // Class Management
  | ClassCreatedData
  | StudentAddedToClassData
  | ValidationTimeoutProcessedData
  | StudentAssociationsConfirmedData
  // Processing Results
  | BatchSpellcheckCompletedData
  | BatchCjAssessmentCompletedData
  | BatchProcessingStartedData
  | BatchResultsReadyData
  | BatchAssessmentCompletedData;
```

### WebSocket Event Handlers
```typescript
interface WebSocketEventHandlers {
  // Connection Events
  connected: (data: { timestamp: string }) => void;
  disconnected: (event: CloseEvent) => void;
  error: (error: Event) => void;
  message: (message: NotificationEnvelope) => void;
  
  // File Operation Events
  batch_files_uploaded: (data: BatchFilesUploadedData) => void;
  batch_file_removed: (data: BatchFileRemovedData) => void;
  batch_validation_failed: (data: BatchValidationFailedData) => void;
  
  // Class Management Events
  class_created: (data: ClassCreatedData) => void;
  student_added_to_class: (data: StudentAddedToClassData) => void;
  validation_timeout_processed: (data: ValidationTimeoutProcessedData) => void;
  student_associations_confirmed: (data: StudentAssociationsConfirmedData) => void;
  
  // Processing Result Events
  batch_spellcheck_completed: (data: BatchSpellcheckCompletedData) => void;
  batch_cj_assessment_completed: (data: BatchCjAssessmentCompletedData) => void;
  batch_processing_started: (data: BatchProcessingStartedData) => void;
  batch_results_ready: (data: BatchResultsReadyData) => void;
  batch_assessment_completed: (data: BatchAssessmentCompletedData) => void;
  
  // Reconnection Events
  maxReconnectAttemptsReached: (data: { attempts: number }) => void;
}
```

### WebSocket Error Codes
```typescript
interface WebSocketError {
  code: WebSocketErrorCode;
  message: string;
  retry_recommended?: boolean;
  retry_after_seconds?: number;
}

type WebSocketErrorCode = 
  | 1008  // Authentication failed
  | 4000  // Rate limit exceeded  
  | 1011  // Server error
  | 1000  // Normal closure
  | 1001  // Going away
  | 1002  // Protocol error
  | 1003  // Unsupported data
  | 1006  // Abnormal closure
  | 1015; // TLS handshake failure
```

---

## Error Types

### API Error Response
```typescript
interface ApiError {
  detail: string;
  correlation_id?: string;
  error_code?: string;
  status_code?: number;
  timestamp?: string;
}

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: ApiError;
}
```

### Common Error Types
```typescript
type HttpStatusCode = 
  | 200  // OK
  | 201  // Created
  | 400  // Bad Request
  | 401  // Unauthorized
  | 403  // Forbidden
  | 404  // Not Found
  | 409  // Conflict
  | 413  // Payload Too Large
  | 429  // Too Many Requests
  | 500  // Internal Server Error
  | 502  // Bad Gateway
  | 503  // Service Unavailable
  | 504; // Gateway Timeout

interface ValidationError {
  field: string;
  message: string;
  code: string;
}

interface NetworkError extends Error {
  code: string;
  errno?: number;
  syscall?: string;
}

interface TimeoutError extends Error {
  timeout: number;
}

interface RateLimitError extends Error {
  retryAfter: number;
  limit: number;
  remaining: number;
}
```

---

## Environment Configuration

### Frontend Environment Variables (Svelte 5 + Vite)
```typescript
interface FrontendEnvConfig {
  // API Configuration
  VITE_API_BASE_URL: string;           // Default: http://localhost:4001
  VITE_WS_BASE_URL: string;            // Default: ws://localhost:8080
  NODE_ENV: 'development' | 'production' | 'test';
  
  // Feature Flags
  VITE_ENABLE_WEBSOCKET: string;       // 'true' | 'false'
  VITE_ENABLE_DEBUG_LOGGING: string;   // 'true' | 'false'
  
  // Timeouts and Limits
  VITE_API_TIMEOUT: string;            // Default: '30000' (ms)
  VITE_UPLOAD_TIMEOUT: string;         // Default: '300000' (ms)
  VITE_MAX_FILE_SIZE: string;          // Default: '10485760' (10MB)
  VITE_MAX_FILES: string;              // Default: '50'
}
```

### API Gateway Configuration (Reference)
```typescript
interface ApiGatewayConfig {
  // Core Service Configuration
  API_GATEWAY_HTTP_HOST: string;           // Default: "0.0.0.0"
  API_GATEWAY_HTTP_PORT: string;           // Default: "4001"
  API_GATEWAY_SERVICE_NAME: string;        // Default: "api-gateway-service"
  API_GATEWAY_LOG_LEVEL: string;           // Default: "INFO"
  API_GATEWAY_ENV_TYPE: string;            // Default: "development"

  // Security Configuration
  API_GATEWAY_JWT_SECRET_KEY: string;      // Required for production
  API_GATEWAY_JWT_ALGORITHM: string;       // Default: "HS256"

  // CORS Configuration  
  API_GATEWAY_CORS_ORIGINS: string[];      // Default: ["http://localhost:3000", "http://localhost:3001"]
  API_GATEWAY_CORS_ALLOW_CREDENTIALS: string; // Default: "true"
  API_GATEWAY_CORS_ALLOW_METHODS: string[];   // Default: ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
  API_GATEWAY_CORS_ALLOW_HEADERS: string[];   // Default: ["*"]

  // Service Dependencies
  API_GATEWAY_CMS_API_URL: string;         // Default: "http://class_management_service:8000"
  API_GATEWAY_FILE_SERVICE_URL: string;    // Default: "http://file_service:8000"
  API_GATEWAY_RESULT_AGGREGATOR_URL: string; // Default: "http://result_aggregator_service:8000"
  API_GATEWAY_KAFKA_BOOTSTRAP_SERVERS: string; // Default: "kafka:9092"
  API_GATEWAY_REDIS_URL: string;           // Default: "redis://redis:6379"

  // Performance & Resilience
  API_GATEWAY_HTTP_CLIENT_TIMEOUT_SECONDS: string;        // Default: "30"
  API_GATEWAY_HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS: string; // Default: "10"
  API_GATEWAY_RATE_LIMIT_REQUESTS: string;                // Default: "100"
  API_GATEWAY_RATE_LIMIT_WINDOW: string;                  // Default: "60"
  API_GATEWAY_CIRCUIT_BREAKER_ENABLED: string;            // Default: "true"
  API_GATEWAY_HTTP_CIRCUIT_BREAKER_FAILURE_THRESHOLD: string; // Default: "5"
  API_GATEWAY_HTTP_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: string;  // Default: "60"
}
```

---

## Type Guards and Utilities

### Type Guards
```typescript
function isApiResponse<T>(obj: any): obj is ApiResponse<T> {
  return typeof obj === 'object' && 
         obj !== null && 
         typeof obj.success === 'boolean';
}

function isApiError(obj: any): obj is ApiError {
  return typeof obj === 'object' && 
         obj !== null && 
         typeof obj.detail === 'string';
}

function isNotificationEnvelope(obj: any): obj is NotificationEnvelope {
  return typeof obj === 'object' && 
         obj !== null && 
         typeof obj.notification_type === 'string' && 
         typeof obj.timestamp === 'string' && 
         obj.data !== undefined;
}

function isWebSocketError(obj: any): obj is WebSocketError {
  return typeof obj === 'object' && 
         obj !== null && 
         typeof obj.code === 'number' && 
         typeof obj.message === 'string';
}
```

### Validation Utilities
```typescript
function validateJWTToken(token: string): { isValid: boolean; payload?: JWTPayload; error?: string } {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) {
      return { isValid: false, error: 'Invalid JWT format' };
    }
    
    const payload = JSON.parse(atob(parts[1])) as JWTPayload;
    
    if (!payload.sub || typeof payload.sub !== 'string' || payload.sub.trim() === '') {
      return { isValid: false, error: 'Missing or empty sub claim' };
    }
    
    if (!payload.exp || typeof payload.exp !== 'number') {
      return { isValid: false, error: 'Missing or invalid exp claim' };
    }
    
    if (payload.exp * 1000 <= Date.now()) {
      return { isValid: false, error: 'Token expired' };
    }
    
    return { isValid: true, payload };
  } catch (error) {
    return { isValid: false, error: 'Failed to parse JWT token' };
  }
}

function validateFileUpload(files: File[]): FileValidationResult {
  const maxFileSize = 10 * 1024 * 1024; // 10MB
  const maxFiles = 50;
  const allowedMimeTypes = [
    'text/plain',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'
  ];

  const errors: string[] = [];
  const warnings: string[] = [];
  const validFiles: File[] = [];
  const invalidFiles: Array<{ file: File; reasons: string[] }> = [];

  if (files.length === 0) {
    errors.push('No files selected');
  } else if (files.length > maxFiles) {
    errors.push(`Too many files. Maximum ${maxFiles} files allowed`);
  }

  files.forEach((file, index) => {
    const fileReasons: string[] = [];
    
    if (file.size === 0) {
      fileReasons.push('File is empty');
    } else if (file.size > maxFileSize) {
      fileReasons.push(`File exceeds maximum size (${formatFileSize(maxFileSize)})`);
    }

    if (!allowedMimeTypes.includes(file.type)) {
      fileReasons.push(`Unsupported file type: ${file.type}`);
    }

    if (fileReasons.length > 0) {
      invalidFiles.push({ file, reasons: fileReasons });
      errors.push(`File ${index + 1} (${file.name}): ${fileReasons.join(', ')}`);
    } else {
      validFiles.push(file);
    }
  });

  return {
    isValid: errors.length === 0,
    errors,
    warnings,
    validFiles,
    invalidFiles
  };
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}
```

---

## Constants

### Default Values
```typescript
export const API_DEFAULTS = {
  BASE_URL: 'http://localhost:4001',
  WS_URL: 'ws://localhost:8080',
  TIMEOUT: 30000,
  RETRY_ATTEMPTS: 3,
  RETRY_DELAY: 1000,
  MAX_FILE_SIZE: 10 * 1024 * 1024, // 10MB
  MAX_FILES: 50,
  HEARTBEAT_INTERVAL: 30000,
  RECONNECT_ATTEMPTS: 5,
  RECONNECT_DELAY: 1000,
  MAX_RECONNECT_DELAY: 30000
} as const;

export const MIME_TYPES = {
  ALLOWED: [
    'text/plain',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'
  ]
} as const;

export const HTTP_STATUS = {
  OK: 200,
  CREATED: 201,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  PAYLOAD_TOO_LARGE: 413,
  TOO_MANY_REQUESTS: 429,
  INTERNAL_SERVER_ERROR: 500,
  BAD_GATEWAY: 502,
  SERVICE_UNAVAILABLE: 503,
  GATEWAY_TIMEOUT: 504
} as const;
```

---

This reference provides complete type definitions and API specifications for HuleEdu integration. Use these types to ensure type safety and consistency across your frontend implementation.