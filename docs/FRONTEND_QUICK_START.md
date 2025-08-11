# HuleEdu Frontend Quick Start Guide

## Overview

This guide helps you get started with HuleEdu API integration quickly. It covers essential authentication, basic API setup, and common operations to get your frontend application connected and working.

## Prerequisites

- Node.js 16+ and npm/yarn
- Basic knowledge of JavaScript/TypeScript
- A frontend framework (React, Svelte, Vue, etc.) or vanilla JavaScript

## Table of Contents

- [Authentication Setup](#authentication-setup)
- [Basic API Client](#basic-api-client)
- [Common Operations](#common-operations)
- [Error Handling Basics](#error-handling-basics)
- [Development Setup](#development-setup)
- [Next Steps](#next-steps)

---

## Authentication Setup

The HuleEdu API Gateway uses JWT (JSON Web Tokens) for authentication. All endpoints except `/healthz` and `/v1/test/no-auth` require valid JWT tokens.

### JWT Token Structure

Based on the API Gateway Service configuration (`services/api_gateway_service/config.py`):

```typescript
// JWT Token Response (implement with your auth service)
interface JWTToken {
  access_token: string;
  token_type: "Bearer";
  expires_in?: number; // seconds
}

// JWT Payload Structure (HS256 algorithm)
interface JWTPayload {
  sub: string;        // User ID (required, non-empty) - validated by API Gateway
  exp: number;        // Expiration timestamp (required) - validated by API Gateway
  iat: number;        // Issued at timestamp
  // Additional claims as needed by your auth service
}
```

**Critical Requirements** (per `services/api_gateway_service/config.py`):
- **Algorithm**: HS256 (`JWT_ALGORITHM: str = "HS256"`)
- **Secret Key**: Must match `JWT_SECRET_KEY` environment variable
- **Required Claims**: `sub` (non-empty) and `exp` are validated by the API Gateway

### Basic Authentication Flow

```typescript
// 1. Login and get token (implement with your auth service)
async function login(credentials: { username: string; password: string }): Promise<JWTToken> {
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

// 2. Store token securely
function storeToken(token: JWTToken): void {
  // For development: localStorage (less secure but simpler)
  localStorage.setItem('access_token', token.access_token);
  localStorage.setItem('token_expires', (Date.now() + (token.expires_in || 3600) * 1000).toString());
  
  // For production: consider httpOnly cookies
  // document.cookie = `access_token=${token.access_token}; HttpOnly; Secure; SameSite=Strict`;
}

// 3. Retrieve token with expiration check
function getToken(): string | null {
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

// 4. Clear token
function clearToken(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('token_expires');
}

// 5. Create authorization headers
function createAuthHeaders(correlationId?: string): Record<string, string> {
  const token = getToken();
  if (!token) {
    throw new Error('No valid authentication token available');
  }
  
  const headers: Record<string, string> = {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
  
  if (correlationId) {
    headers['X-Correlation-ID'] = correlationId;
  }
  
  return headers;
}
```

---

## Basic API Client

Create a simple API client for common HuleEdu operations:

```typescript
import { v4 as uuidv4 } from 'uuid';

interface ApiResponse<T> {
  data?: T;
  error?: {
    detail: string;
    correlation_id?: string;
  };
  success: boolean;
}

class HuleEduApiClient {
  private baseUrl: string;
  
  constructor(baseUrl: string = 'http://localhost:4001') {
    this.baseUrl = baseUrl;
  }
  
  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    requireAuth: boolean = true
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseUrl}${endpoint}`;
    const correlationId = uuidv4();
    
    let headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options.headers as Record<string, string>
    };
    
    if (requireAuth) {
      try {
        const authHeaders = createAuthHeaders(correlationId);
        headers = { ...headers, ...authHeaders };
      } catch (error) {
        return {
          error: { detail: 'Authentication required' },
          success: false
        };
      }
    }
    
    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        return {
          error: {
            detail: errorData.detail || `HTTP ${response.status}`,
            correlation_id: correlationId
          },
          success: false
        };
      }
      
      const data = await response.json();
      return { data, success: true };
      
    } catch (error) {
      return {
        error: {
          detail: error instanceof Error ? error.message : 'Network error',
          correlation_id: correlationId
        },
        success: false
      };
    }
  }
  
  // Health check (no auth required)
  async healthCheck(): Promise<ApiResponse<any>> {
    return this.request('/healthz', {}, false);
  }
  
  // Get batch status
  async getBatchStatus(batchId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/batches/${batchId}/status`);
  }
  
  // Request pipeline processing
  async requestPipeline(batchId: string, request: any): Promise<ApiResponse<void>> {
    return this.request(`/v1/batches/${batchId}/pipelines`, {
      method: 'POST',
      body: JSON.stringify(request)
    });
  }
  
  // Upload files
  async uploadFiles(formData: FormData): Promise<ApiResponse<any>> {
    return this.request('/v1/files/batch', {
      method: 'POST',
      body: formData,
      headers: {} // Don't set Content-Type for FormData
    });
  }
}

// Create a singleton instance
const apiClient = new HuleEduApiClient();
export default apiClient;
```

---

## Common Operations

### 1. Check API Health

```typescript
// Verify the API is accessible
async function checkApiHealth() {
  try {
    const response = await apiClient.healthCheck();
    if (response.success) {
      console.log('API is healthy:', response.data);
      return true;
    } else {
      console.error('API health check failed:', response.error);
      return false;
    }
  } catch (error) {
    console.error('Failed to check API health:', error);
    return false;
  }
}
```

### 2. Get Batch Status

```typescript
// Check the status of a batch
async function getBatchStatus(batchId: string) {
  try {
    const response = await apiClient.getBatchStatus(batchId);
    if (response.success) {
      console.log('Batch status:', response.data);
      return response.data;
    } else {
      console.error('Failed to get batch status:', response.error);
      return null;
    }
  } catch (error) {
    console.error('Error getting batch status:', error);
    return null;
  }
}
```

### 3. Upload Files

```typescript
// Upload files to create a batch
async function uploadFiles(files: File[], batchId: string) {
  const formData = new FormData();
  formData.append('batch_id', batchId);
  
  files.forEach(file => {
    formData.append('files', file);
  });
  
  try {
    const response = await apiClient.uploadFiles(formData);
    if (response.success) {
      console.log('Files uploaded successfully:', response.data);
      return response.data;
    } else {
      console.error('File upload failed:', response.error);
      return null;
    }
  } catch (error) {
    console.error('Error uploading files:', error);
    return null;
  }
}
```

### 4. Request Processing Pipeline

```typescript
// Request processing for a batch
async function requestProcessing(batchId: string, pipelineType: string = 'spellcheck') {
  const request = {
    pipeline_phase: pipelineType,
    priority: 'standard'
  };
  
  try {
    const response = await apiClient.requestPipeline(batchId, request);
    if (response.success) {
      console.log('Processing requested successfully');
      return true;
    } else {
      console.error('Failed to request processing:', response.error);
      return false;
    }
  } catch (error) {
    console.error('Error requesting processing:', error);
    return false;
  }
}
```

---

## Error Handling Basics

### Common Error Types

```typescript
// Basic error handling for API responses
function handleApiError(error: { detail: string; correlation_id?: string }) {
  console.error('API Error:', error.detail);
  
  if (error.correlation_id) {
    console.log('Correlation ID:', error.correlation_id);
  }
  
  // Handle specific error cases
  if (error.detail.includes('Authentication')) {
    // Clear token and redirect to login
    clearToken();
    window.location.href = '/login';
  } else if (error.detail.includes('Rate limit')) {
    // Show rate limit message
    alert('Too many requests. Please wait a moment and try again.');
  } else {
    // Generic error handling
    alert(`Error: ${error.detail}`);
  }
}
```

### Simple Retry Logic

```typescript
// Basic retry function for transient failures
async function withRetry<T>(
  operation: () => Promise<T>,
  maxRetries: number = 3,
  delay: number = 1000
): Promise<T> {
  let lastError: Error;
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error as Error;
      
      if (attempt === maxRetries) {
        break;
      }
      
      // Wait before retry
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, attempt)));
    }
  }
  
  throw lastError!;
}

// Usage example
async function getBatchStatusWithRetry(batchId: string) {
  return withRetry(() => apiClient.getBatchStatus(batchId));
}
```

---

## Development Setup

### Environment Configuration

Create a configuration file for different environments:

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

Based on `services/api_gateway_service/config.py`, the API Gateway is configured with CORS support for:

**Default Development Ports:**
- `http://localhost:3000` (Create React App default)
- `http://localhost:3001` (Alternative development port)

**Configuration:**
```python
# From services/api_gateway_service/config.py
CORS_ORIGINS: list[str] = Field(
    default=["http://localhost:3000", "http://localhost:3001"],
    description="Allowed CORS origins for React frontend",
)
CORS_ALLOW_CREDENTIALS: bool = Field(
    default=True, description="Allow credentials in CORS requests"
)
CORS_ALLOW_METHODS: list[str] = Field(
    default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    description="Allowed HTTP methods for CORS",
)
```

**For Different Ports:**
If you're using a different development port (e.g., Vite's 5173), configure the `API_GATEWAY_CORS_ORIGINS` environment variable:

```bash
API_GATEWAY_CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

**For Production:**
Set production origins in the environment variable:
```bash
API_GATEWAY_CORS_ORIGINS=["https://yourdomain.com","https://app.yourdomain.com"]
```

### Package Dependencies

Install required dependencies:

```bash
npm install uuid
npm install --save-dev @types/uuid
```

For TypeScript projects, you may also want:

```bash
npm install --save-dev typescript @types/node
```

### Environment Variables

Based on the API Gateway Service configuration (`services/api_gateway_service/config.py`), ensure these environment variables are properly configured:

#### **Frontend Application Environment Variables**
```bash
# API Configuration
REACT_APP_API_BASE_URL=http://localhost:4001  # Development
REACT_APP_WS_BASE_URL=ws://localhost:8081     # Development
NODE_ENV=development

# For production:
# REACT_APP_API_BASE_URL=https://api.huledu.com
# REACT_APP_WS_BASE_URL=wss://ws.huledu.com
# NODE_ENV=production
```

#### **API Gateway Service Environment Variables** (for reference)
```bash
# Core Configuration
API_GATEWAY_HTTP_HOST=0.0.0.0
API_GATEWAY_HTTP_PORT=4001
API_GATEWAY_LOG_LEVEL=INFO

# Security (REQUIRED for production)
API_GATEWAY_JWT_SECRET_KEY=your-production-secret-key
API_GATEWAY_JWT_ALGORITHM=HS256

# CORS (adjust for your frontend URLs)
API_GATEWAY_CORS_ORIGINS=["http://localhost:3000","http://localhost:3001"]
API_GATEWAY_CORS_ALLOW_CREDENTIALS=true

# Service Dependencies
API_GATEWAY_CMS_API_URL=http://class_management_service:8000
API_GATEWAY_FILE_SERVICE_URL=http://file_service:8000
API_GATEWAY_RESULT_AGGREGATOR_URL=http://result_aggregator_service:8000
API_GATEWAY_KAFKA_BOOTSTRAP_SERVERS=kafka:9092
API_GATEWAY_REDIS_URL=redis://redis:6379

# Performance & Resilience
API_GATEWAY_RATE_LIMIT_REQUESTS=100
API_GATEWAY_RATE_LIMIT_WINDOW=60
API_GATEWAY_CIRCUIT_BREAKER_ENABLED=true
API_GATEWAY_HTTP_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
API_GATEWAY_HTTP_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
```

---

## Next Steps

Once you have basic API integration working, explore these advanced topics:

### **Real-Time Features**

- **[Real-Time Communication Guide](FRONTEND_REALTIME_GUIDE.md)** - WebSocket integration and notifications *(Coming Soon)*
- **[WebSocket API Documentation](WEBSOCKET_API_DOCUMENTATION.md)** - Technical WebSocket API reference

### **File Management**

- **[File Upload Guide](FRONTEND_FILE_UPLOAD_GUIDE.md)** - Advanced file handling with progress tracking *(Coming Soon)*

### **Production Readiness**

- **[Production Guide](FRONTEND_PRODUCTION_GUIDE.md)** - Error handling, resilience, and production patterns *(Coming Soon)*

### **Framework Integration**

- **[Framework Examples](FRONTEND_FRAMEWORK_EXAMPLES.md)** - React, Svelte, and other framework-specific implementations *(Coming Soon)*
- **[Svelte Integration Examples](SVELTE_INTEGRATION_EXAMPLES.md)** - Existing Svelte-specific examples

## Example: Complete Basic Integration

Here's a complete example of a simple React component that demonstrates the basic integration:

```typescript
import React, { useState, useEffect } from 'react';
import apiClient from './api-client';

const BatchManager: React.FC = () => {
  const [batchId, setBatchId] = useState<string>('');
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleGetStatus = async () => {
    if (!batchId) {
      setError('Please enter a batch ID');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.getBatchStatus(batchId);
      if (response.success) {
        setStatus(response.data);
      } else {
        setError(response.error?.detail || 'Failed to get status');
      }
    } catch (err) {
      setError('Network error occurred');
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.uploadFiles(Array.from(files));
      if (response.success) {
        console.log('Upload successful:', response.data);
        // Handle successful upload
      } else {
        setError(response.error?.detail || 'Upload failed');
      }
    } catch (err) {
      setError('Upload error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2>HuleEdu Batch Manager</h2>
      
      <div>
        <input
          type="text"
          placeholder="Enter Batch ID"
          value={batchId}
          onChange={(e) => setBatchId(e.target.value)}
        />
        <button onClick={handleGetStatus} disabled={loading}>
          Get Status
        </button>
      </div>

      <div>
        <input
          type="file"
          multiple
          onChange={handleFileUpload}
          disabled={loading}
        />
      </div>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'red' }}>Error: {error}</p>}
      {status && (
        <div>
          <h3>Batch Status</h3>
          <pre>{JSON.stringify(status, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

{{ ... }}
export default BatchManager;
```

---

## Troubleshooting

### Common Issues

1. **CORS Errors**: 
   - Ensure your development server is running on port 3000 or 3001 (default allowed origins)
   - For other ports, configure `API_GATEWAY_CORS_ORIGINS` environment variable
   - Check browser console for specific CORS error details

2. **Authentication Failures**: 
   - Verify JWT token format: `Authorization: Bearer <token>`
   - Check token algorithm matches HS256 (per API Gateway config)
   - Ensure required claims: `sub` (non-empty) and `exp` (future timestamp)
   - Verify `JWT_SECRET_KEY` matches between auth service and API Gateway

3. **Network Errors**: 
   - Verify API Gateway is running on port 4001 (`API_GATEWAY_HTTP_PORT`)
   - Check API health: `GET http://localhost:4001/healthz`
   - Review API Gateway logs for specific error details

4. **Rate Limiting**: 
   - Default limit: 100 requests per minute per client
   - Look for HTTP 429 responses with `Retry-After` header
   - Implement exponential backoff retry logic

5. **File Upload Issues**: 
   - Don't set `Content-Type` header for FormData (browser sets it automatically)
   - Check file size limits and allowed types
   - Verify `batch_id` parameter is included in FormData

6. **Circuit Breaker**: 
   - API Gateway may return errors if downstream services are failing
   - Check service health endpoints and logs
   - Wait for recovery timeout (default: 60 seconds)

### Getting Help

#### **Debugging Steps**
1. **Check Correlation IDs**: All API responses include correlation IDs for tracking
{{ ... }}
   - API Gateway: `GET http://localhost:4001/healthz`
   - Check response for service status and dependencies
3. **Review Network Tab**: Browser developer tools show detailed request/response information
4. **Check Environment Variables**: Ensure all required variables are set correctly
5. **Validate JWT Tokens**: Use online JWT decoders to verify token structure and claims

#### **API Contract References**
- **OpenAPI Specification**: `http://localhost:4001/docs` (interactive documentation)
- **Pydantic Models**: `libs/common_core/src/common_core/models/` (source of truth for data structures)
- **Service Configuration**: `services/api_gateway_service/config.py` (environment variables and defaults)

#### **Additional Resources**
- **[Frontend Integration Index](FRONTEND_INTEGRATION_INDEX.md)** - Navigation to all frontend guides
- **[WebSocket API Documentation](WEBSOCKET_API_DOCUMENTATION.md)** - Real-time communication details
- **[Frontend Readiness Checklist](../TASKS/FRONTEND_READINESS_CHECKLIST.md)** - Implementation validation checklist

---

*This guide gets you started quickly. For comprehensive patterns and production-ready implementations, explore the other guides in the [Frontend Integration Index](FRONTEND_INTEGRATION_INDEX.md).*
