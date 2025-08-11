# Svelte 5 Integration Examples for HuleEdu API

## Overview

This document provides **Svelte 5** examples using the new **runes system** for integrating with the HuleEdu API Gateway. All core API patterns from the main integration guide apply - these examples show modern Svelte 5 implementation patterns.

> **Note**: For Svelte 4 legacy syntax, see the migration section at the bottom.

## SvelteKit Setup

### API Client Store (Svelte 5)

```typescript
// src/lib/stores/api-client.svelte.ts
import type { 
  BatchStatusResponse, 
  ClientBatchPipelineRequest, 
  AuthResponse
} from '../../docs/api-types';

class ApiClient {
  private baseUrl = 'http://localhost:4001/v1';
  
  // Svelte 5 runes
  accessToken = $state<string | null>(null);
  isAuthenticated = $state(false);
  user = $state<any>(null);
  isLoading = $state(false);
  error = $state<string | null>(null);

  constructor() {
    // Load token from localStorage on initialization
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token');
      if (token) {
        this.accessToken = token;
        this.isAuthenticated = true;
      }
    }
  }

  // Derived state
  authHeaders = $derived(() => ({
    'Authorization': this.accessToken ? `Bearer ${this.accessToken}` : '',
    'Content-Type': 'application/json'
  }));

  async login(email: string, password: string): Promise<boolean> {
    this.isLoading = true;
    this.error = null;

    try {
      const response = await fetch(`${this.baseUrl}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      if (!response.ok) throw new Error('Login failed');

      const data: AuthResponse = await response.json();
      this.accessToken = data.access_token;
      this.user = data.user;
      this.isAuthenticated = true;
      localStorage.setItem('access_token', data.access_token);
      return true;
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Login failed';
      return false;
    } finally {
      this.isLoading = false;
    }
  }

  logout() {
    this.accessToken = null;
    this.user = null;
    this.isAuthenticated = false;
    this.error = null;
    localStorage.removeItem('access_token');
  }

  async createBatch(request: ClientBatchPipelineRequest): Promise<BatchStatusResponse | null> {
    this.isLoading = true;
    this.error = null;

    try {
      const response = await fetch(`${this.baseUrl}/batches`, {
        method: 'POST',
        headers: this.authHeaders,
        body: JSON.stringify(request)
      });

      if (!response.ok) throw new Error('Failed to create batch');
      return await response.json();
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to create batch';
      return null;
    } finally {
      this.isLoading = false;
    }
  }

  async getBatchStatus(batchId: string): Promise<BatchStatusResponse | null> {
    try {
      const response = await fetch(`${this.baseUrl}/batches/${batchId}/status`, {
        headers: this.authHeaders
      });

      if (!response.ok) throw new Error('Failed to get batch status');
      return await response.json();
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Failed to get batch status';
      return null;
    }
  }
}

export const apiClient = new ApiClient();
```

### WebSocket Manager (Svelte 5)

```typescript
// src/lib/stores/websocket.svelte.ts
import { apiClient } from './api-client.svelte';
import type { 
  TeacherNotification, 
  WebSocketMessage, 
  NotificationType, 
  NotificationPriority,
  WebSocketEventCategory 
} from '../types/websocket';

