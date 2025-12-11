---
id: "210-frontend-dashboard-rules"
type: "implementation"
created: 2025-08-17
last_updated: 2025-11-17
scope: "frontend"
---

# 210: Frontend Dashboard Rules

## 1. Dashboard Architecture

### 1.1. Teacher-Centric Design
- **Primary User**: Teachers monitoring batch processing and student work
- **Core Features**: Batch status, progress tracking, student association management
- **Real-Time**: WebSocket-driven updates for immediate status visibility
- **Responsive**: Desktop-first, mobile-compatible design

### 1.2. Dashboard Layout Structure
```
dashboard/
├── +layout.svelte          # Shared dashboard shell
├── +page.svelte            # Dashboard overview/home
├── batches/
│   ├── +page.svelte        # Batch list view
│   ├── [batch_id]/
│   │   ├── +page.svelte    # Batch detail view
│   │   └── status/         # Real-time status monitoring
├── classes/
│   ├── +page.svelte        # Class management
│   └── [class_id]/         # Individual class views
└── notifications/
    └── +page.svelte        # Notification center
```

## 2. Real-Time Data Patterns

### 2.1. Optimistic WebSocket Updates
```typescript
// WebSocket updates UI immediately, REST confirms
const batchStore = createBatchStore();

wsClient.subscribe('batch_pipeline_completed', (event) => {
  // Immediate UI update
  batchStore.updateBatch(event.batch_id, {
    status: event.final_status,
    updated_at: event.timestamp
  });
  
  // Background verification via REST API
  setTimeout(() => {
    apiClient.getBatchStatus(event.batch_id)
      .then(response => {
        // Reconcile any differences
        batchStore.updateBatch(event.batch_id, response);
      });
  }, 1000);
});
```

### 2.2. Status Consistency Management
```typescript
// Ensure REST/WebSocket status values match exactly
interface BatchStatusDisplay {
  status: BatchClientStatus;
  displayText: string;
  color: 'green' | 'blue' | 'yellow' | 'red' | 'gray';
  icon: string;
}

const STATUS_DISPLAY_MAP: Record<BatchClientStatus, BatchStatusDisplay> = {
  'pending_content': { 
    status: 'pending_content',
    displayText: 'Pending Content',
    color: 'gray',
    icon: 'clock'
  },
  'ready': {
    status: 'ready', 
    displayText: 'Ready to Process',
    color: 'blue',
    icon: 'play'
  },
  'processing': {
    status: 'processing',
    displayText: 'Processing',
    color: 'yellow', 
    icon: 'spinner'
  },
  'completed_successfully': {
    status: 'completed_successfully',
    displayText: 'Completed Successfully',
    color: 'green',
    icon: 'check'
  },
  'completed_with_failures': {
    status: 'completed_with_failures', 
    displayText: 'Completed with Issues',
    color: 'yellow',
    icon: 'warning'
  },
  'failed': {
    status: 'failed',
    displayText: 'Failed',
    color: 'red',
    icon: 'x'
  },
  'cancelled': {
    status: 'cancelled',
    displayText: 'Cancelled', 
    color: 'gray',
    icon: 'stop'
  }
};
```

## 3. Component Patterns

### 3.1. Batch Status Card Component
```typescript
interface BatchCardProps {
  batch: BatchData;
  onClick?: (batch: BatchData) => void;
  showDetails?: boolean;
}

// Component must handle all 7 status states consistently
export function BatchCard({ batch, onClick, showDetails = false }: BatchCardProps) {
  const statusDisplay = STATUS_DISPLAY_MAP[batch.status];
  
  return (
    <div class={`batch-card status-${statusDisplay.color}`}>
      <div class="status-indicator">
        <Icon name={statusDisplay.icon} />
        <span>{statusDisplay.displayText}</span>
      </div>
      {showDetails && (
        <BatchDetails {batch} />
      )}
    </div>
  );
}
```

### 3.2. Real-Time Progress Component
```typescript
// Progress tracking with WebSocket updates
export function BatchProgress({ batchId }: { batchId: string }) {
  let progress = $state<ProgressData | null>(null);
  
  $effect(() => {
    // Subscribe to progress updates
    const unsubscribe = wsClient.subscribe('batch_progress_update', (event) => {
      if (event.batch_id === batchId) {
        progress = event.progress;
      }
    });
    
    // Initial progress fetch
    apiClient.getBatchProgress(batchId).then(data => {
      progress = data;
    });
    
    return unsubscribe;
  });
  
  return (
    <div class="progress-container">
      {#if progress}
        <ProgressBar 
          value={progress.percentage} 
          max={100}
          label={`${progress.completed}/${progress.total} essays`}
        />
      {/if}
    </div>
  );
}
```

## 4. Notification Management

### 4.1. Notification Store Pattern
```typescript
interface NotificationData {
  id: string;
  type: 'batch_completed' | 'batch_failed' | 'student_validation_required';
  title: string;
  message: string;
  timestamp: Date;
  read: boolean;
  batchId?: string;
  classId?: string;
}

export function createNotificationStore() {
  let notifications = $state<NotificationData[]>([]);
  
  const addNotification = (notification: NotificationData) => {
    notifications = [notification, ...notifications].slice(0, 50); // Keep latest 50
  };
  
  const markAsRead = (notificationId: string) => {
    const notification = notifications.find(n => n.id === notificationId);
    if (notification) {
      notification.read = true;
    }
  };
  
  return {
    get notifications() { return notifications; },
    get unreadCount() { return notifications.filter(n => !n.read).length; },
    addNotification,
    markAsRead
  };
}
```

