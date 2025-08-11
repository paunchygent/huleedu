# Frontend Real-Time Integration Guide

Production-ready WebSocket integration patterns for HuleEdu real-time notifications.

## Overview

The HuleEdu WebSocket Service (port 8081) provides real-time teacher notifications with JWT authentication. This guide covers production-grade connection management, all 15 notification types, and framework integration patterns.

## Connection Management

### WebSocket URL Format

```text
ws://localhost:8081/ws?token=<JWT_TOKEN>
```

### Production WebSocket Client

```typescript
interface WebSocketConfig {
  maxReconnectAttempts?: number;
  reconnectDelay?: number;
  maxReconnectDelay?: number;
  heartbeatInterval?: number;
  connectionTimeout?: number;
}

class HuleEduWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private connectionState: 'disconnected' | 'connecting' | 'connected' | 'error' = 'disconnected';
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private eventEmitter = new EventTarget();
  
  constructor(
    private wsUrl: string = 'ws://localhost:8081',
    private config: WebSocketConfig = {}
  ) {}
  
  async connect(): Promise<void> {
    const token = await tokenManager.getValidToken();
    if (!token) throw new Error('No authentication token available');
    
    this.connectionState = 'connecting';
    const wsUrlWithAuth = `${this.wsUrl}/ws?token=${encodeURIComponent(token)}`;
    
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(wsUrlWithAuth);
      
      this.ws.onopen = () => {
        this.connectionState = 'connected';
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        this.emit('connected', { timestamp: new Date().toISOString() });
        resolve();
      };
      
      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('WebSocket message parse error:', error);
        }
      };
      
      this.ws.onclose = (event) => {
        this.connectionState = 'disconnected';
        this.stopHeartbeat();
        this.handleClose(event);
      };
      
      this.ws.onerror = reject;
    });
  }
  
  private handleClose(event: CloseEvent): void {
    if (event.code === 1008 || event.code === 4001) {
      // Authentication error - don't reconnect
      this.connectionState = 'error';
      this.emit('authError', { code: event.code, reason: event.reason });
    } else if (event.code !== 1000 && event.code !== 1001) {
      // Abnormal closure - attempt reconnect
      this.attemptReconnect();
    }
  }
  
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= (this.config.maxReconnectAttempts ?? 5)) {
      this.connectionState = 'error';
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
  
  private emit(eventType: string, data: any): void {
    this.eventEmitter.dispatchEvent(new CustomEvent(eventType, { detail: data }));
  }
  
  addEventListener(eventType: string, listener: EventListener): void {
    this.eventEmitter.addEventListener(eventType, listener);
  }
}
```

## Notification Types & Interfaces

### Core Types

```typescript
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

interface WebSocketMessage {
  type: 'teacher_notification' | 'pong';
  data: TeacherNotification;
}

type WebSocketEventCategory = 
  | 'batch_progress'
  | 'processing_results'
  | 'file_operations'
  | 'class_management'
  | 'student_workflow'
  | 'system_alerts';

type NotificationPriority = 
  | 'critical'    // Action required within 24 hours
  | 'immediate'   // Prompt attention (errors, failures)
  | 'high'        // Important but not urgent
  | 'standard'    // Normal priority
  | 'low';        // Informational only

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

## Notification Manager

Production notification handling with priority-based routing and UI integration.

```typescript
class NotificationManager {
  private notifications: TeacherNotification[] = [];
  private unreadCount = 0;
  private wsClient: HuleEduWebSocketClient;
  private eventEmitter = new EventTarget();
  
  constructor(wsClient: HuleEduWebSocketClient) {
    this.wsClient = wsClient;
    this.setupHandlers();
  }
  
  private setupHandlers(): void {
    this.wsClient.addEventListener('message', (event) => {
      const notification = event.detail as TeacherNotification;
      this.addNotification(notification);
      this.routeByPriority(notification);
    });
  }
  
  private addNotification(notification: TeacherNotification): void {
    this.notifications.unshift(notification);
    this.unreadCount++;
    
    // Limit stored notifications
    if (this.notifications.length > 100) {
      this.notifications = this.notifications.slice(0, 100);
    }
    
    this.emit('notificationAdded', notification);
    this.emit('unreadCountChanged', this.unreadCount);
  }
  