class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private messageHandlers = new Map<NotificationType, (notification: TeacherNotification) => void>();
  private categoryHandlers = new Map<WebSocketEventCategory, (notification: TeacherNotification) => void>();
  
  // Svelte 5 runes
  isConnected = $state(false);
  connectionState = $state<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
  notifications = $state<TeacherNotification[]>([]);
  connectionError = $state<string | null>(null);
  lastHeartbeat = $state<Date | null>(null);

  // Derived state
  unreadCount = $derived(() => 
    this.notifications.filter(n => !n.read).length
  );
  
  criticalNotifications = $derived(() =>
    this.notifications.filter(n => n.priority === 'critical' && !n.read)
  );

  async connect(): Promise<void> {
    if (!apiClient.isAuthenticated || !apiClient.accessToken) {
      this.connectionError = 'Not authenticated';
      throw new Error('Authentication required');
    }

    return new Promise((resolve, reject) => {
      try {
        this.connectionState = 'connecting';
        const wsUrl = `ws://localhost:8081/ws/?token=${encodeURIComponent(apiClient.accessToken!)}`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
          this.isConnected = true;
          this.connectionState = 'connected';
          this.connectionError = null;
          this.reconnectAttempts = 0;
          this.lastHeartbeat = new Date();
          console.log('WebSocket connected');
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event);
        };

        this.ws.onclose = (event) => {
          this.isConnected = false;
          this.connectionState = 'disconnected';
          console.log('WebSocket disconnected:', event.code, event.reason);
          
          // Handle different close codes
          if (event.code === 1008) {
            // Auth error
            this.connectionError = 'Authentication failed';
            this.connectionState = 'error';
            reject(new Error('Authentication failed'));
          } else if (event.code === 4000) {
            // Connection limit exceeded
            this.connectionError = 'Connection limit exceeded';
            this.connectionState = 'error';
          } else {
            this.attemptReconnect();
          }
        };

        this.ws.onerror = (error) => {
          this.connectionError = 'WebSocket connection error';
          this.connectionState = 'error';
          console.error('WebSocket error:', error);
          reject(error);
        };
      } catch (err) {
        this.connectionError = 'Failed to connect to WebSocket';
        this.connectionState = 'error';
        reject(err);
      }
    });
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const message: WebSocketMessage = JSON.parse(event.data);
      
      if (message.type === 'teacher_notification') {
        const notification = message.data;
        
        // Add unique ID and read status for UI
        const enrichedNotification = {
          ...notification,
          id: `${notification.correlation_id}-${Date.now()}`,
          read: false
        };
        
        // Add to notifications list
        this.notifications = [enrichedNotification, ...this.notifications.slice(0, 99)]; // Keep last 100
        
        // Call specific handlers
        const typeHandler = this.messageHandlers.get(notification.notification_type);
        if (typeHandler) {
          typeHandler(notification);
        }
        
        const categoryHandler = this.categoryHandlers.get(notification.category);
        if (categoryHandler) {
          categoryHandler(notification);
        }
        
        // Show browser notification for high priority
        if (notification.priority === 'critical' || notification.priority === 'immediate') {
          this.showBrowserNotification(notification);
        }
      }
    } catch (err) {
      console.error('Failed to parse WebSocket message:', err);
    }
  }

  private showBrowserNotification(notification: TeacherNotification): void {
    if ('Notification' in window && Notification.permission === 'granted') {
      const title = this.getNotificationTitle(notification);
      const body = this.formatNotificationMessage(notification);
      
      new Notification(title, {
        body,
        icon: '/favicon.ico',
        badge: '/badge-icon.png',
        tag: notification.correlation_id,
        requireInteraction: notification.priority === 'critical'
      });
    }
  }

  private getNotificationTitle(notification: TeacherNotification): string {
    switch (notification.category) {
      case 'batch_progress': return 'Batch Update';
      case 'processing_results': return 'Processing Complete';
      case 'file_operations': return 'File Operation';
      case 'class_management': return 'Class Update';
      case 'student_workflow': return 'Student Action Required';
      case 'system_alerts': return 'System Alert';
      default: return 'HuleEdu Notification';
    }
  }

  private formatNotificationMessage(notification: TeacherNotification): string {
    // Use the same formatting logic from the main integration guide
    const { notification_type, payload, batch_id, class_id } = notification;
    
    switch (notification_type) {
      case 'batch_files_uploaded':
        return `Files uploaded for batch ${batch_id} (${payload.file_count} files)`;
      case 'batch_processing_completed':
        return `Processing completed for batch ${batch_id}`;
      case 'student_matching_confirmation_required':
        return `Student matching requires confirmation for batch ${batch_id}`;
      case 'batch_results_ready':
        return `Results ready for batch ${batch_id} (${payload.essay_count} essays)`;
      default:
        return `${notification_type.replace(/_/g, ' ')}`;
    }
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.connectionError = 'Max reconnection attempts reached';
      this.connectionState = 'error';
      return;
    }
    
    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
    
    setTimeout(() => {
      this.connect().catch(console.error);
    }, delay);
  }

  // Register notification handlers
  onNotification(type: NotificationType, handler: (notification: TeacherNotification) => void): void {
    this.messageHandlers.set(type, handler);
  }

  onCategory(category: WebSocketEventCategory, handler: (notification: TeacherNotification) => void): void {
    this.categoryHandlers.set(category, handler);
  }

  // Request browser notification permission
  async requestNotificationPermission(): Promise<boolean> {
    if ('Notification' in window) {
      const permission = await Notification.requestPermission();
      return permission === 'granted';
    }
    return false;
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    this.isConnected = false;
    this.connectionState = 'disconnected';
  }

  markAsRead(notificationId: string): void {
    this.notifications = this.notifications.map(n => 
      n.id === notificationId ? { ...n, read: true } : n
    );
  }

  markAllAsRead(): void {
    this.notifications = this.notifications.map(n => ({ ...n, read: true }));
  }

  removeNotification(notificationId: string): void {
    this.notifications = this.notifications.filter(n => n.id !== notificationId);
  }

  clearAll(): void {
    this.notifications = [];
  }
}

