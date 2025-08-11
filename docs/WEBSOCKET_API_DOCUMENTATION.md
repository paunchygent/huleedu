# WebSocket API Documentation

## Overview

The HuleEdu WebSocket Service provides real-time communication capabilities for the platform, enabling instant notifications and status updates for batch processing, essay analysis, and system events.

**Service URL**: `ws://localhost:8081/ws`  
**Authentication**: JWT token via query parameter  
**Protocol**: Text-based JSON messages

## Connection Establishment

### Authentication Flow

WebSocket connections require JWT authentication passed as a query parameter:

```javascript
const token = "your-jwt-token-here";
const wsUrl = `ws://localhost:8081/ws?token=${encodeURIComponent(token)}`;
const websocket = new WebSocket(wsUrl);
```

### Connection Lifecycle

```javascript
class HuleEduWebSocketClient {
    constructor(token, options = {}) {
        this.token = token;
        this.baseUrl = options.baseUrl || 'ws://localhost:8081';
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 5;
        this.reconnectDelay = options.reconnectDelay || 1000;
        this.websocket = null;
        this.eventHandlers = new Map();
    }

    connect() {
        const wsUrl = `${this.baseUrl}/ws?token=${encodeURIComponent(this.token)}`;
        this.websocket = new WebSocket(wsUrl);

        this.websocket.onopen = (event) => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            this.emit('connected', event);
        };

