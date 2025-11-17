# Svelte 5 Integration Guide

Complete guide for integrating HuleEdu services with Svelte 5 - from basic setup to production deployment.

## Table of Contents

### Getting Started
- [Quick Setup](#quick-setup)
- [Environment Configuration](#environment-configuration)
- [Basic Authentication](#basic-authentication)

### Core Integration
- [Store Architecture](#store-architecture)
- [API Client Setup](#api-client-setup)
- [WebSocket Management](#websocket-management)

### Components
- [Login Component](#login-component)
- [Batch Dashboard](#batch-dashboard)
- [File Upload](#file-upload)
- [Notification Center](#notification-center)

### Production Deployment
- [Error Handling](#error-handling)
- [Performance Optimization](#performance-optimization)
- [Security Considerations](#security-considerations)

---

## Getting Started

### Quick Setup

**Prerequisites**: Node.js 18+, Svelte 5, TypeScript

**1. Install Dependencies**
```bash
npm install @types/node
# No additional dependencies required - uses native fetch and WebSocket
```

**2. Environment Configuration**
```typescript
// .env
VITE_API_BASE_URL=http://localhost:4001
VITE_WS_BASE_URL=ws://localhost:8080
VITE_JWT_SECRET=your-development-secret
```

**3. TypeScript Configuration**
```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["DOM", "DOM.Iterable", "ES2022"],
    "types": ["vite/client"]
  }
}
```

### Environment Configuration

**Development Setup**
```typescript
// src/lib/config.ts
export const config = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:4001',
  wsBaseUrl: import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8080',
  isDevelopment: import.meta.env.DEV,
  isProduction: import.meta.env.PROD
};
```

**CORS Configuration**
Ensure your API Gateway allows your development origin:
```bash
# API Gateway should include your development URL in CORS_ORIGINS
API_GATEWAY_CORS_ORIGINS=["http://localhost:5173", "http://localhost:4173", "http://localhost:3000"]
```

### Development Utilities

**Mock Endpoints for Development**
The API Gateway provides mock endpoints specifically for Svelte 5 development:

```typescript
// Mock data endpoints (development only)
const mockEndpoints = {
  classes: '/dev/mock/classes',
  students: '/dev/mock/students/{class_id}',
  essays: '/dev/mock/essays/{status}',
  batches: '/dev/mock/batches',
  reactiveState: '/dev/mock/reactive-state',
  wsNotification: '/dev/mock/websocket/trigger',
  testToken: '/dev/auth/test-token'
};

// Example: Get mock classes optimized for Svelte 5 runes
const response = await fetch(`${config.apiBaseUrl}/dev/mock/classes`);
const { classes, metadata } = await response.json();

// Reactive state data structure for Svelte 5
const { app_state, reactive_counters } = await fetch(`${config.apiBaseUrl}/dev/mock/reactive-state`)
  .then(r => r.json());
```

**Test Token Generation**
```typescript
// Generate test tokens for authentication testing
const tokenResponse = await fetch(`${config.apiBaseUrl}/dev/auth/test-token`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    user_type: 'teacher',
    expires_minutes: 60,
    class_id: 'class-001'
  })
});

const { access_token, claims } = await tokenResponse.json();
```

**Development Headers**
Development mode includes debug headers:
```
X-HuleEdu-Environment: development
X-HuleEdu-Dev-Mode: enabled  
X-HuleEdu-CORS-Origins: http://localhost:5173,http://localhost:4173,http://localhost:3000
X-HuleEdu-Service: api-gateway-service
```

### Basic Authentication

**Quick Auth Test**
```typescript
// Test API connectivity
async function testConnection() {
  try {
    const response = await fetch(`${config.apiBaseUrl}/v1/test/no-auth`);
    const data = await response.json();
    console.log('API connected:', data);
  } catch (error) {
    console.error('API connection failed:', error);
  }
}
```

**JWT Token Storage**
```typescript
// For development - use localStorage
// For production - use httpOnly cookies
class TokenManager {
  static store(token: string): void {
    localStorage.setItem('huledu_token', token);
  }
  
  static retrieve(): string | null {
    return localStorage.getItem('huledu_token');
  }
  
  static clear(): void {
    localStorage.removeItem('huledu_token');
  }
}
```

---

## Store Architecture

### Complete API Client Store

```typescript
// src/lib/stores/api-client.svelte.ts
import { config } from '$lib/config';

interface User {
  id: string;
  email: string;
  role: 'teacher' | 'student';
  name: string;
}

class ApiClient {
  // Reactive state using $state()
  isAuthenticated = $state(false);
  isLoading = $state(false);
  user = $state<User | null>(null);
  error = $state<string | null>(null);

  private accessToken = $state<string | null>(null);
  
  // Derived state using $derived()
  authHeaders = $derived(() => ({
    'Authorization': this.accessToken ? `Bearer ${this.accessToken}` : '',
    'Content-Type': 'application/json',
    'X-Correlation-ID': crypto.randomUUID()
  }));

  isTeacher = $derived(this.user?.role === 'teacher');
  canUploadFiles = $derived(this.isAuthenticated && this.isTeacher);

  constructor() {
    this.loadStoredAuth();
  }

  private loadStoredAuth(): void {
    const token = TokenManager.retrieve();
    if (token && !this.isTokenExpired(token)) {
      this.accessToken = token;
      this.isAuthenticated = true;
      this.loadUserProfile();
    }
  }

  private isTokenExpired(token: string): boolean {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload.exp * 1000 < Date.now();
    } catch {
      return true;
    }
  }

  async login(email: string, password: string): Promise<boolean> {
    this.isLoading = true;
    this.error = null;
    
    try {
      const response = await fetch(`${config.apiBaseUrl}/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      if (!response.ok) {
        throw new Error('Invalid credentials');
      }
      
      const data = await response.json();
      this.accessToken = data.access_token;
      this.user = data.user;
      this.isAuthenticated = true;
      
      TokenManager.store(data.access_token);
      return true;
    } catch (error) {
      this.error = error instanceof Error ? error.message : 'Login failed';
      return false;
    } finally {
      this.isLoading = false;
    }
  }

  private async loadUserProfile(): Promise<void> {
    try {
      const response = await fetch(`${config.apiBaseUrl}/v1/auth/profile`, {
        headers: this.authHeaders
      });
      
      if (response.ok) {
        this.user = await response.json();
      }
    } catch (error) {
      console.error('Failed to load user profile:', error);
    }
  }

  logout(): void {
    this.isAuthenticated = false;
    this.user = null;
    this.accessToken = null;
    this.error = null;
    TokenManager.clear();
  }

  // API Methods
  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${config.apiBaseUrl}${endpoint}`, {
      ...options,
      headers: { ...this.authHeaders, ...options.headers }
    });

    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }

    return response.json();
  }

  async createBatch(fileCount: number): Promise<{ batch_id: string }> {
    return this.request('/v1/batches', {
      method: 'POST',
      body: JSON.stringify({ file_count: fileCount })
    });
  }

  async getBatchStatus(batchId: string): Promise<any> {
    return this.request(`/v1/batches/${batchId}/status`);
  }

  async processBatch(batchId: string): Promise<void> {
    return this.request(`/v1/batches/${batchId}/process`, {
      method: 'POST'
    });
  }
}

export const apiClient = new ApiClient();
```

### WebSocket Manager Store

```typescript
// src/lib/stores/websocket.svelte.ts
import { apiClient } from './api-client.svelte';
import { config } from '$lib/config';

interface TeacherNotification {
  notification_id: string;
  notification_type: string;
  category: string;
  priority: 'critical' | 'immediate' | 'high' | 'standard' | 'low';
  title: string;
  message: string;
  timestamp: string;
  batch_id?: string;
  correlation_id: string;
  read: boolean;
  payload?: Record<string, any>;
}

class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  // Reactive state
  isConnected = $state(false);
  connectionError = $state<string | null>(null);
  notifications = $state<TeacherNotification[]>([]);
  
  // Derived state  
  unreadCount = $derived(() => 
    this.notifications.filter(n => !n.read).length
  );
  
  criticalNotifications = $derived(() =>
    this.notifications.filter(n => n.priority === 'critical' && !n.read)
  );

  async connect(): Promise<void> {
    if (!apiClient.isAuthenticated || !apiClient.accessToken) {
      throw new Error('Must be authenticated to connect WebSocket');
    }

    try {
      const wsUrl = `${config.wsBaseUrl}/ws?token=${encodeURIComponent(apiClient.accessToken)}`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.connectionError = null;
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          const notification: TeacherNotification = JSON.parse(event.data);
          this.handleNotification(notification);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      this.ws.onclose = (event) => {
        this.isConnected = false;
        if (event.code !== 1000 && event.code !== 1001) {
          this.attemptReconnect();
        }
      };

      this.ws.onerror = () => {
        this.connectionError = 'WebSocket connection error';
      };
    } catch (error) {
      this.connectionError = error instanceof Error ? error.message : 'Connection failed';
    }
  }

  private handleNotification(notification: TeacherNotification): void {
    // Add to notifications list (keep last 100)
    this.notifications = [notification, ...this.notifications.slice(0, 99)];

    // Show browser notification for high priority
    if (['critical', 'immediate'].includes(notification.priority)) {
      this.showBrowserNotification(notification);
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = 1000 * Math.pow(2, this.reconnectAttempts - 1);
      
      setTimeout(() => {
        this.connect().catch(console.error);
      }, Math.min(delay, 30000));
    }
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    this.isConnected = false;
  }

  markAsRead(notificationId: string): void {
    this.notifications = this.notifications.map(n => 
      n.notification_id === notificationId ? { ...n, read: true } : n
    );
  }

  clearAll(): void {
    this.notifications = [];
  }

  private showBrowserNotification(notification: TeacherNotification): void {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(notification.title, {
        body: notification.message,
        icon: '/favicon.ico',
        requireInteraction: notification.priority === 'critical'
      });
    }
  }
}

export const wsManager = new WebSocketManager();

// Auto-connect when authenticated
$effect(() => {
  if (apiClient.isAuthenticated && !wsManager.isConnected) {
    wsManager.connect();
  } else if (!apiClient.isAuthenticated && wsManager.isConnected) {
    wsManager.disconnect();
  }
});
```

### Batch Management Store

```typescript
// src/lib/stores/batch.svelte.ts
import { apiClient } from './api-client.svelte';
import { wsManager } from './websocket.svelte';

interface Batch {
  id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  created_at: string;
  updated_at: string;
  completed_at?: string;
  file_count: number;
  current_phase?: string;
  progress?: {
    percentage: number;
    phase: string;
    estimated_completion?: string;
  };
  error_message?: string;
}

class BatchStore {
  batches = $state<Batch[]>([]);
  isLoading = $state(false);
  error = $state<string | null>(null);

  // Derived state
  activeBatches = $derived(
    this.batches.filter(b => b.status === 'processing')
  );
  
  completedBatches = $derived(
    this.batches.filter(b => b.status === 'completed')
  );

  async loadBatches(): Promise<void> {
    if (!apiClient.isAuthenticated) return;

    this.isLoading = true;
    this.error = null;
    
    try {
      this.batches = await apiClient.request('/v1/batches');
    } catch (error) {
      this.error = error instanceof Error ? error.message : 'Failed to load batches';
    } finally {
      this.isLoading = false;
    }
  }

  async createBatch(fileCount: number): Promise<string | null> {
    try {
      const result = await apiClient.createBatch(fileCount);
      await this.loadBatches(); // Refresh list
      return result.batch_id;
    } catch (error) {
      this.error = error instanceof Error ? error.message : 'Failed to create batch';
      return null;
    }
  }

  // Auto-update from WebSocket notifications
  $effect(() => {
    const updateFromNotification = (notification: any) => {
      const batchIndex = this.batches.findIndex(b => b.id === notification.batch_id);
      if (batchIndex !== -1) {
        const batch = this.batches[batchIndex];
        
        switch (notification.notification_type) {
          case 'batch_processing_started':
            batch.status = 'processing';
            break;
          case 'batch_processing_completed':
            batch.status = 'completed';
            break;
          case 'batch_processing_failed':
            batch.status = 'failed';
            batch.error_message = notification.payload?.error_message;
            break;
        }
        
        // Trigger reactivity
        this.batches = [...this.batches];
      }
    };

    // Listen to WebSocket notifications
    wsManager.notifications.forEach(notification => {
      if (notification.batch_id) {
        updateFromNotification(notification);
      }
    });
  });
}

export const batchStore = new BatchStore();
```

---

## Components

### Login Component

```svelte
<!-- src/lib/components/Login.svelte -->
<script lang="ts">
  import { apiClient } from '$lib/stores/api-client.svelte';
  
  let email = $state('');
  let password = $state('');
  let showPassword = $state(false);

  async function handleLogin() {
    if (!email || !password) return;
    await apiClient.login(email, password);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !apiClient.isLoading) {
      handleLogin();
    }
  }
</script>

<div class="login-container">
  <form class="login-form" onsubmit|preventDefault={handleLogin}>
    <h2>Login to HuleEdu</h2>
    
    {#if apiClient.error}
      <div class="error">{apiClient.error}</div>
    {/if}
    
    <div class="form-group">
      <label for="email">Email</label>
      <input 
        id="email"
        type="email" 
        bind:value={email}
        placeholder="teacher@example.com"
        disabled={apiClient.isLoading}
        onkeydown={handleKeydown}
      />
    </div>
    
    <div class="form-group">
      <label for="password">Password</label>
      <div class="password-input">
        <input 
          id="password"
          type={showPassword ? 'text' : 'password'}
          bind:value={password}
          placeholder="Enter your password"
          disabled={apiClient.isLoading}
          onkeydown={handleKeydown}
        />
        <button 
          type="button" 
          onclick={() => showPassword = !showPassword}
          disabled={apiClient.isLoading}
        >
          {showPassword ? '👁️' : '👁️‍🗨️'}
        </button>
      </div>
    </div>
    
    <button 
      type="submit" 
      disabled={apiClient.isLoading || !email || !password}
      class="login-button"
    >
      {apiClient.isLoading ? 'Logging in...' : 'Login'}
    </button>
  </form>
</div>

<style>
  .login-container {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    padding: 1rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  }

  .login-form {
    background: white;
    padding: 2rem;
    border-radius: 8px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
    width: 100%;
    max-width: 400px;
  }

  .form-group {
    margin-bottom: 1rem;
  }

  .form-group label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 600;
  }

  .form-group input {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid #ddd;
    border-radius: 4px;
  }

  .password-input {
    position: relative;
  }

  .password-input button {
    position: absolute;
    right: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    cursor: pointer;
  }

  .login-button {
    width: 100%;
    background: #667eea;
    color: white;
    border: none;
    padding: 0.75rem;
    border-radius: 4px;
    cursor: pointer;
  }

  .login-button:disabled {
    background: #a0aec0;
    cursor: not-allowed;
  }

  .error {
    background: #fed7d7;
    color: #c53030;
    padding: 0.75rem;
    border-radius: 4px;
    margin-bottom: 1rem;
  }
</style>
```

### Batch Dashboard

```svelte
<!-- src/lib/components/BatchDashboard.svelte -->
<script lang="ts">
  import { batchStore } from '$lib/stores/batch.svelte';
  import { wsManager } from '$lib/stores/websocket.svelte';
  
  // Load batches on mount
  $effect(() => {
    batchStore.loadBatches();
  });
</script>

<div class="dashboard">
  <div class="header">
    <h2>Batch Dashboard</h2>
    <div class="status">
      <span class="ws-status" class:connected={wsManager.isConnected}>
        {wsManager.isConnected ? '🟢' : '🔴'} WebSocket
      </span>
      {#if wsManager.unreadCount > 0}
        <span class="notifications-badge">{wsManager.unreadCount}</span>
      {/if}
    </div>
  </div>

  <div class="stats">
    <div class="stat-card">
      <h3>Total Batches</h3>
      <p>{batchStore.batches.length}</p>
    </div>
    <div class="stat-card">
      <h3>Active</h3>
      <p>{batchStore.activeBatches.length}</p>
    </div>
    <div class="stat-card">
      <h3>Completed</h3>
      <p>{batchStore.completedBatches.length}</p>
    </div>
  </div>

  {#if batchStore.isLoading}
    <div class="loading">Loading batches...</div>
  {:else if batchStore.error}
    <div class="error">{batchStore.error}</div>
  {:else}
    <div class="batch-grid">
      {#each batchStore.batches as batch (batch.id)}
        <div class="batch-card" class:processing={batch.status === 'processing'}>
          <h3>Batch {batch.id}</h3>
          <p>Status: <span class="status-{batch.status}">{batch.status}</span></p>
          <p>Files: {batch.file_count}</p>
          <p>Created: {new Date(batch.created_at).toLocaleDateString()}</p>
          
          {#if batch.progress}
            <div class="progress">
              <div class="progress-bar">
                <div class="progress-fill" style="width: {batch.progress.percentage}%"></div>
              </div>
              <span>{batch.progress.percentage}% - {batch.progress.phase}</span>
            </div>
          {/if}
          
          {#if batch.error_message}
            <p class="error-text">{batch.error_message}</p>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .dashboard {
    padding: 1.5rem;
    max-width: 1200px;
    margin: 0 auto;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
  }

  .status {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .ws-status.connected {
    color: green;
  }

  .notifications-badge {
    background: red;
    color: white;
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
    font-size: 0.75rem;
  }

  .stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }

  .stat-card {
    background: white;
    padding: 1rem;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
    text-align: center;
  }

  .batch-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1rem;
  }

  .batch-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1rem;
  }

  .batch-card.processing {
    border-color: #3182ce;
  }

  .progress {
    margin-top: 0.5rem;
  }

  .progress-bar {
    width: 100%;
    height: 6px;
    background: #e2e8f0;
    border-radius: 3px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: #3182ce;
    transition: width 0.3s ease;
  }

  .status-processing { color: #3182ce; }
  .status-completed { color: #38a169; }
  .status-failed { color: #e53e3e; }

  .error-text {
    color: #e53e3e;
    font-size: 0.875rem;
    margin-top: 0.5rem;
  }

  .loading, .error {
    text-align: center;
    padding: 2rem;
  }

  .error {
    color: #e53e3e;
    background: #fed7d7;
    border-radius: 4px;
  }
</style>
```

### File Upload

```svelte
<!-- src/lib/components/FileUpload.svelte -->
<script lang="ts">
  import { apiClient } from '$lib/stores/api-client.svelte';
  
  const { 
    batchId,
    onComplete
  }: {
    batchId: string;
    onComplete?: (success: boolean) => void;
  } = $props();
  
  let files: FileList | null = $state(null);
  let uploading = $state(false);
  let uploadProgress = $state(0);
  let error = $state<string | null>(null);

  async function handleUpload() {
    if (!files || files.length === 0) return;
    
    uploading = true;
    error = null;
    uploadProgress = 0;

    try {
      const formData = new FormData();
      formData.append('batch_id', batchId);
      
      Array.from(files).forEach(file => {
        formData.append('files', file);
      });

      // Use XMLHttpRequest for progress tracking
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable) {
            uploadProgress = Math.round((event.loaded / event.total) * 100);
          }
        });

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve();
          } else {
            reject(new Error(`Upload failed: ${xhr.status}`));
          }
        });

        xhr.addEventListener('error', () => {
          reject(new Error('Network error'));
        });

        xhr.open('POST', `${apiClient.config.apiBaseUrl}/v1/files/batch`);
        Object.entries(apiClient.authHeaders).forEach(([key, value]) => {
          if (key !== 'Content-Type') {
            xhr.setRequestHeader(key, value);
          }
        });
        
        xhr.send(formData);
      });

      onComplete?.(true);
      files = null; // Reset
    } catch (err) {
      error = err instanceof Error ? err.message : 'Upload failed';
      onComplete?.(false);
    } finally {
      uploading = false;
      uploadProgress = 0;
    }
  }

  const fileList = $derived(files ? Array.from(files) : []);
  const totalSize = $derived(
    fileList.reduce((sum, file) => sum + file.size, 0)
  );

  function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
</script>

<div class="file-upload">
  <div class="upload-area">
    <input 
      type="file" 
      bind:files 
      multiple 
      accept=".txt,.pdf,.docx,.doc"
      disabled={uploading}
    />
    
    {#if fileList.length > 0}
      <div class="file-list">
        <p>{fileList.length} files selected ({formatFileSize(totalSize)})</p>
        {#each fileList as file}
          <div class="file-item">
            <span>{file.name}</span>
            <span>{formatFileSize(file.size)}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  {#if uploading}
    <div class="progress">
      <div class="progress-bar">
        <div class="progress-fill" style="width: {uploadProgress}%"></div>
      </div>
      <span>{uploadProgress}%</span>
    </div>
  {/if}

  {#if error}
    <div class="error">{error}</div>
  {/if}

  <button 
    onclick={handleUpload} 
    disabled={uploading || fileList.length === 0}
  >
    {uploading ? 'Uploading...' : 'Upload Files'}
  </button>
</div>

<style>
  .file-upload {
    border: 2px dashed #cbd5e0;
    border-radius: 8px;
    padding: 1.5rem;
  }

  .file-list {
    margin: 1rem 0;
  }

  .file-item {
    display: flex;
    justify-content: space-between;
    padding: 0.25rem 0;
    border-bottom: 1px solid #e2e8f0;
  }

  .progress {
    margin: 1rem 0;
  }

  .progress-bar {
    width: 100%;
    height: 8px;
    background: #e2e8f0;
    border-radius: 4px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: #48bb78;
    transition: width 0.3s ease;
  }

  .error {
    background: #fed7d7;
    color: #c53030;
    padding: 0.75rem;
    border-radius: 4px;
    margin: 1rem 0;
  }

  button {
    background: #4299e1;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 4px;
    cursor: pointer;
  }

  button:disabled {
    background: #a0aec0;
    cursor: not-allowed;
  }
</style>
```

### Notification Center

```svelte
<!-- src/lib/components/NotificationCenter.svelte -->
<script lang="ts">
  import { wsManager } from '$lib/stores/websocket.svelte';
  
  function formatTime(timestamp: string): string {
    return new Date(timestamp).toLocaleTimeString();
  }

  function handleMarkAsRead(notificationId: string) {
    wsManager.markAsRead(notificationId);
  }

  function handleClearAll() {
    wsManager.clearAll();
  }
</script>

<div class="notification-center">
  <div class="header">
    <h3>Notifications</h3>
    <div class="actions">
      <span class="status" class:connected={wsManager.isConnected}>
        {wsManager.isConnected ? '🟢' : '🔴'}
      </span>
      {#if wsManager.notifications.length > 0}
        <button onclick={handleClearAll} class="clear-btn">Clear All</button>
      {/if}
    </div>
  </div>

  <div class="notification-list">
    {#each wsManager.notifications as notification (notification.notification_id)}
      <div 
        class="notification-item" 
        class:unread={!notification.read}
        class:critical={notification.priority === 'critical'}
      >
        <div class="notification-content">
          <div class="notification-title">{notification.title}</div>
          <div class="notification-message">{notification.message}</div>
          <div class="notification-meta">
            <span class="priority priority-{notification.priority}">
              {notification.priority}
            </span>
            <span class="time">{formatTime(notification.timestamp)}</span>
          </div>
        </div>
        
        {#if !notification.read}
          <button 
            onclick={() => handleMarkAsRead(notification.notification_id)}
            class="mark-read-btn"
          >
            ✓
          </button>
        {/if}
      </div>
    {/each}
    
    {#if wsManager.notifications.length === 0}
      <div class="no-notifications">No notifications</div>
    {/if}
  </div>
</div>

<style>
  .notification-center {
    max-width: 400px;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    background: white;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    border-bottom: 1px solid #e2e8f0;
  }

  .header h3 {
    margin: 0;
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .clear-btn {
    background: #e53e3e;
    color: white;
    border: none;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    cursor: pointer;
  }

  .notification-list {
    max-height: 400px;
    overflow-y: auto;
  }

  .notification-item {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 1rem;
    border-bottom: 1px solid #f7fafc;
  }

  .notification-item.unread {
    background: #ebf8ff;
    border-left: 4px solid #3182ce;
  }

  .notification-item.critical {
    border-left-color: #e53e3e !important;
    background: #fed7d7;
  }

  .notification-content {
    flex: 1;
  }

  .notification-title {
    font-weight: 600;
    margin-bottom: 0.25rem;
  }

  .notification-message {
    color: #4a5568;
    font-size: 0.875rem;
    margin-bottom: 0.5rem;
  }

  .notification-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .priority {
    padding: 0.125rem 0.375rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
  }

  .priority-critical { background: #fed7d7; color: #c53030; }
  .priority-immediate { background: #fef2f2; color: #dc2626; }
  .priority-high { background: #fef08a; color: #ca8a04; }
  .priority-standard { background: #e2e8f0; color: #4a5568; }
  .priority-low { background: #f0f9ff; color: #0369a1; }

  .time {
    font-size: 0.75rem;
    color: #718096;
  }

  .mark-read-btn {
    background: #48bb78;
    color: white;
    border: none;
    border-radius: 50%;
    width: 24px;
    height: 24px;
    cursor: pointer;
    font-size: 0.75rem;
  }

  .no-notifications {
    padding: 2rem;
    text-align: center;
    color: #a0aec0;
  }
</style>
```

---

## Production Deployment

### Error Handling

**Global Error Handler**
```typescript
// src/lib/utils/error-handler.ts
export class ErrorHandler {
  static async withRetry<T>(
    operation: () => Promise<T>,
    maxRetries: number = 3
  ): Promise<T> {
    let lastError: Error;
    
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await operation();
      } catch (error) {
        lastError = error as Error;
        
        if (attempt === maxRetries) break;
        
        // Exponential backoff
        const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
    
    throw lastError!;
  }

  static handleApiError(error: unknown): string {
    if (error instanceof Error) {
      return error.message;
    }
    return 'An unexpected error occurred';
  }
}
```

**Error Boundary Component**
```svelte
<!-- src/lib/components/ErrorBoundary.svelte -->
<script lang="ts">
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
  }
  
  function retry(): void {
    hasError = false;
    error = null;
  }
</script>

{#if hasError}
  {#if fallback}
    {@render fallback({ error, retry })}
  {:else}
    <div class="error-boundary">
      <h3>Something went wrong</h3>
      <p>{error?.message || 'An unexpected error occurred'}</p>
      <button onclick={retry}>Try Again</button>
    </div>
  {/if}
{:else}
  {@render children()}
{/if}

<style>
  .error-boundary {
    padding: 2rem;
    text-align: center;
    background: #fed7d7;
    border: 1px solid #fecaca;
    border-radius: 8px;
    color: #c53030;
  }

  button {
    background: #3182ce;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    margin-top: 1rem;
  }
</style>
```

### Performance Optimization

**Lazy Loading**
```typescript
// Lazy load components
const BatchDashboard = lazy(() => import('$lib/components/BatchDashboard.svelte'));
const FileUpload = lazy(() => import('$lib/components/FileUpload.svelte'));
```

**Debounced Search**
```typescript
// src/lib/utils/debounce.ts
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout;
  
  return (...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

// Usage in component
let searchTerm = $state('');
const debouncedSearch = debounce((term: string) => {
  // Perform search
}, 300);

$effect(() => {
  if (searchTerm) {
    debouncedSearch(searchTerm);
  }
});
```

### Security Considerations

**Token Security**
```typescript
// For production - use httpOnly cookies instead of localStorage
class SecureTokenManager {
  static async store(token: string): Promise<void> {
    // Set httpOnly cookie via server endpoint
    await fetch('/api/auth/set-cookie', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token })
    });
  }

  static async retrieve(): Promise<string | null> {
    // Cookie is sent automatically with requests
    try {
      const response = await fetch('/api/auth/verify');
      if (response.ok) {
        const { token } = await response.json();
        return token;
      }
    } catch (error) {
      console.error('Token retrieval failed:', error);
    }
    return null;
  }
}
```

**Input Sanitization**
```typescript
// Sanitize user inputs
export function sanitizeInput(input: string): string {
  return input
    .trim()
    .replace(/[<>\"'&]/g, (match) => {
      const entities: Record<string, string> = {
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '&': '&amp;'
      };
      return entities[match];
    });
}
```

**CSRF Protection**
```typescript
// Include CSRF token in requests
function getCsrfToken(): string {
  return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

// Add to request headers
headers: {
  ...apiClient.authHeaders,
  'X-CSRF-Token': getCsrfToken()
}
```

---

## Complete App Example

```svelte
<!-- src/App.svelte -->
<script lang="ts">
  import { apiClient } from '$lib/stores/api-client.svelte';
  import Login from '$lib/components/Login.svelte';
  import BatchDashboard from '$lib/components/BatchDashboard.svelte';
  import NotificationCenter from '$lib/components/NotificationCenter.svelte';
  import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';
</script>

<main>
  <ErrorBoundary>
    {#if apiClient.isAuthenticated}
      <div class="app-layout">
        <header class="app-header">
          <h1>HuleEdu Dashboard</h1>
          <div class="user-menu">
            <span>Welcome, {apiClient.user?.name}</span>
            <button onclick={apiClient.logout}>Logout</button>
          </div>
        </header>
        
        <div class="app-content">
          <div class="main-content">
            <BatchDashboard />
          </div>
          
          <aside class="sidebar">
            <NotificationCenter />
          </aside>
        </div>
      </div>
    {:else}
      <Login />
    {/if}
  </ErrorBoundary>
</main>

<style>
  .app-layout {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .app-header {
    background: #2d3748;
    color: white;
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .user-menu {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .user-menu button {
    background: #4a5568;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
  }

  .app-content {
    flex: 1;
    display: flex;
    gap: 1rem;
  }

  .main-content {
    flex: 1;
  }

  .sidebar {
    width: 400px;
    padding: 1rem;
  }

  @media (max-width: 768px) {
    .app-content {
      flex-direction: column;
    }
    
    .sidebar {
      width: 100%;
    }
  }
</style>
```

This guide provides everything needed to build a complete Svelte 5 integration with HuleEdu services, from basic authentication to production deployment.
