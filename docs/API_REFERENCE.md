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
// Base URL: http://localhost:4001/v1
interface BatchEndpoints {
  healthCheck: '/healthz';                           // GET (no auth)
  createBatch: '/batches';                          // POST
  getBatchStatus: '/batches/:batchId/status';       // GET
  requestPipeline: '/batches/:batchId/pipelines';   // POST
  uploadFiles: '/files/batch';                      // POST (FormData)
}
```

### Request/Response Types
```typescript
interface BatchCreateRequest {
  file_count: number;
  title?: string;
  description?: string;
  class_id?: string;
}

interface BatchCreateResponse {
  batch_id: string;
  status: BatchStatus;
  created_at: string;
}

interface BatchStatusResponse {
  batch_id: string;
  status: BatchStatus;
  user_id: string;
  created_at: string;
  updated_at: string;
  details: {
    progress?: {
      percentage: number;
      phase: string;
      estimated_completion?: string;
    };
    files_processed?: number;
    total_files?: number;
    error_details?: string;
    processing_duration_seconds?: number;
  };
  files?: BatchFileInfo[];
}

interface BatchFileInfo {
  file_id: string;
  filename: string;
  size_bytes: number;
  status: FileStatus;
  upload_timestamp: string;
  processing_results?: ProcessingResults;
}

type BatchStatus = 
  | 'created' 
  | 'uploading' 
  | 'uploaded' 
  | 'pending' 
  | 'processing' 
  | 'completed' 
  | 'failed' 
  | 'cancelled';

type FileStatus = 
  | 'uploaded' 
  | 'processing' 
  | 'completed' 
  | 'failed';

interface ProcessingResults {
  spellcheck?: {
    errors_found: number;
    corrections_suggested: number;
    confidence_score: number;
  };
  content_judgment?: {
    quality_score: number;
    readability_score: number;
    coherence_score: number;
    argument_strength: number;
  };
  feedback?: {
    sections: string[];
    overall_score: number;
    word_count: number;
  };
}
```

### Pipeline Processing
```typescript
interface PipelineRequest {
  pipeline_phase: PipelinePhase;
  priority: Priority;
  configuration?: PipelineConfiguration;
}

type PipelinePhase = 
  | 'spellcheck' 
  | 'content_judgment' 
  | 'feedback_generation';

type Priority = 
  | 'low' 
  | 'standard' 
  | 'high' 
  | 'urgent';

interface PipelineConfiguration {
  spellcheck?: {
    language: string;
    strict_mode: boolean;
  };
  content_judgment?: {
    rubric_id?: string;
    detailed_analysis: boolean;
  };
  feedback?: {
    feedback_type: 'brief' | 'detailed' | 'comprehensive';
    include_suggestions: boolean;
  };
}
```

---

## File Upload API

### Upload Request
```typescript
interface FileUploadData {
  batch_id: string;        // FormData field
  files: File[];          // FormData field (multiple)
}

interface FileUploadResponse {
  batch_id: string;
  uploaded_files: UploadedFileInfo[];
  total_files: number;
  total_size_bytes: number;
  upload_timestamp: string;
}