### 4.2. WebSocket Notification Integration
```typescript
// Auto-convert WebSocket events to UI notifications
wsClient.subscribe('teacher_notification_requested', (event) => {
  const notification: NotificationData = {
    id: event.correlation_id,
    type: event.notification_type,
    title: event.title,
    message: event.message,
    timestamp: new Date(event.timestamp),
    read: false,
    batchId: event.batch_id,
    classId: event.class_id
  };
  
  notificationStore.addNotification(notification);
  
  // Show toast for high-priority notifications
  if (event.priority === 'HIGH') {
    toast.success(notification.title, {
      action: {
        label: 'View',
        onClick: () => navigateToBatch(notification.batchId)
      }
    });
  }
});
```

## 5. Navigation Patterns

### 5.1. Context-Aware Navigation
```typescript
// Navigation that maintains context across views
export const dashboardNavigation = {
  // Preserve selected batch/class across route changes
  selectedBatch: $state<string | null>(null),
  selectedClass: $state<string | null>(null),
  
  navigateToBatch(batchId: string) {
    this.selectedBatch = batchId;
    goto(`/dashboard/batches/${batchId}`);
  },
  
  navigateToClass(classId: string) {
    this.selectedClass = classId; 
    goto(`/dashboard/classes/${classId}`);
  }
};
```

### 5.2. Breadcrumb Component
```typescript
// Auto-generated breadcrumbs based on route and context
export function DashboardBreadcrumbs() {
  const page = $page;
  const breadcrumbs = $derived(() => {
    const segments = page.url.pathname.split('/').filter(Boolean);
    return segments.map((segment, index) => ({
      label: formatSegmentLabel(segment, index, segments),
      href: '/' + segments.slice(0, index + 1).join('/'),
      active: index === segments.length - 1
    }));
  });
  
  return (
    <nav class="breadcrumbs">
      {#each breadcrumbs as crumb}
        <BreadcrumbItem {crumb} />
      {/each}
    </nav>
  );
}
```

## 6. Data Loading Patterns

### 6.1. Progressive Loading
```typescript
// Load dashboard data progressively
export function useDashboardData() {
  let batches = $state<BatchData[]>([]);
  let classes = $state<ClassData[]>([]);
  let loading = $state({ batches: false, classes: false });
  
  // Load most critical data first (recent batches)
  $effect(() => {
    loading.batches = true;
    apiClient.getBatches({ limit: 10, sort: 'recent' })
      .then(data => { batches = data; })
      .finally(() => { loading.batches = false; });
  });
  
  // Load classes in background
  $effect(() => {
    setTimeout(() => {
      loading.classes = true;
      apiClient.getClasses()
        .then(data => { classes = data; })
        .finally(() => { loading.classes = false; });
    }, 100);
  });
  
  return { batches, classes, loading };
}
```

### 6.2. Error Boundary for Dashboard
```typescript
// Dashboard-specific error handling
export function DashboardErrorBoundary() {
  let error = $state<Error | null>(null);
  
  const handleDashboardError = (err: Error) => {
    console.error('Dashboard error:', err);
    error = err;
    
    // Show user-friendly error message
    toast.error('Dashboard temporarily unavailable', {
      action: {
        label: 'Retry',
        onClick: () => window.location.reload()
      }
    });
  };
  
  return { error, handleDashboardError };
}
```

## 7. Performance Optimization

### 7.1. Virtual Scrolling for Large Lists
```typescript
// Use virtual scrolling for batch/class lists > 100 items
import { VirtualList } from 'svelte-virtual-list';

export function BatchList({ batches }: { batches: BatchData[] }) {
  const itemHeight = 80; // Fixed item height for virtual scrolling
  
  return (
    <VirtualList
      items={batches}
      let:item
      {itemHeight}
    >
      <BatchCard batch={item} />
    </VirtualList>
  );
}
```

### 7.2. Smart WebSocket Subscriptions
```typescript
// Only subscribe to notifications for visible components
export function useVisibilityBasedSubscription(batchId: string) {
  let visible = $state(true);
  
  $effect(() => {
    // Subscribe only when component is visible
    if (visible) {
      const unsubscribe = wsClient.subscribe(`batch_${batchId}_updates`, handleUpdate);
      return unsubscribe;
    }
  });
  
  // Observe visibility changes
  $effect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    
    return () => observer.disconnect();
  });
}
```

## 8. Accessibility Standards

### 8.1. Screen Reader Support
- **Status Updates**: Announce status changes via aria-live regions
- **Progress**: Use proper progress bar semantics with aria-label
- **Navigation**: Implement skip links for keyboard users
- **Focus Management**: Maintain logical tab order across dashboard sections

### 8.2. Keyboard Navigation
```typescript
// Dashboard-wide keyboard shortcuts
export function useDashboardKeyboardShortcuts() {
  $effect(() => {
    const handleKeyboard = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey) {
        switch (event.key) {
          case 'b':
            event.preventDefault();
            goto('/dashboard/batches');
            break;
          case 'c':
            event.preventDefault();
            goto('/dashboard/classes');
            break;
          case 'n':
            event.preventDefault();
            goto('/dashboard/notifications');
            break;
        }
      }
    };
    
    document.addEventListener('keydown', handleKeyboard);
    return () => document.removeEventListener('keydown', handleKeyboard);
  });
}
