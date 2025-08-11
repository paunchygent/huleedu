# Frontend Framework Examples Guide

Comprehensive Svelte 5 integration patterns and examples for HuleEdu frontend applications using runes syntax.

## Overview

This guide provides production-ready Svelte 5 examples demonstrating integration with HuleEdu services using modern runes syntax (`$state()`, `$derived()`, `$effect()`, `$props()`).

## Authentication Integration

### Token Management Store

```typescript
// lib/stores/auth.svelte.ts
import { TokenManager } from '../auth/TokenManager';

class AuthStore {
  private tokenManager = new TokenManager();
  
  // Reactive state using $state()
  isAuthenticated = $state(false);
  user = $state<User | null>(null);
  token = $state<string | null>(null);
  
  // Derived state using $derived()
  isTeacher = $derived(this.user?.role === 'teacher');
  canUploadFiles = $derived(this.isAuthenticated && this.isTeacher);
  
  constructor() {
    this.initializeAuth();
  }
  
  private async initializeAuth(): Promise<void> {
    try {
      const token = await this.tokenManager.getValidToken();
      if (token) {
        this.token = token;
        this.isAuthenticated = true;
        this.user = await this.fetchUserProfile();
      }
    } catch (error) {
      console.error('Auth initialization failed:', error);
    }
  }
  
  async login(credentials: LoginCredentials): Promise<boolean> {
    try {
      const response = await this.tokenManager.authenticate(credentials);
      this.token = response.token;
      this.user = response.user;
      this.isAuthenticated = true;
      return true;
    } catch (error) {
      console.error('Login failed:', error);
      return false;
    }
  }
  
  async logout(): Promise<void> {
    await this.tokenManager.clearToken();
    this.token = null;
    this.user = null;
    this.isAuthenticated = false;
  }
  
  private async fetchUserProfile(): Promise<User> {
    const response = await fetch('/api/v1/auth/profile', {
      headers: await this.tokenManager.createAuthHeaders()
    });
    return await response.json();
  }
}

export const authStore = new AuthStore();
```

### Login Component

```svelte
<!-- Login.svelte -->
<script lang="ts">
  import { authStore } from '$lib/stores/auth.svelte';
  
  let credentials = $state({
    email: '',
    password: ''
  });
  
  let isLoading = $state(false);
  let error = $state<string | null>(null);
  
  // Derived validation
  const isValid = $derived(
    credentials.email.includes('@') && 
    credentials.password.length >= 8
  );
  
  async function handleSubmit(): Promise<void> {
    if (!isValid) return;
    
    isLoading = true;
    error = null;
    
    try {
      const success = await authStore.login(credentials);
      if (!success) {
        error = 'Invalid credentials';
      }
    } catch (err) {
      error = 'Login failed. Please try again.';
    } finally {
      isLoading = false;
    }
  }
</script>

<form onsubmit|preventDefault={handleSubmit}>
  <div class="form-group">
    <label for="email">Email</label>
    <input
      id="email"
      type="email"
      bind:value={credentials.email}
      required
    />
  </div>
  
  <div class="form-group">
    <label for="password">Password</label>
    <input
      id="password"
      type="password"
      bind:value={credentials.password}
      required
    />
  </div>
  
  {#if error}
    <div class="error">{error}</div>
  {/if}
  
  <button type="submit" disabled={!isValid || isLoading}>
    {isLoading ? 'Logging in...' : 'Login'}
  </button>
</form>
```

## Batch Management Integration

### Batch Store with Real-time Updates

