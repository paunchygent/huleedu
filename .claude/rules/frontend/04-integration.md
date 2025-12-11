# Backend Integration

## API Gateway
All frontend calls go through API Gateway (BFF pattern).

## Authentication
- JWT tokens with Bearer format
- Automatic token renewal (5-minute threshold)
- Include `X-Correlation-ID` header

## WebSocket
- Use `HuleEduWebSocketClient` for real-time updates
- Handle reconnection with exponential backoff
- 15 notification types from `TeacherNotificationRequestedV1`

## Error Handling
- `NetworkError`, `RateLimitError`, `ValidationError`
- Circuit breaker pattern for failing services
- Offline queue for request resilience

**Detailed**: `docs/how-to/FRONTEND_INTEGRATION_GUIDE.md`