export const wsManager = new WebSocketManager();
```

## Svelte Components

### Login Component (Svelte 5)

```svelte
<!-- src/routes/login/+page.svelte -->
<script lang="ts">
  import { apiClient } from '$lib/stores/api-client.svelte';
  import { wsManager } from '$lib/stores/websocket.svelte';
  import { goto } from '$app/navigation';
  
  let email = $state('');
  let password = $state('');
  let showPassword = $state(false);

  async function handleLogin() {
    const success = await apiClient.login(email, password);
    if (success) {
      wsManager.connect();
      goto('/dashboard');
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      handleLogin();
    }
  }
</script>

<div class="login-form">
  <h1>Login to HuleEdu</h1>
  
  <form on:submit|preventDefault={handleLogin}>
    <div class="field">
      <label for="username">Username</label>
      <input 
        id="username" 
        type="text" 
        bind:value={username} 
        required 
        disabled={loading}
      />
    </div>
    
    <div class="field">
      <label for="password">Password</label>
      <input 
        id="password" 
        type="password" 
        bind:value={password} 
        required 
        disabled={loading}
      />
    </div>
    
    {#if error}
      <div class="error">{error}</div>
    {/if}
    
    <button type="submit" disabled={loading}>
      {loading ? 'Logging in...' : 'Login'}
    </button>
  </form>
</div>

<style>
  .login-form {
    max-width: 400px;
    margin: 2rem auto;
    padding: 2rem;
    border: 1px solid #ddd;
    border-radius: 8px;
  }
  
  .field {
    margin-bottom: 1rem;
  }
  
  label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: bold;
  }
  
  input {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  
  .error {
    color: red;
    margin-bottom: 1rem;
  }
  
  button {
    width: 100%;
    padding: 0.75rem;
    background: #007bff;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  
  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
```

### Batch Status Component

```svelte
<!-- src/lib/components/BatchStatus.svelte -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { apiClient } from '$lib/stores/api';
  import type { BatchStatusResponse } from '../../docs/api-types';
  
  export let batchId: string;
  
  let status: BatchStatusResponse | null = null;
  let loading = true;
  let error = '';
  
  async function fetchStatus() {
    try {
      loading = true;
      const response = await apiClient.getBatchStatus(batchId);
      
      if (response.success && response.data) {
        status = response.data;
        error = '';
      } else {
        error = response.error?.detail || 'Failed to fetch status';
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Unknown error';
    } finally {
      loading = false;
    }
  }
  
  onMount(() => {
    fetchStatus();
    
    // Poll for updates every 5 seconds
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  });
</script>

<div class="batch-status">
  <h3>Batch Status: {batchId}</h3>
  
  {#if loading}
    <div class="loading">Loading...</div>
  {:else if error}
    <div class="error">
      Error: {error}
      <button on:click={fetchStatus}>Retry</button>
    </div>
  {:else if status}
    <div class="status-info">
      <div class="status-badge" class:processing={status.status === 'PROCESSING'}>
        {status.status}
      </div>
      
      <details>
        <summary>Status Details</summary>
        <pre>{JSON.stringify(status.details, null, 2)}</pre>
      </details>
    </div>
  {:else}
    <div class="no-data">No status available</div>
  {/if}
</div>

<style>
  .batch-status {
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 1rem;
    margin: 1rem 0;
  }
  
  .loading {
    text-align: center;
    color: #666;
  }
  
  .error {
    color: red;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .status-badge {
    display: inline-block;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    background: #e9ecef;
    font-weight: bold;
    margin-bottom: 1rem;
  }
  
  .status-badge.processing {
    background: #fff3cd;
    color: #856404;
  }
  
  pre {
    background: #f8f9fa;
    padding: 1rem;
    border-radius: 4px;
    overflow-x: auto;
  }
</style>
```

### File Upload Component

```svelte
<!-- src/lib/components/FileUpload.svelte -->
<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { apiClient } from '$lib/stores/api';
  
  export let batchId: string;
  
  const dispatch = createEventDispatcher();
  
  let files: FileList | null = null;
  let uploading = false;
  let progress = 0;
  let error = '';
  
  async function handleUpload() {
    if (!files || files.length === 0) {
      error = 'Please select files to upload';
      return;
    }
    
    const formData = new FormData();
    formData.append('batch_id', batchId);
    
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    
    try {
      uploading = true;
      error = '';
      progress = 0;
      
      // Upload with progress tracking
      const response = await uploadWithProgress(formData);
      
      if (response.success) {
        dispatch('upload-complete', response.data);
        files = null; // Reset file input
      } else {
        error = response.error?.detail || 'Upload failed';
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Upload failed';
    } finally {
      uploading = false;
      progress = 0;
    }
  }
  
  function uploadWithProgress(formData: FormData): Promise<any> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          progress = Math.round((event.loaded / event.total) * 100);
        }
      });
      
      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const response = JSON.parse(xhr.responseText);
            resolve({ success: true, data: response });
          } catch {
            resolve({ success: true, data: null });
          }
        } else {
          resolve({ 
            success: false, 
            error: { detail: `Upload failed with status ${xhr.status}` }
          });
        }
      });
      
      xhr.addEventListener('error', () => {
        reject(new Error('Upload failed due to network error'));
      });
      
      // Set auth header
      const token = localStorage.getItem('access_token');
      if (token) {
        xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      }
      
      xhr.open('POST', 'http://localhost:4001/v1/files/batch');
      xhr.send(formData);
    });
  }
