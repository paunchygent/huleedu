# WebSocket Frontend Integration Guide

## Overview

This guide explains how to integrate your frontend application with the WebSocket service for real-time notifications.

## WebSocket Service Details

### 1. Endpoint URL

**WebSocket Endpoint:**

```
ws://websocket-service:8081/ws?token={jwt_token}
```

**Environment URLs:**

- Development: `ws://localhost:8081/ws?token={jwt_token}`
- Production: `wss://your-domain.com/websocket/ws?token={jwt_token}`

### 2. Authentication Method

JWT token must be passed as a query parameter:

```javascript
// Universal WebSocket client support
const ws = new WebSocket(`ws://websocket-service:8081/ws?token=${jwtToken}`);
```

### 3. User ID Handling

User ID is extracted directly from the JWT token - no need to pass it separately in the URL.

## Integration Steps

### Step 1: Create WebSocket Connection

Implement the WebSocket connection function:

```javascript
function connectWebSocket(jwtToken) {
  const ws = new WebSocket(`ws://websocket-service:8081/ws?token=${jwtToken}`);
  
  return ws;
}
```

### Step 2: Configure Environment Variables

Set up your environment configuration:

```javascript
const config = {
  wsEndpoint: process.env.WEBSOCKET_SERVICE_URL || 'ws://localhost:8081/ws'
};
```

### Step 3: Handle Connection Errors

The service uses standard WebSocket close codes:

```javascript
ws.onclose = (event) => {
  switch (event.code) {
    case 1008: // Policy Violation (authentication failed)
      console.error('Authentication failed - token invalid or expired');
      // Refresh token and reconnect
      break;
    case 1001: // Going Away (server shutdown)
      console.log('Server is shutting down');
      // Implement reconnection logic
      break;
    case 4000: // Custom: Connection limit exceeded
      console.error('Too many connections for this user');
      // Wait before reconnecting
      break;
    default:
      console.log('Connection closed', event.code, event.reason);
  }
};
```

## Complete Integration Example

Here's a complete example of a WebSocket client implementation:

```javascript
class WebSocketClient {
  constructor(tokenProvider) {
    this.tokenProvider = tokenProvider;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // Start with 1 second
  }

  async connect() {
    try {
      const token = await this.tokenProvider.getToken();
      const wsUrl = `${process.env.WEBSOCKET_SERVICE_URL || 'ws://localhost:8081/ws'}?token=${token}`;
      
      this.ws = new WebSocket(wsUrl);
      
      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
      };
      
      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      };
      
      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
      
      this.ws.onclose = (event) => {
        this.handleClose(event);
      };
      
    } catch (error) {
      console.error('Failed to connect:', error);
      this.scheduleReconnect();
    }
  }
  
  handleMessage(data) {
    // Handle incoming messages
    console.log('Received:', data);
    // Dispatch to your application's message handlers
  }
  
  handleClose(event) {
    console.log(`WebSocket closed: ${event.code} - ${event.reason}`);
    
    if (event.code === 1008) {
      // Authentication failed - refresh token before reconnecting
      this.tokenProvider.refreshToken().then(() => {
        this.connect();
      });
    } else if (event.code !== 1000) { // 1000 = Normal closure
      this.scheduleReconnect();
    }
  }
  
  scheduleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`Reconnecting in ${this.reconnectDelay}ms (attempt ${this.reconnectAttempts})`);
      
      setTimeout(() => {
        this.connect();
      }, this.reconnectDelay);
      
      // Exponential backoff
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
    } else {
      console.error('Max reconnection attempts reached');
    }
  }
  
  disconnect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.close(1000, 'Client disconnect');
    }
  }
}
```

## Message Format

The message format remains unchanged. Messages are still JSON-encoded strings:

```javascript
// Incoming message format
{
  "event_type": "essay_status_update",
  "data": {
    "essay_id": "essay123",
    "status": "completed",
    "timestamp": "2025-07-18T10:30:00Z"
  }
}
```

## Testing the Integration

1. **Test Authentication:**

   ```javascript
   // Test with valid token
   const ws1 = new WebSocket(`ws://localhost:8081/ws?token=${validToken}`);
   
   // Test with invalid token - should close with code 1008
   const ws2 = new WebSocket(`ws://localhost:8081/ws?token=invalid`);
   
   // Test with expired token - should close with code 1008
   const ws3 = new WebSocket(`ws://localhost:8081/ws?token=${expiredToken}`);
   ```

2. **Test Message Reception:**
   - Use Redis CLI to publish test messages:

   ```bash
   redis-cli
   > PUBLISH ws:user123 '{"event_type":"test","data":{"message":"Hello"}}'
   ```

3. **Test Connection Limits:**
   - Open multiple connections with the same token
   - Verify that old connections are closed when limit is exceeded

## Support

For issues or questions:

- Check WebSocket service logs: `docker logs huleedu_websocket_service`
- Verify JWT token validity
- Ensure Redis is accessible
- Check service health: `curl http://localhost:8081/healthz`