        this.websocket.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                this.handleMessage(message);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
            }
        };

        this.websocket.onclose = (event) => {
            console.log('WebSocket disconnected:', event.code, event.reason);
            this.emit('disconnected', event);
            this.handleReconnection(event);
        };

        this.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.emit('error', error);
        };
    }

    handleReconnection(event) {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
            
            setTimeout(() => {
                this.connect();
            }, delay);
        } else {
            console.error('Max reconnection attempts reached');
            this.emit('maxReconnectAttemptsReached');
        }
    }

    on(eventType, handler) {
        if (!this.eventHandlers.has(eventType)) {
            this.eventHandlers.set(eventType, []);
        }
        this.eventHandlers.get(eventType).push(handler);
    }

    emit(eventType, data) {
        const handlers = this.eventHandlers.get(eventType) || [];
        handlers.forEach(handler => handler(data));
    }

    handleMessage(message) {
        const { notification_type, data } = message;
        this.emit('message', message);
        this.emit(notification_type, data);
    }

    disconnect() {
        if (this.websocket) {
            this.websocket.close(1000, 'Client disconnect');
        }
    }
}
```

## Notification Event Types

The WebSocket service delivers 15 different notification types based on the `TeacherNotificationRequestedV1` event structure:

### 1. Batch Status Notifications

#### `BATCH_CREATED`

Notifies when a new batch is created.

```json
{
    "notification_type": "BATCH_CREATED",
    "timestamp": "2024-01-15T10:30:00Z",
    "data": {
        "batch_id": "batch_123",
        "user_id": "user_456",
        "status": "CREATED",
        "file_count": 0,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `BATCH_FILES_UPLOADED`

Notifies when files are successfully uploaded to a batch.

```json
{
    "notification_type": "BATCH_FILES_UPLOADED",
    "timestamp": "2024-01-15T10:35:00Z",
    "data": {
        "batch_id": "batch_123",
        "user_id": "user_456",
        "files_uploaded": 5,
        "total_size_bytes": 2048576,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `BATCH_PROCESSING_STARTED`

Notifies when batch processing begins.

```json
{
    "notification_type": "BATCH_PROCESSING_STARTED",
    "timestamp": "2024-01-15T10:40:00Z",
    "data": {
        "batch_id": "batch_123",
        "user_id": "user_456",
        "pipeline_phase": "SPELLCHECK",
        "estimated_duration_minutes": 15,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `BATCH_PROCESSING_COMPLETED`

Notifies when batch processing is completed.

```json
{
    "notification_type": "BATCH_PROCESSING_COMPLETED",
    "timestamp": "2024-01-15T10:55:00Z",
    "data": {
        "batch_id": "batch_123",
        "user_id": "user_456",
        "pipeline_phase": "SPELLCHECK",
        "status": "COMPLETED",
        "processing_duration_minutes": 14,
        "essays_processed": 5,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `BATCH_PROCESSING_FAILED`

Notifies when batch processing fails.

```json
{
    "notification_type": "BATCH_PROCESSING_FAILED",
    "timestamp": "2024-01-15T10:45:00Z",
    "data": {
        "batch_id": "batch_123",
        "user_id": "user_456",
        "pipeline_phase": "SPELLCHECK",
        "error_type": "ValidationError",
        "error_message": "Invalid file format detected",
        "retry_recommended": true,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

### 2. Essay Status Notifications

#### `ESSAY_SPELLCHECK_COMPLETED`

Notifies when spellcheck is completed for an essay.

```json
{
    "notification_type": "ESSAY_SPELLCHECK_COMPLETED",
    "timestamp": "2024-01-15T10:42:00Z",
    "data": {
        "essay_id": "essay_789",
        "batch_id": "batch_123",
        "user_id": "user_456",
        "spelling_errors_found": 3,
        "grammar_errors_found": 1,
        "confidence_score": 0.95,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `ESSAY_CONTENT_JUDGMENT_COMPLETED`

Notifies when content judgment is completed for an essay.

```json
{
    "notification_type": "ESSAY_CONTENT_JUDGMENT_COMPLETED",
    "timestamp": "2024-01-15T11:15:00Z",
    "data": {
        "essay_id": "essay_789",
        "batch_id": "batch_123",
        "user_id": "user_456",
        "content_quality_score": 8.5,
        "readability_score": 7.8,
        "coherence_score": 8.2,
        "argument_strength": 7.9,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `ESSAY_FEEDBACK_GENERATED`

Notifies when feedback is generated for an essay.

```json
{
    "notification_type": "ESSAY_FEEDBACK_GENERATED",
    "timestamp": "2024-01-15T11:30:00Z",
    "data": {
        "essay_id": "essay_789",
        "batch_id": "batch_123",
        "user_id": "user_456",
        "feedback_sections": ["structure", "content", "grammar", "style"],
        "overall_score": 8.1,
        "feedback_length_words": 245,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `ESSAY_PROCESSING_FAILED`

Notifies when essay processing fails.

```json
{
    "notification_type": "ESSAY_PROCESSING_FAILED",
    "timestamp": "2024-01-15T10:43:00Z",
    "data": {
        "essay_id": "essay_789",
        "batch_id": "batch_123",
        "user_id": "user_456",
        "pipeline_phase": "SPELLCHECK",
        "error_type": "ProcessingError",
        "error_message": "Text extraction failed - unsupported file format",
        "retry_recommended": false,
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

### 3. System Notifications

#### `SYSTEM_MAINTENANCE_SCHEDULED`

Notifies about scheduled system maintenance.

```json
{
    "notification_type": "SYSTEM_MAINTENANCE_SCHEDULED",
    "timestamp": "2024-01-15T09:00:00Z",
    "data": {
        "maintenance_start": "2024-01-16T02:00:00Z",
        "maintenance_end": "2024-01-16T04:00:00Z",
        "affected_services": ["batch_processing", "file_upload"],
        "description": "Scheduled database maintenance",
        "user_id": "user_456",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `SYSTEM_MAINTENANCE_STARTED`

Notifies when system maintenance begins.

```json
{
    "notification_type": "SYSTEM_MAINTENANCE_STARTED",
    "timestamp": "2024-01-16T02:00:00Z",
    "data": {
        "maintenance_type": "database_upgrade",
        "estimated_duration_minutes": 120,
        "affected_services": ["batch_processing", "file_upload"],
        "user_id": "user_456",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `SYSTEM_MAINTENANCE_COMPLETED`

Notifies when system maintenance is completed.

```json
{
    "notification_type": "SYSTEM_MAINTENANCE_COMPLETED",
    "timestamp": "2024-01-16T03:45:00Z",
    "data": {
        "maintenance_type": "database_upgrade",
        "actual_duration_minutes": 105,
        "services_restored": ["batch_processing", "file_upload"],
        "user_id": "user_456",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `SERVICE_DEGRADATION_ALERT`

Notifies about service performance degradation.

```json
{
    "notification_type": "SERVICE_DEGRADATION_ALERT",
    "timestamp": "2024-01-15T14:20:00Z",
    "data": {
        "affected_service": "content_judgment_service",
        "degradation_level": "moderate",
        "expected_delay_minutes": 5,
        "estimated_resolution": "2024-01-15T15:00:00Z",
        "user_id": "user_456",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

#### `SERVICE_RESTORED`

Notifies when service is restored after degradation.

```json
{
    "notification_type": "SERVICE_RESTORED",
    "timestamp": "2024-01-15T14:55:00Z",
    "data": {
        "restored_service": "content_judgment_service",
        "downtime_duration_minutes": 35,
        "performance_status": "normal",
        "user_id": "user_456",
        "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
    }
}
```

## Error Handling and Reconnection

### Connection Errors

#### Authentication Failure (4001)

```json
{
    "error": "Authentication failed",
    "code": 4001,
    "message": "Invalid or expired JWT token",
    "retry_recommended": false
}
```

#### Rate Limit Exceeded (4029)

```json
{
    "error": "Rate limit exceeded",
    "code": 4029,
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

### React Hook Implementation

```typescript
import { useEffect, useRef, useState } from 'react';

interface WebSocketMessage {
    notification_type: string;
    timestamp: string;
    data: any;
}

interface UseWebSocketOptions {
    token: string;
    baseUrl?: string;
    maxReconnectAttempts?: number;
    reconnectDelay?: number;
}

export function useWebSocket(options: UseWebSocketOptions) {
    const [isConnected, setIsConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
    const [error, setError] = useState<string | null>(null);
    const websocketRef = useRef<HuleEduWebSocketClient | null>(null);

    useEffect(() => {
        const client = new HuleEduWebSocketClient(options.token, {
            baseUrl: options.baseUrl,
            maxReconnectAttempts: options.maxReconnectAttempts,
            reconnectDelay: options.reconnectDelay
        });

        client.on('connected', () => {
            setIsConnected(true);
            setError(null);
        });

        client.on('disconnected', () => {
            setIsConnected(false);
        });

        client.on('error', (error) => {
            setError(error.message || 'WebSocket error');
        });

        client.on('message', (message) => {
            setLastMessage(message);
        });

        client.connect();
        websocketRef.current = client;

        return () => {
            client.disconnect();
        };
    }, [options.token]);

    const subscribe = (eventType: string, handler: (data: any) => void) => {
        websocketRef.current?.on(eventType, handler);
    };

    return {
        isConnected,
        lastMessage,
        error,
        subscribe
    };
}
```

### Svelte Store Implementation

```typescript
// websocket-store.ts
import { writable, derived } from 'svelte/store';

interface WebSocketState {
    isConnected: boolean;
    lastMessage: WebSocketMessage | null;
    error: string | null;
}

function createWebSocketStore(token: string) {
    const { subscribe, set, update } = writable<WebSocketState>({
        isConnected: false,
        lastMessage: null,
        error: null
    });

    let client: HuleEduWebSocketClient | null = null;

    const connect = () => {
        client = new HuleEduWebSocketClient(token);

        client.on('connected', () => {
            update(state => ({ ...state, isConnected: true, error: null }));
        });

        client.on('disconnected', () => {
            update(state => ({ ...state, isConnected: false }));
        });

        client.on('error', (error) => {
            update(state => ({ ...state, error: error.message }));
        });

        client.on('message', (message) => {
            update(state => ({ ...state, lastMessage: message }));
        });

        client.connect();
    };

    const disconnect = () => {
        client?.disconnect();
        client = null;
    };

    const subscribeToEvent = (eventType: string, handler: (data: any) => void) => {
        client?.on(eventType, handler);
    };

    return {
        subscribe,
        connect,
        disconnect,
        subscribeToEvent
    };
}

export const websocketStore = createWebSocketStore;
```

## Testing WebSocket Connections

### Manual Testing with Browser DevTools

```javascript
// Open browser console and run:
const token = "your-jwt-token";
const ws = new WebSocket(`ws://localhost:8081/ws?token=${encodeURIComponent(token)}`);

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
        client.on('BATCH_CREATED', messageHandler);
        
        const testMessage = {
            notification_type: 'BATCH_CREATED',
            data: { batch_id: 'test-batch' }
        };
        
        // Simulate message receipt
        mockWebSocket.onmessage({
            data: JSON.stringify(testMessage)
        });
        
        expect(messageHandler).toHaveBeenCalledWith(testMessage.data);
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
- Expired tokens result in immediate connection termination (code 4001)
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

- Verify WebSocket service is running on port 8081
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