</script>

<div class="file-upload">
  <h3>Upload Files</h3>
  
  <div class="upload-area">
    <input 
      type="file" 
      multiple 
      accept=".txt,.pdf,.docx"
      bind:files
      disabled={uploading}
    />
    
    {#if files && files.length > 0}
      <div class="file-list">
        <h4>Selected Files:</h4>
        {#each Array.from(files) as file}
          <div class="file-item">
            {file.name} ({(file.size / 1024 / 1024).toFixed(2)} MB)
          </div>
        {/each}
      </div>
    {/if}
    
    {#if error}
      <div class="error">{error}</div>
    {/if}
    
    {#if uploading}
      <div class="progress">
        <div class="progress-bar" style="width: {progress}%"></div>
        <span class="progress-text">{progress}%</span>
      </div>
    {/if}
    
    <button 
      on:click={handleUpload} 
      disabled={uploading || !files || files.length === 0}
    >
      {uploading ? 'Uploading...' : 'Upload Files'}
    </button>
  </div>
</div>

<style>
  .file-upload {
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 1rem;
    margin: 1rem 0;
  }
  
  .upload-area {
    text-align: center;
  }
  
  .file-list {
    margin: 1rem 0;
    text-align: left;
  }
  
  .file-item {
    padding: 0.25rem 0;
    border-bottom: 1px solid #eee;
  }
  
  .error {
    color: red;
    margin: 1rem 0;
  }
  
  .progress {
    position: relative;
    height: 20px;
    background: #f0f0f0;
    border-radius: 10px;
    margin: 1rem 0;
    overflow: hidden;
  }
  
  .progress-bar {
    height: 100%;
    background: #007bff;
    transition: width 0.3s ease;
  }
  
  .progress-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 0.8rem;
    font-weight: bold;
  }
  
  button {
    padding: 0.75rem 1.5rem;
    background: #007bff;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    margin-top: 1rem;
  }
  
  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
```

### Notification Component

```svelte
<!-- src/lib/components/NotificationCenter.svelte -->
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { notifications, wsClient, wsConnected } from '$lib/stores/websocket';
  import { authToken } from '$lib/stores/api';
  import type { TeacherNotification } from '../../docs/api-types';
  
  let unsubscribeAuth: () => void;
  let unsubscribeNotifications: () => void;
  
  onMount(() => {
    // Connect WebSocket when authenticated
    unsubscribeAuth = authToken.subscribe(token => {
      if (token) {
        wsClient.connect(token);
      } else {
        wsClient.disconnect();
      }
    });
    
    // Subscribe to notifications for UI updates
    unsubscribeNotifications = notifications.subscribe(items => {
      // Could trigger toast notifications here
      if (items.length > 0) {
        const latest = items[0];
        showToast(latest);
      }
    });
  });
  
  onDestroy(() => {
    if (unsubscribeAuth) unsubscribeAuth();
    if (unsubscribeNotifications) unsubscribeNotifications();
    wsClient.disconnect();
  });
  
  function showToast(notification: TeacherNotification) {
    // Simple toast implementation
    const toast = document.createElement('div');
    toast.className = `toast toast-${notification.priority.toLowerCase()}`;
    toast.textContent = formatNotification(notification);
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
      toast.remove();
    }, 5000);
  }
  
  function formatNotification(notification: TeacherNotification): string {
    switch (notification.notification_type) {
      case 'batch_processing_started':
        return `Batch processing started for batch ${notification.batch_id}`;
      case 'batch_processing_completed':
        return `Batch processing completed for batch ${notification.batch_id}`;
      default:
        return `Notification: ${notification.notification_type}`;
    }
  }
  
  function clearNotifications() {
    notifications.set([]);
  }
</script>

<div class="notification-center">
  <div class="header">
    <h3>Notifications</h3>
    <div class="status">
      <span class="connection-status" class:connected={$wsConnected}>
        {$wsConnected ? 'Connected' : 'Disconnected'}
      </span>
      {#if $notifications.length > 0}
        <button on:click={clearNotifications}>Clear All</button>
      {/if}
    </div>
  </div>
  
  <div class="notification-list">
    {#each $notifications as notification (notification.correlation_id)}
      <div class="notification-item" class:urgent={notification.priority === 'IMMEDIATE'}>
        <div class="notification-header">
          <span class="type">{notification.notification_type}</span>
          <span class="time">{new Date(notification.timestamp).toLocaleTimeString()}</span>
        </div>
        <div class="notification-content">
          {formatNotification(notification)}
        </div>
        {#if notification.action_required}
          <div class="action-required">Action Required</div>
        {/if}
      </div>
    {:else}
      <div class="no-notifications">No notifications</div>
    {/each}
  </div>
</div>

<style>
  .notification-center {
    max-width: 400px;
    border: 1px solid #ddd;
    border-radius: 8px;
    background: white;
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
  
  .notification-list {
    max-height: 400px;
    overflow-y: auto;
  }
  
  .notification-item {
    padding: 1rem;
    border-bottom: 1px solid #eee;
  }
  
  .notification-item.urgent {
    background: #fff3cd;
    border-left: 4px solid #ffc107;
  }
  
  .notification-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }
  
  .type {
    font-weight: bold;
    font-size: 0.9rem;
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
  
  /* Global toast styles */
  :global(.toast) {
    position: fixed;
    top: 20px;
    right: 20px;
    padding: 1rem;
    border-radius: 4px;
    color: white;
    z-index: 1000;
    animation: slideIn 0.3s ease;
  }
  
  :global(.toast-low) { background: #28a745; }
  :global(.toast-standard) { background: #17a2b8; }
  :global(.toast-high) { background: #ffc107; color: black; }
  :global(.toast-immediate) { background: #dc3545; }
  
  @keyframes slideIn {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }
</style>
```

## SvelteKit Layout

```svelte
<!-- src/routes/+layout.svelte -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { auth, isAuthenticated } from '$lib/stores/api';
  import NotificationCenter from '$lib/components/NotificationCenter.svelte';
  
  onMount(() => {
    // Check for existing authentication on app load
    auth.checkAuth();
  });
</script>

<div class="app">
  <header>
    <h1>HuleEdu Platform</h1>
    {#if $isAuthenticated}
      <nav>
        <a href="/dashboard">Dashboard</a>
        <a href="/batches">Batches</a>
        <a href="/classes">Classes</a>
        <button on:click={auth.logout}>Logout</button>
      </nav>
    {/if}
  </header>
  
  <main>
    <slot />
  </main>
  
  {#if $isAuthenticated}
    <aside class="notifications">
      <NotificationCenter />
    </aside>
  {/if}
</div>

<style>
  .app {
    display: grid;
    grid-template-areas: 
      "header header"
      "main notifications";
    grid-template-columns: 1fr 400px;
    min-height: 100vh;
  }
  
  header {
    grid-area: header;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 2rem;
    background: #f8f9fa;
    border-bottom: 1px solid #dee2e6;
  }
  
  main {
    grid-area: main;
    padding: 2rem;
  }
  
  .notifications {
    grid-area: notifications;
    padding: 2rem 1rem;
    background: #f8f9fa;
    border-left: 1px solid #dee2e6;
  }
  
  nav {
    display: flex;
    gap: 1rem;
    align-items: center;
  }
  
  nav a {
    text-decoration: none;
    color: #007bff;
    padding: 0.5rem 1rem;
    border-radius: 4px;
  }
  
  nav a:hover {
    background: #e9ecef;
  }
  
  nav button {
    padding: 0.5rem 1rem;
    background: #dc3545;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
</style>
```

## Key Differences from React

1. **Stores instead of Context**: Svelte stores provide reactive state management
2. **Reactive statements**: Use `$:` for computed values instead of `useMemo`
3. **Lifecycle functions**: `onMount`, `onDestroy` instead of `useEffect`
4. **Two-way binding**: `bind:value` for form inputs
5. **Event handling**: `on:click` instead of `onClick`
6. **Conditional rendering**: `{#if}` blocks instead of `&&` operators
7. **Loops**: `{#each}` blocks instead of `.map()`

## Svelte 5 vs Svelte 4 Reference

For developers migrating from Svelte 4, here are the key differences:

### Core Syntax Changes

| Svelte 4 | Svelte 5 | Use Case |
|----------|----------|----------|
| `let count = writable(0)` | `let count = $state(0)` | Reactive state |
| `$: doubled = $count * 2` | `let doubled = $derived(count * 2)` | Computed values |
| `onMount(() => {})` | `$effect(() => {})` | Side effects |
| `export let name` | `let { name } = $props()` | Component props |
| `on:click={handler}` | `onclick={handler}` | Event handlers |

### API Client Store (Svelte 5)

```typescript
// src/lib/stores/api-client.svelte.ts
class ApiClient {
  private baseUrl = 'http://localhost:4001/v1';
  
  // Svelte 5 runes
  isAuthenticated = $state(false);
  accessToken = $state<string | null>(null);
  user = $state<any>(null);
  isLoading = $state(false);
  error = $state<string | null>(null);

  // Derived state
  authHeaders = $derived(() => ({
    'Authorization': this.accessToken ? `Bearer ${this.accessToken}` : '',
    'Content-Type': 'application/json'
  }));

  constructor() {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token');
      if (token) {
        this.accessToken = token;
        this.isAuthenticated = true;
      }
    }
  }

  async login(email: string, password: string): Promise<boolean> {
    this.isLoading = true;
    this.error = null;
    // ... rest of login logic
  }
}

export const apiClient = new ApiClient();
```

### WebSocket Manager (Svelte 5)

```typescript
// src/lib/stores/websocket.svelte.ts
class WebSocketManager {
  private ws: WebSocket | null = null;
  
  isConnected = $state(false);
  notifications = $state<Notification[]>([]);
  connectionError = $state<string | null>(null);

  // Derived state
  unreadCount = $derived(() => 
    this.notifications.filter(n => !n.read).length
  );

  connect() {
    // ... WebSocket connection logic
  }
}

export const wsManager = new WebSocketManager();
```

### Component Example (Svelte 5)

```svelte
<!-- LoginForm.svelte -->
<script lang="ts">
  import { apiClient } from '$lib/stores/api-client.svelte';
  
  let email = $state('');
  let password = $state('');
  let showPassword = $state(false);

  async function handleLogin() {
    const success = await apiClient.login(email, password);
    if (success) {
      // Handle successful login
    }
  }
</script>

<form onsubmit|preventDefault={handleLogin}>
  <input
    type="email"
    bind:value={email}
    placeholder="Email"
    required
  />
  
  <input
    type={showPassword ? 'text' : 'password'}
    bind:value={password}
    placeholder="Password"
    required
  />
  
  <button
    type="button"
    onclick={() => showPassword = !showPassword}
  >
    {showPassword ? 'Hide' : 'Show'}
  </button>
  
  <button type="submit" disabled={apiClient.isLoading}>
    {apiClient.isLoading ? 'Signing in...' : 'Sign in'}
  </button>
</form>
```

### Tailwind CSS Integration

#### Setup

```bash
npm create svelte@latest huledu-frontend
cd huledu-frontend
npm install -D @tailwindcss/forms @tailwindcss/typography
```

#### Tailwind Config

```javascript
// tailwind.config.js
export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8'
        }
      }
    }
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography')
  ]
}
```

#### Styled Components

```svelte
<!-- Modern Login Form with Tailwind -->
<div class="min-h-screen flex items-center justify-center bg-gray-50">
  <div class="max-w-md w-full space-y-8">
    <h2 class="text-center text-3xl font-extrabold text-gray-900">
      Sign in to HuleEdu
    </h2>
    
    <form class="space-y-6" onsubmit|preventDefault={handleLogin}>
      <input
        type="email"
        bind:value={email}
        class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
        placeholder="Email address"
        required
      />
      
      <button
        type="submit"
        disabled={apiClient.isLoading}
        class="w-full py-2 px-4 bg-primary-600 hover:bg-primary-700 text-white font-medium rounded-md disabled:opacity-50 transition-colors"
      >
        {apiClient.isLoading ? 'Signing in...' : 'Sign in'}
      </button>
    </form>
  </div>
</div>
```

### Layout with Auto-WebSocket Connection

```svelte
<!-- src/routes/+layout.svelte -->
<script lang="ts">
  import '../app.css';
  import { apiClient } from '$lib/stores/api-client.svelte';
  import { wsManager } from '$lib/stores/websocket.svelte';
  
  // Auto-connect WebSocket when authenticated
  $effect(() => {
    if (apiClient.isAuthenticated && !wsManager.isConnected) {
      wsManager.connect();
    }
  });
</script>

<div class="min-h-screen bg-gray-50">
  {#if apiClient.isAuthenticated}
    <nav class="bg-white shadow">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex justify-between h-16">
          <h1 class="text-xl font-semibold text-gray-900">HuleEdu</h1>
          <button
            onclick={() => {
              apiClient.logout();
              wsManager.disconnect();
            }}
            class="text-red-600 hover:text-red-700"
          >
            Logout
          </button>
        </div>
      </div>
    </nav>
    <main class="max-w-7xl mx-auto py-6 px-4">
      <slot />
    </main>
  {:else}
    <slot />
  {/if}
</div>
```

### Migration Benefits

- **Performance**: Svelte 5 runes provide better performance and smaller bundle sizes
- **Developer Experience**: Simpler mental model, no store subscriptions to manage
- **TypeScript**: Better type inference with runes
- **Styling**: Tailwind provides utility-first CSS with excellent developer experience

### Backend Compatibility

**All HuleEdu backend integration remains identical:**

- API endpoints and authentication unchanged
- WebSocket connection patterns identical
- File upload and batch processing unchanged
- TypeScript types from `docs/api-types.ts` work with both versions

## Development Commands

```bash
# Create new SvelteKit project
npm create svelte@latest huledu-frontend
cd huledu-frontend
npm install

# Add TypeScript support (if not selected during creation)
npx svelte-add@latest typescript

# Install additional dependencies
npm install uuid
npm install -D @types/uuid

# Development server
npm run dev

# Build for production
npm run build
```

The core API integration patterns remain identical - only the component syntax and state management approach change for Svelte!