```typescript
// lib/stores/batches.svelte.ts
import { wsNotificationStore } from './websocket.svelte';
import type { Batch, BatchStatus } from '../types/batch';

class BatchStore {
  // Reactive state
  batches = $state<Batch[]>([]);
  selectedBatch = $state<Batch | null>(null);
  isLoading = $state(false);
  
  // Derived state
  activeBatches = $derived(
    this.batches.filter(b => b.status === 'processing')
  );
  
  completedBatches = $derived(
    this.batches.filter(b => b.status === 'completed')
  );
  
  batchCount = $derived(this.batches.length);
  
  constructor() {
    this.setupRealtimeUpdates();
  }
  
  private setupRealtimeUpdates(): void {
    // Listen for batch-related notifications
    wsNotificationStore.addEventListener('message', (event) => {
      const notification = event.detail;
      
      if (notification.batch_id) {
        this.updateBatchFromNotification(notification);
      }
    });
  }
  
  private updateBatchFromNotification(notification: any): void {
    const batchIndex = this.batches.findIndex(b => b.id === notification.batch_id);
    
    if (batchIndex >= 0) {
      const batch = this.batches[batchIndex];
      
      switch (notification.notification_type) {
        case 'batch_processing_started':
          batch.status = 'processing';
          batch.current_phase = notification.payload.pipeline_phase;
          break;
          
        case 'batch_processing_completed':
          batch.status = 'completed';
          batch.completed_at = new Date().toISOString();
          break;
          
        case 'batch_processing_failed':
          batch.status = 'failed';
          batch.error_message = notification.payload.error_message;
          break;
      }
      
      // Trigger reactivity
      this.batches = [...this.batches];
    }
  }
  
  async loadBatches(): Promise<void> {
    this.isLoading = true;
    try {
      const response = await fetch('/api/v1/batches', {
        headers: await createAuthHeaders()
      });
      this.batches = await response.json();
    } catch (error) {
      console.error('Failed to load batches:', error);
    } finally {
      this.isLoading = false;
    }
  }
  
  async createBatch(files: File[]): Promise<string | null> {
    try {
      const response = await fetch('/api/v1/batches', {
        method: 'POST',
        headers: await createAuthHeaders(),
        body: JSON.stringify({ file_count: files.length })
      });
      
      const batch = await response.json();
      this.batches = [batch, ...this.batches];
      return batch.id;
    } catch (error) {
      console.error('Failed to create batch:', error);
      return null;
    }
  }
  
  selectBatch(batch: Batch): void {
    this.selectedBatch = batch;
  }
}

export const batchStore = new BatchStore();
```

### Batch Dashboard Component

```svelte
<!-- BatchDashboard.svelte -->
<script lang="ts">
  import { batchStore } from '$lib/stores/batches.svelte';
  import { wsNotificationStore } from '$lib/stores/websocket.svelte';
  import BatchCard from './BatchCard.svelte';
  
  // Load batches on mount
  $effect(() => {
    batchStore.loadBatches();
    wsNotificationStore.connect();
    
    // Cleanup on destroy
    return () => {
      wsNotificationStore.disconnect();
    };
  });
  
  function getStatusColor(status: string): string {
    const colors = {
      'pending': 'text-yellow-600',
      'processing': 'text-blue-600',
      'completed': 'text-green-600',
      'failed': 'text-red-600'
    };
    return colors[status] || 'text-gray-600';
  }
</script>

<div class="dashboard">
  <div class="header">
    <h1>Batch Dashboard</h1>
    
    <div class="stats">
      <div class="stat">
        <span class="label">Total Batches</span>
        <span class="value">{batchStore.batchCount}</span>
      </div>
      
      <div class="stat">
        <span class="label">Active</span>
        <span class="value text-blue-600">{batchStore.activeBatches.length}</span>
      </div>
      
      <div class="stat">
        <span class="label">Completed</span>
        <span class="value text-green-600">{batchStore.completedBatches.length}</span>
      </div>
    </div>
    
    <div class="connection-status">
      <span class="status-indicator" class:connected={wsNotificationStore.isConnected}></span>
      <span>{wsNotificationStore.connectionState}</span>
      
      {#if wsNotificationStore.hasUnread}
        <span class="notification-badge">{wsNotificationStore.unreadCount}</span>
      {/if}
    </div>
  </div>
  
  <div class="batch-grid">
    {#if batchStore.isLoading}
      <div class="loading">Loading batches...</div>
    {:else if batchStore.batches.length === 0}
      <div class="empty-state">
        <p>No batches found. Upload some files to get started.</p>
      </div>
    {:else}
      {#each batchStore.batches as batch (batch.id)}
        <BatchCard 
          {batch}
          onclick={() => batchStore.selectBatch(batch)}
        />
      {/each}
    {/if}
  </div>
</div>

<style>
  .dashboard {
    padding: 2rem;
    max-width: 1200px;
    margin: 0 auto;
  }
  
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .stats {
    display: flex;
    gap: 2rem;
  }
  
  .stat {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  
  .label {
    font-size: 0.875rem;
    color: #6b7280;
  }
  
  .value {
    font-size: 1.5rem;
    font-weight: 600;
    color: #374151;
  }
  
  .connection-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
  }
  
  .status-indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ef4444;
  }
  
  .status-indicator.connected {
    background: #10b981;
  }
  
  .notification-badge {
    background: #3b82f6;
    color: white;
    border-radius: 50%;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    min-width: 1.5rem;
    text-align: center;
  }
  
  .batch-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.5rem;
  }
  
  .loading,
  .empty-state {
    grid-column: 1 / -1;
    text-align: center;
    padding: 3rem;
    color: #6b7280;
  }
</style>
```

## File Upload Integration

### Upload Progress Component