  private routeByPriority(notification: TeacherNotification): void {
    switch (notification.priority) {
      case 'critical':
        this.handleCritical(notification);
        break;
      case 'immediate':
        this.handleImmediate(notification);
        break;
      case 'high':
        this.showToast(notification, 'warning', 8000);
        break;
      case 'standard':
        this.showToast(notification, 'info', 5000);
        break;
      case 'low':
        this.showToast(notification, 'success', 3000);
        break;
    }
  }
  
  private handleCritical(notification: TeacherNotification): void {
    // Show modal for critical notifications
    this.showModal({
      title: 'Critical Action Required',
      message: this.formatMessage(notification),
      type: 'error',
      persistent: true,
      actions: [
        {
          label: 'Take Action',
          primary: true,
          onClick: () => this.navigateToAction(notification)
        }
      ]
    });
    
    this.playSound('critical');
    this.showBrowserNotification(notification, { requireInteraction: true });
  }
  
  private handleImmediate(notification: TeacherNotification): void {
    this.showToast(notification, 'error', 0, true); // persistent
    this.playSound('immediate');
    this.showBrowserNotification(notification);
  }
  
  private formatMessage(notification: TeacherNotification): string {
    const { notification_type, payload, batch_id } = notification;
    
    const messages: Record<string, string> = {
      'batch_files_uploaded': `✅ Files uploaded (${payload.file_count} files)`,
      'batch_file_removed': `🗑️ File removed: ${payload.filename}`,
      'batch_validation_failed': `❌ Validation failed: ${payload.error_message}`,
      'batch_processing_started': `🔄 Processing started: ${payload.pipeline_phase}`,
      'batch_processing_completed': `✅ Processing completed`,
      'batch_processing_failed': `❌ Processing failed: ${payload.error_message}`,
      'batch_results_ready': `📊 Results ready (${payload.essay_count} essays)`,
      'batch_assessment_completed': `✅ Assessment completed`,
      'batch_spellcheck_completed': `📝 Spellcheck completed (${payload.corrections_count} corrections)`,
      'batch_cj_assessment_completed': `🎯 CJ Assessment completed`,
      'class_created': `🏫 Class created: ${payload.class_name} (${payload.student_count} students)`,
      'student_added_to_class': `👤 Student added: ${payload.student_name}`,
      'validation_timeout_processed': `⏰ Validation timeout processed`,
      'student_associations_confirmed': `✅ Student associations confirmed`,
      'student_matching_confirmation_required': `🔍 Student matching requires confirmation`
    };
    
    return messages[notification_type] || `📢 ${notification_type.replace(/_/g, ' ')}`;
  }
  
  private navigateToAction(notification: TeacherNotification): void {
    const routes: Record<string, string> = {
      'student_matching_confirmation_required': `/batches/${notification.batch_id}/matching`,
      'batch_results_ready': `/batches/${notification.batch_id}/results`,
      'batch_processing_failed': `/batches/${notification.batch_id}/status`,
      'class_created': `/classes/${notification.class_id}`,
      'batch_files_uploaded': `/batches/${notification.batch_id}/files`
    };
    
    const route = routes[notification.notification_type];
    if (route) window.location.href = route;
  }
  
  // Public API
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
  
  addEventListener(eventType: string, listener: EventListener): void {
    this.eventEmitter.addEventListener(eventType, listener);
  }
  
  private emit(eventType: string, data: any): void {
    this.eventEmitter.dispatchEvent(new CustomEvent(eventType, { detail: data }));
  }
  
  // Placeholder methods - implement with your UI library
  private showModal(options: any): void { /* Implement modal */ }
  private showToast(notification: TeacherNotification, type: string, duration: number, persistent = false): void { /* Implement toast */ }
  private playSound(type: string): void { /* Implement sound */ }
  private showBrowserNotification(notification: TeacherNotification, options: any = {}): void {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(this.formatMessage(notification), {
        icon: '/notification-icon.png',
        ...options
      });
    }
  }
}
```
