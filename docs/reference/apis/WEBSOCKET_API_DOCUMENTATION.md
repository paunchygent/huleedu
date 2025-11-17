# WebSocket API Documentation

## Overview

The HuleEdu WebSocket Service provides real-time communication capabilities for the platform, enabling instant notifications and status updates for batch processing, essay analysis, and system events.

**Service URL**: `ws://localhost:8080/ws`  
**Authentication**: JWT token via query parameter  
**Protocol**: Text-based JSON messages

## Connection Establishment

### Authentication Flow

WebSocket connections require JWT authentication passed as a query parameter:

```javascript
const token = "your-jwt-token-here";
const wsUrl = `ws://localhost:8080/ws?token=${encodeURIComponent(token)}`;
const websocket = new WebSocket(wsUrl);
```

### Connection Lifecycle

For complete WebSocket client implementation with reconnection logic, see [Shared Code Patterns - WebSocket Connection Management](SHARED_CODE_PATTERNS.md#websocket-connection-management).

Basic connection example:
```javascript
const wsClient = new HuleEduWebSocketClient(token, {
  maxReconnectAttempts: 5,
  reconnectDelay: 1000,
  heartbeatInterval: 30000
});

wsClient.on('connected', () => console.log('Connected'));
wsClient.on('message', handleNotification);
wsClient.connect();
```

## Notification Event Types

The WebSocket service delivers 14 different notification types based on the `TeacherNotificationRequestedV1` event structure:

### 1. File Operation Notifications

#### `batch_files_uploaded`

Notifies when files are successfully uploaded to a batch.

```json
{
    "notification_type": "batch_files_uploaded",
    "timestamp": "2024-01-15T10:35:00Z",
    "category": "file_operations",
    "priority": "standard",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "user_id": "user_456",
        "files_uploaded": 5,
        "total_size_bytes": 2048576
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `batch_file_removed`

Notifies when a file is removed from a batch.

```json
{
    "notification_type": "batch_file_removed",
    "timestamp": "2024-01-15T10:40:00Z",
    "category": "file_operations", 
    "priority": "standard",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "file_id": "file_789",
        "filename": "essay_student1.pdf"
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `batch_validation_failed`

Notifies when batch validation fails.

```json
{
    "notification_type": "batch_validation_failed",
    "timestamp": "2024-01-15T10:45:00Z",
    "category": "system_alerts",
    "priority": "immediate", 
    "action_required": true,
    "payload": {
        "batch_id": "batch_123",
        "validation_errors": ["Invalid file format", "Missing student associations"],
        "error_message": "Batch validation failed due to file format issues"
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 2. Class Management Notifications

#### `class_created`

Notifies when a new class is created.

```json
{
    "notification_type": "class_created",
    "timestamp": "2024-01-15T09:15:00Z",
    "category": "class_management",
    "priority": "standard",
    "action_required": false,
    "payload": {
        "class_id": "class_456", 
        "class_name": "English Composition A",
        "teacher_id": "teacher_789"
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `student_added_to_class`

Notifies when a student is added to a class.

```json
{
    "notification_type": "student_added_to_class",
    "timestamp": "2024-01-15T09:30:00Z",
    "category": "class_management",
    "priority": "low",
    "action_required": false,
    "payload": {
        "class_id": "class_456",
        "student_id": "student_123",
        "student_name": "John Smith"
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `validation_timeout_processed`

Notifies when validation timeout has been processed.

```json
{
    "notification_type": "validation_timeout_processed",
    "timestamp": "2024-01-15T11:00:00Z",
    "category": "student_workflow",
    "priority": "immediate",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "timeout_duration_seconds": 300,
        "processed_students": 15
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `student_associations_confirmed`

Notifies when student associations have been confirmed.

```json
{
    "notification_type": "student_associations_confirmed",
    "timestamp": "2024-01-15T11:15:00Z",
    "category": "student_workflow", 
    "priority": "high",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "confirmed_associations": 12,
        "pending_associations": 3
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 3. Processing Result Notifications

#### `batch_spellcheck_completed`

Notifies when spellcheck is completed for a batch.

```json
{
    "notification_type": "batch_spellcheck_completed",
    "timestamp": "2024-01-15T10:42:00Z",
    "category": "batch_progress",
    "priority": "low",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "essays_processed": 15,
        "total_errors_found": 42,
        "processing_duration_seconds": 180
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `batch_cj_assessment_completed`

Notifies when content judgment assessment is completed for a batch.

```json
{
    "notification_type": "batch_cj_assessment_completed",
    "timestamp": "2024-01-15T11:15:00Z",
    "category": "batch_progress",
    "priority": "standard",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "essays_assessed": 15,
        "average_content_score": 7.8,
        "processing_duration_seconds": 450
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `batch_processing_started`

Notifies when batch processing begins.

```json
{
    "notification_type": "batch_processing_started",
    "timestamp": "2024-01-15T10:00:00Z",
    "category": "batch_progress",
    "priority": "low",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "pipeline_phase": "spellcheck",
        "estimated_duration_minutes": 8
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `batch_results_ready`

Notifies when batch processing results are ready.

```json
{
    "notification_type": "batch_results_ready",
    "timestamp": "2024-01-15T12:00:00Z",
    "category": "processing_results",
    "priority": "high",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "results_count": 15,
        "download_url": "/api/v1/batches/batch_123/results"
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `batch_assessment_completed`

Notifies when all assessments for a batch are completed.

```json
{
    "notification_type": "batch_assessment_completed",
    "timestamp": "2024-01-15T12:30:00Z",
    "category": "processing_results",
    "priority": "standard",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "total_essays": 15,
        "completed_assessments": 15,
        "overall_completion_rate": 1.0
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 4. Pipeline Completion Notifications

#### `batch_pipeline_completed`

Notifies when all requested pipeline phases have completed for a batch.

```json
{
    "notification_type": "batch_pipeline_completed",
    "timestamp": "2024-01-15T13:00:00Z",
    "category": "processing_results",
    "priority": "high",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "completed_phases": ["spellcheck", "cj_assessment"],
        "final_status": "COMPLETED_SUCCESSFULLY",
        "processing_duration_seconds": 1800.5,
        "successful_essay_count": 15,
        "failed_essay_count": 0,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

#### `phase_skipped`

Notifies when a pipeline phase is skipped due to prior completion (optimization).

```json
{
    "notification_type": "phase_skipped",
    "timestamp": "2024-01-15T10:05:00Z",
    "category": "batch_progress",
    "priority": "low",
    "action_required": false,
    "payload": {
        "batch_id": "batch_123",
        "phase_name": "spellcheck",
        "skip_reason": "already_completed",
        "storage_id": "storage_abc123",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    },
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

## Error Handling and Reconnection

### Connection Errors

#### Authentication Failure (1008)

```json
{
    "error": "Authentication failed",
    "code": 1008,
    "message": "Invalid or expired JWT token",
    "retry_recommended": false
}
```

#### Rate Limit Exceeded (4000)

```json
{
    "error": "Rate limit exceeded",
    "code": 4000,
    "message": "Too many connection attempts",
    "retry_after_seconds": 60
}
```

#### Server Error (1011)

```json
{
    "error": "Internal server error",
    "code": 1011,
    "message": "WebSocket service temporarily unavailable",
    "retry_recommended": true
}
```

### Reconnection Strategy

Implement exponential backoff with jitter for reconnection attempts:

```javascript
class ReconnectionManager {
    constructor(options = {}) {
        this.maxAttempts = options.maxAttempts || 5;
        this.baseDelay = options.baseDelay || 1000;
        this.maxDelay = options.maxDelay || 30000;
        this.jitterFactor = options.jitterFactor || 0.1;
        this.attempts = 0;
    }

    getNextDelay() {
        if (this.attempts >= this.maxAttempts) {
            return null; // No more attempts
        }

        const exponentialDelay = this.baseDelay * Math.pow(2, this.attempts);
        const cappedDelay = Math.min(exponentialDelay, this.maxDelay);
        const jitter = cappedDelay * this.jitterFactor * Math.random();
        
        this.attempts++;
        return cappedDelay + jitter;
    }

    reset() {
        this.attempts = 0;
    }
}
```

## Client Integration Examples

### Framework Integration

For production-ready WebSocket integration with Svelte 5 and other frameworks, see:

- **[Svelte 5 Integration Guide](SVELTE_INTEGRATION_GUIDE.md#websocket-management)** - Complete WebSocket management with runes
- **[Shared Code Patterns](SHARED_CODE_PATTERNS.md#websocket-connection-management)** - Base WebSocket client implementation

Example integration:
```typescript
// For Svelte 5
import { wsManager } from '$lib/stores/websocket.svelte';

// Auto-reactive WebSocket state
$effect(() => {
  console.log('Connection status:', wsManager.isConnected);
  console.log('Notifications:', wsManager.notifications.length);
});
```

### Pipeline Completion Integration Examples

#### Basic Pipeline Completion Handling

```typescript
// Subscribe to pipeline completion events
wsClient.on('batch_pipeline_completed', (data) => {
  console.log(`Pipeline completed for batch ${data.payload.batch_id}`);
  console.log(`Status: ${data.payload.final_status}`);
  console.log(`Duration: ${data.payload.processing_duration_seconds}s`);
  
  // Update UI state
  updateBatchStatus(data.payload.batch_id, 'completed');
  showCompletionNotification(data.payload);
  enableResultsDownload(data.payload.batch_id);
});

// Handle phase skipping for optimization transparency
wsClient.on('phase_skipped', (data) => {
  console.log(`Phase ${data.payload.phase_name} skipped for batch ${data.payload.batch_id}`);
  console.log(`Reason: ${data.payload.skip_reason}`);
  
  // Update progress indicator
  updateProgressIndicator(data.payload.batch_id, data.payload.phase_name, 'skipped');
});
```

#### Svelte 5 Reactive Integration

```typescript
// stores/batch.svelte.ts
import { writable } from 'svelte/store';

interface BatchState {
  status: 'processing' | 'completed' | 'failed';
  completedPhases: string[];
  stats?: {
    duration: number;
    successfulEssays: number;
    failedEssays: number;
  };
}

export const batchStates = $state<Record<string, BatchState>>({});

// WebSocket event handler
export function handlePipelineCompleted(event: BatchPipelineCompletedData) {
  const batchId = event.payload.batch_id;
  
  batchStates[batchId] = {
    status: event.payload.final_status === 'COMPLETED_SUCCESSFULLY' ? 'completed' : 'failed',
    completedPhases: event.payload.completed_phases,
    stats: {
      duration: event.payload.processing_duration_seconds,
      successfulEssays: event.payload.successful_essay_count,
      failedEssays: event.payload.failed_essay_count,
    }
  };
}
```

#### React Integration Example

```typescript
// hooks/usePipelineCompletion.ts
import { useEffect, useState } from 'react';
import { wsClient } from '../services/websocket';

interface PipelineStats {
  batchId: string;
  status: string;
  duration: number;
  successfulEssays: number;
  failedEssays: number;
  completedPhases: string[];
}

export function usePipelineCompletion() {
  const [completedPipelines, setCompletedPipelines] = useState<PipelineStats[]>([]);
  
  useEffect(() => {
    const handleCompletion = (data: BatchPipelineCompletedData) => {
      const stats: PipelineStats = {
        batchId: data.payload.batch_id,
        status: data.payload.final_status,
        duration: data.payload.processing_duration_seconds,
        successfulEssays: data.payload.successful_essay_count,
        failedEssays: data.payload.failed_essay_count,
        completedPhases: data.payload.completed_phases,
      };
      
      setCompletedPipelines(prev => [...prev, stats]);
      
      // Show user notification
      if (data.payload.final_status === 'COMPLETED_SUCCESSFULLY') {
        toast.success(`Pipeline completed successfully for batch ${data.payload.batch_id}`);
      } else {
        toast.warning(`Pipeline completed with issues for batch ${data.payload.batch_id}`);
      }
    };
    
    wsClient.on('batch_pipeline_completed', handleCompletion);
    
    return () => {
      wsClient.off('batch_pipeline_completed', handleCompletion);
    };
  }, []);
  
  return { completedPipelines };
}
```

#### Error Handling and Edge Cases

```typescript
// Comprehensive event handling with error recovery
class PipelineCompletionHandler {
  private batchTimeouts: Map<string, NodeJS.Timeout> = new Map();
  private readonly COMPLETION_TIMEOUT = 30 * 60 * 1000; // 30 minutes
  
  handlePipelineStarted(batchId: string) {
    // Set timeout for pipeline completion
    const timeout = setTimeout(() => {
      this.handlePipelineTimeout(batchId);
    }, this.COMPLETION_TIMEOUT);
    
    this.batchTimeouts.set(batchId, timeout);
  }
  
  handlePipelineCompleted(data: BatchPipelineCompletedData) {
    const batchId = data.payload.batch_id;
    
    // Clear timeout
    const timeout = this.batchTimeouts.get(batchId);
    if (timeout) {
      clearTimeout(timeout);
      this.batchTimeouts.delete(batchId);
    }
    
    // Process completion
    try {
      this.updateBatchResults(data);
      this.notifyUser(data);
      this.enableDownloads(batchId);
    } catch (error) {
      console.error('Error processing pipeline completion:', error);
      this.handleCompletionError(batchId, error);
    }
  }
  
  private handlePipelineTimeout(batchId: string) {
    console.warn(`Pipeline completion timeout for batch ${batchId}`);
    // Fallback to polling API for status
    this.pollBatchStatus(batchId);
  }
  
  private async pollBatchStatus(batchId: string) {
    try {
      const response = await fetch(`/api/v1/batches/${batchId}/status`);
      const status = await response.json();
      
      if (status.details.status === 'completed') {
        // Manually trigger completion handling
        this.handleMissedCompletion(batchId, status);
      }
    } catch (error) {
      console.error('Error polling batch status:', error);
    }
  }
}
```

## Testing WebSocket Connections

### Manual Testing with Browser DevTools

```javascript
// Open browser console and run:
const token = "your-jwt-token";
const ws = new WebSocket(`ws://localhost:8080/ws?token=${encodeURIComponent(token)}`);

ws.onopen = () => console.log('Connected');
ws.onmessage = (event) => console.log('Message:', JSON.parse(event.data));
ws.onclose = (event) => console.log('Disconnected:', event.code, event.reason);
ws.onerror = (error) => console.error('Error:', error);
```

### Automated Testing

```javascript
// Jest test example
describe('WebSocket Client', () => {
    let mockWebSocket;
    let client;

    beforeEach(() => {
        mockWebSocket = {
            send: jest.fn(),
            close: jest.fn(),
            addEventListener: jest.fn(),
            removeEventListener: jest.fn()
        };
        
        global.WebSocket = jest.fn(() => mockWebSocket);
        client = new HuleEduWebSocketClient('test-token');
    });

    test('should handle connection events', () => {
        const connectHandler = jest.fn();
        client.on('connected', connectHandler);
        
        client.connect();
        
        // Simulate connection open
        mockWebSocket.onopen({ type: 'open' });
        
        expect(connectHandler).toHaveBeenCalled();
    });

    test('should handle message parsing', () => {
        const messageHandler = jest.fn();
        client.on('batch_files_uploaded', messageHandler);
        
        const testMessage = {
            notification_type: 'batch_files_uploaded',
            payload: { batch_id: 'test-batch' }
        };
        
        // Simulate message receipt
        mockWebSocket.onmessage({
            data: JSON.stringify(testMessage)
        });
        
        expect(messageHandler).toHaveBeenCalledWith(testMessage.payload);
    });
});
```

## Performance Considerations

### Connection Limits

- Maximum 5 concurrent connections per user
- Idle timeout: 300 seconds (5 minutes)
- Message rate limit: 100 messages per minute per connection

### Message Size Limits

- Maximum message size: 64KB
- Batch notification messages are typically 1-2KB
- System notifications are typically 500 bytes - 1KB

### Monitoring and Metrics

The WebSocket service exposes Prometheus metrics at `/metrics`:

- `websocket_connections_total` - Total active connections
- `websocket_messages_sent_total` - Total messages sent
- `websocket_connection_duration_seconds` - Connection duration histogram
- `websocket_message_size_bytes` - Message size histogram

## Security Considerations

### Token Validation

- JWT tokens are validated on connection establishment
- Expired tokens result in immediate connection termination (code 1008)
- Token refresh requires reconnection with new token

### Rate Limiting

- Connection attempts: 10 per minute per IP
- Message processing: 100 messages per minute per connection
- Exceeded limits result in temporary connection blocks

### CORS Configuration

WebSocket connections respect CORS origins configuration:

```bash
CORS_ORIGINS=["http://localhost:3000", "https://app.huledu.com"]
```

## Troubleshooting

### Common Issues

#### Connection Refused

- Verify WebSocket service is running on port 8080
- Check firewall settings
- Ensure CORS origins include your domain

#### Authentication Failures

- Verify JWT token is valid and not expired
- Check token format (should be passed as query parameter)
- Ensure token has required claims (user_id, exp)

#### Message Delivery Issues

- Check Redis connectivity (WebSocket service uses Redis pub/sub)
- Verify user_id in token matches notification target
- Monitor service logs for processing errors

#### Performance Issues

- Monitor connection count (max 5 per user)
- Check message rate limits
- Verify network connectivity and latency

### Debug Logging

Enable debug logging by setting environment variable:

```bash
LOG_LEVEL=DEBUG
```

This will provide detailed logs for:

- Connection establishment and termination
- Message routing and delivery
- Authentication and authorization events
- Error conditions and recovery attempts