```svelte
<!-- UploadProgress.svelte -->
<script lang="ts">
  import { fileUploadStore } from '$lib/stores/fileUpload.svelte';
  
  const { 
    batchId,
    onComplete 
  }: {
    batchId: string;
    onComplete?: (success: boolean) => void;
  } = $props();
  
  // Derived progress calculations
  const progressPercentage = $derived(
    fileUploadStore.uploadProgress?.percentage ?? 0
  );
  
  const estimatedTimeRemaining = $derived(() => {
    const progress = fileUploadStore.uploadProgress;
    if (!progress?.remainingTime) return null;
    
    const minutes = Math.floor(progress.remainingTime / 60);
    const seconds = Math.round(progress.remainingTime % 60);
    
    if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    }
    return `${seconds}s`;
  });
  
  const uploadSpeed = $derived(() => {
    const progress = fileUploadStore.uploadProgress;
    return progress?.speed ? fileUploadStore.formatSpeed(progress.speed) : null;
  });
  
  // Auto-start upload when files are selected
  $effect(() => {
    if (fileUploadStore.canUpload && batchId) {
      fileUploadStore.uploadFiles(batchId).then((success) => {
        onComplete?.(success);
      });
    }
  });
</script>

{#if fileUploadStore.isUploading && fileUploadStore.uploadProgress}
  <div class="upload-progress">
    <div class="progress-header">
      <h3>Uploading Files</h3>
      <span class="percentage">{progressPercentage}%</span>
    </div>
    
    <div class="progress-bar">
      <div 
        class="progress-fill" 
        style="width: {progressPercentage}%"
      ></div>
    </div>
    
    <div class="progress-details">
      <div class="file-info">
        {fileUploadStore.formatFileSize(fileUploadStore.uploadProgress.loaded)} / 
        {fileUploadStore.formatFileSize(fileUploadStore.uploadProgress.total)}
      </div>
      
      {#if uploadSpeed}
        <div class="speed">{uploadSpeed}</div>
      {/if}
      
      {#if estimatedTimeRemaining}
        <div class="time-remaining">{estimatedTimeRemaining} remaining</div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .upload-progress {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1.5rem;
    margin: 1rem 0;
  }
  
  .progress-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }
  
  .progress-header h3 {
    margin: 0;
    color: #374151;
  }
  
  .percentage {
    font-weight: 600;
    color: #3b82f6;
  }
  
  .progress-bar {
    width: 100%;
    height: 8px;
    background: #e5e7eb;
    border-radius: 4px;
    overflow: hidden;
    margin-bottom: 1rem;
  }
  
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #1d4ed8);
    transition: width 0.3s ease;
  }
  
  .progress-details {
    display: flex;
    justify-content: space-between;
    font-size: 0.875rem;
    color: #6b7280;
  }
</style>
```

## Advanced Patterns

### Reactive Form Validation

```svelte
<!-- EssayUploadForm.svelte -->
<script lang="ts">
  import { fileUploadStore } from '$lib/stores/fileUpload.svelte';
  import { batchStore } from '$lib/stores/batches.svelte';
  
  let formData = $state({
    title: '',
    description: '',
    dueDate: '',
    classId: ''
  });
  
  let isSubmitting = $state(false);
  
  // Comprehensive form validation
  const validation = $derived(() => {
    const errors: string[] = [];
    const warnings: string[] = [];
    
    if (!formData.title.trim()) {
      errors.push('Title is required');
    } else if (formData.title.length < 3) {
      warnings.push('Title should be at least 3 characters');
    }
    
    if (!formData.classId) {
      errors.push('Please select a class');
    }
    
    if (!fileUploadStore.hasFiles) {
      errors.push('Please select files to upload');
    }
    
    const dueDateObj = new Date(formData.dueDate);
    if (formData.dueDate && dueDateObj < new Date()) {
      warnings.push('Due date is in the past');
    }
    
    return {
      isValid: errors.length === 0,
      errors,
      warnings
    };
  });
  
  const canSubmit = $derived(
    validation.isValid && 
    fileUploadStore.canUpload && 
    !isSubmitting
  );
  
  async function handleSubmit(): Promise<void> {
    if (!canSubmit) return;
    
    isSubmitting = true;
    
    try {
      // Create batch
      const batchId = await batchStore.createBatch(fileUploadStore.selectedFiles);
      if (!batchId) throw new Error('Failed to create batch');
      
      // Upload files
      const uploadSuccess = await fileUploadStore.uploadFiles(batchId);
      if (!uploadSuccess) throw new Error('File upload failed');
      
      // Navigate to batch processing page
      window.location.href = `/batches/${batchId}/processing`;
      
    } catch (error) {
      console.error('Form submission failed:', error);
    } finally {
      isSubmitting = false;
    }
  }
</script>

<form onsubmit|preventDefault={handleSubmit}>
  <div class="form-section">
    <h2>Batch Information</h2>
    
    <div class="form-group">
      <label for="title">Title *</label>
      <input
        id="title"
        type="text"
        bind:value={formData.title}
        placeholder="Enter batch title"
        required
      />
    </div>
    
    <div class="form-group">
      <label for="description">Description</label>
      <textarea
        id="description"
        bind:value={formData.description}
        placeholder="Optional description"
        rows="3"
      ></textarea>
    </div>
    
    <div class="form-row">
      <div class="form-group">
        <label for="class">Class *</label>
        <select id="class" bind:value={formData.classId} required>
          <option value="">Select a class</option>
          <option value="class-1">English 101</option>
          <option value="class-2">Writing Workshop</option>
        </select>
      </div>
      
      <div class="form-group">
        <label for="due-date">Due Date</label>
        <input
          id="due-date"
          type="datetime-local"
          bind:value={formData.dueDate}
        />
      </div>
    </div>
  </div>
  
  <!-- Validation Messages -->
  {#if validation.errors.length > 0}
    <div class="validation-errors">
      <h4>Please fix the following errors:</h4>
      <ul>
        {#each validation.errors as error}
          <li>{error}</li>
        {/each}
      </ul>
    </div>
  {/if}
  
  {#if validation.warnings.length > 0}
    <div class="validation-warnings">
      <h4>Warnings:</h4>
      <ul>
        {#each validation.warnings as warning}
          <li>{warning}</li>
        {/each}
      </ul>
    </div>
  {/if}
  
  <div class="form-actions">
    <button type="button" onclick={() => fileUploadStore.clearFiles()}>
      Clear Files
    </button>
    
    <button type="submit" disabled={!canSubmit}>
      {isSubmitting ? 'Creating Batch...' : 'Create Batch & Upload'}
    </button>
  </div>
</form>
```