interface UploadedFileInfo {
  file_id: string;
  filename: string;
  original_filename: string;
  size_bytes: number;
  mime_type: string;
  checksum: string;
}
```

### File Validation
```typescript
interface FileValidationRules {
  maxFileSize: number;      // Default: 10MB
  maxFiles: number;         // Default: 50
  allowedMimeTypes: string[]; // text/plain, application/pdf, .docx, .doc
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
  url: string;                    // ws://localhost:8081/ws
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
  // Batch Events
  | 'BATCH_CREATED'
  | 'BATCH_FILES_UPLOADED'
  | 'BATCH_PROCESSING_STARTED'
  | 'BATCH_PROCESSING_COMPLETED'
  | 'BATCH_PROCESSING_FAILED'
  // Essay Events
  | 'ESSAY_SPELLCHECK_COMPLETED'
  | 'ESSAY_CONTENT_JUDGMENT_COMPLETED'
  | 'ESSAY_FEEDBACK_GENERATED'
  | 'ESSAY_PROCESSING_FAILED'
  // System Events
  | 'SYSTEM_MAINTENANCE_SCHEDULED'
  | 'SYSTEM_MAINTENANCE_STARTED'
  | 'SYSTEM_MAINTENANCE_COMPLETED'
  | 'SERVICE_DEGRADATION_ALERT'
  | 'SERVICE_RESTORED';

// Batch Notification Data Types
interface BatchCreatedData {
  batch_id: string;
  user_id: string;
  status: BatchStatus;
  file_count: number;
  correlation_id: string;
}

interface BatchFilesUploadedData {
  batch_id: string;
  user_id: string;
  files_uploaded: number;
  total_size_bytes: number;
  correlation_id: string;
}

interface BatchProcessingStartedData {
  batch_id: string;
  user_id: string;
  pipeline_phase: PipelinePhase;
  estimated_duration_minutes: number;
  correlation_id: string;
}

interface BatchProcessingCompletedData {
  batch_id: string;
  user_id: string;
  pipeline_phase: PipelinePhase;
  status: 'COMPLETED';
  processing_duration_minutes: number;
  essays_processed: number;
  correlation_id: string;
}

interface BatchProcessingFailedData {
  batch_id: string;
  user_id: string;
  pipeline_phase: PipelinePhase;
  error_type: string;
  error_message: string;
  retry_recommended: boolean;
  correlation_id: string;
}

// Essay Notification Data Types
interface EssaySpellcheckCompletedData {
  essay_id: string;
  batch_id: string;
  user_id: string;
  spelling_errors_found: number;
  grammar_errors_found: number;
  confidence_score: number;
  correlation_id: string;
}

interface EssayContentJudgmentCompletedData {
  essay_id: string;
  batch_id: string;
  user_id: string;
  content_quality_score: number;
  readability_score: number;
  coherence_score: number;
  argument_strength: number;
  correlation_id: string;
}

interface EssayFeedbackGeneratedData {
  essay_id: string;
  batch_id: string;
  user_id: string;
  feedback_sections: string[];
  overall_score: number;
  feedback_length_words: number;
  correlation_id: string;
}

interface EssayProcessingFailedData {
  essay_id: string;
  batch_id: string;
  user_id: string;
  pipeline_phase: PipelinePhase;
  error_type: string;
  error_message: string;
  retry_recommended: boolean;
  correlation_id: string;
}

// System Notification Data Types
interface SystemMaintenanceScheduledData {
  maintenance_start: string;
  maintenance_end: string;
  affected_services: string[];
  description: string;
  user_id: string;
  correlation_id: string;
}

interface SystemMaintenanceStartedData {
  maintenance_type: string;
  estimated_duration_minutes: number;
  affected_services: string[];
  user_id: string;
  correlation_id: string;
}

interface SystemMaintenanceCompletedData {
  maintenance_type: string;
  actual_duration_minutes: number;
  services_restored: string[];
  user_id: string;
  correlation_id: string;
}

interface ServiceDegradationAlertData {
  affected_service: string;
  degradation_level: 'minor' | 'moderate' | 'severe';
  expected_delay_minutes: number;
  estimated_resolution: string;
  user_id: string;
  correlation_id: string;
}

interface ServiceRestoredData {
  restored_service: string;
  downtime_duration_minutes: number;
  performance_status: 'normal' | 'degraded';
  user_id: string;
  correlation_id: string;
}

type NotificationData = 
  | BatchCreatedData
  | BatchFilesUploadedData
  | BatchProcessingStartedData
  | BatchProcessingCompletedData
  | BatchProcessingFailedData
  | EssaySpellcheckCompletedData
  | EssayContentJudgmentCompletedData
  | EssayFeedbackGeneratedData
  | EssayProcessingFailedData
  | SystemMaintenanceScheduledData
  | SystemMaintenanceStartedData
  | SystemMaintenanceCompletedData
  | ServiceDegradationAlertData
  | ServiceRestoredData;
```

### WebSocket Event Handlers
```typescript
interface WebSocketEventHandlers {
  // Connection Events
  connected: (data: { timestamp: string }) => void;
  disconnected: (event: CloseEvent) => void;
  error: (error: Event) => void;
  message: (message: NotificationEnvelope) => void;
  
  // Batch Events
  BATCH_CREATED: (data: BatchCreatedData) => void;
  BATCH_FILES_UPLOADED: (data: BatchFilesUploadedData) => void;
  BATCH_PROCESSING_STARTED: (data: BatchProcessingStartedData) => void;
  BATCH_PROCESSING_COMPLETED: (data: BatchProcessingCompletedData) => void;
  BATCH_PROCESSING_FAILED: (data: BatchProcessingFailedData) => void;
  
  // Essay Events
  ESSAY_SPELLCHECK_COMPLETED: (data: EssaySpellcheckCompletedData) => void;
  ESSAY_CONTENT_JUDGMENT_COMPLETED: (data: EssayContentJudgmentCompletedData) => void;
  ESSAY_FEEDBACK_GENERATED: (data: EssayFeedbackGeneratedData) => void;
  ESSAY_PROCESSING_FAILED: (data: EssayProcessingFailedData) => void;
  
  // System Events
  SYSTEM_MAINTENANCE_SCHEDULED: (data: SystemMaintenanceScheduledData) => void;
  SYSTEM_MAINTENANCE_STARTED: (data: SystemMaintenanceStartedData) => void;
  SYSTEM_MAINTENANCE_COMPLETED: (data: SystemMaintenanceCompletedData) => void;
  SERVICE_DEGRADATION_ALERT: (data: ServiceDegradationAlertData) => void;
  SERVICE_RESTORED: (data: ServiceRestoredData) => void;
  
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
  | 4001  // Authentication failed
  | 4029  // Rate limit exceeded  
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

### Frontend Environment Variables
```typescript
interface FrontendEnvConfig {
  // API Configuration
  REACT_APP_API_BASE_URL: string;      // Default: http://localhost:4001
  REACT_APP_WS_BASE_URL: string;       // Default: ws://localhost:8081
  NODE_ENV: 'development' | 'production' | 'test';
  
  // Feature Flags
  REACT_APP_ENABLE_WEBSOCKET: string;  // 'true' | 'false'
  REACT_APP_ENABLE_DEBUG_LOGGING: string; // 'true' | 'false'
  
  // Timeouts and Limits
  REACT_APP_API_TIMEOUT: string;       // Default: '30000' (ms)
  REACT_APP_UPLOAD_TIMEOUT: string;    // Default: '300000' (ms)
  REACT_APP_MAX_FILE_SIZE: string;     // Default: '10485760' (10MB)
  REACT_APP_MAX_FILES: string;         // Default: '50'
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
  WS_URL: 'ws://localhost:8081',
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