## Production Considerations

### Error Boundaries & Monitoring

```svelte
<!-- App.svelte -->
<script lang="ts">
  import { productionStore } from '$lib/stores/production.svelte';
  import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';
  import { authStore } from '$lib/stores/auth.svelte';
  
  // Global error monitoring
  $effect(() => {
    const handleUnhandledError = (event: ErrorEvent) => {
      productionStore.addError(new Error(event.message));
    };
    
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      productionStore.addError(new Error(event.reason));
    };
    
    window.addEventListener('error', handleUnhandledError);
    window.addEventListener('unhandledrejection', handleUnhandledRejection);
    
    return () => {
      window.removeEventListener('error', handleUnhandledError);
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    };
  });
  
  // Initialize authentication
  $effect(() => {
    authStore.initializeAuth();
  });
</script>

<ErrorBoundary>
  <main>
    {#if authStore.isAuthenticated}
      <slot />
    {:else}
      <div class="login-required">
        <h1>Please log in to continue</h1>
        <a href="/login">Go to Login</a>
      </div>
    {/if}
  </main>
</ErrorBoundary>
```

### Performance Optimization

```typescript
// lib/utils/performance.svelte.ts
import { tick } from 'svelte';

// Debounced reactive updates
export function createDebouncedState<T>(initialValue: T, delay: number = 300) {
  let value = $state(initialValue);
  let debouncedValue = $state(initialValue);
  let timeoutId: NodeJS.Timeout;
  
  $effect(() => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => {
      debouncedValue = value;
    }, delay);
    
    return () => clearTimeout(timeoutId);
  });
  
  return {
    get value() { return value; },
    set value(newValue: T) { value = newValue; },
    get debouncedValue() { return debouncedValue; }
  };
}

// Virtual scrolling for large lists
export class VirtualList {
  items = $state<any[]>([]);
  visibleItems = $state<any[]>([]);
  scrollTop = $state(0);
  itemHeight = 50;
  containerHeight = 400;
  
  constructor(items: any[]) {
    this.items = items;
    this.updateVisibleItems();
  }
  
  private updateVisibleItems = $derived(() => {
    const startIndex = Math.floor(this.scrollTop / this.itemHeight);
    const endIndex = Math.min(
      startIndex + Math.ceil(this.containerHeight / this.itemHeight) + 1,
      this.items.length
    );
    
    this.visibleItems = this.items.slice(startIndex, endIndex).map((item, index) => ({
      ...item,
      index: startIndex + index,
      top: (startIndex + index) * this.itemHeight
    }));
  });
  
  handleScroll(event: Event): void {
    const target = event.target as HTMLElement;
    this.scrollTop = target.scrollTop;
  }
}
```

This comprehensive Svelte 5 framework examples guide demonstrates production-ready patterns using modern runes syntax throughout, focusing exclusively on Svelte 5 without any React or other framework dependencies.
