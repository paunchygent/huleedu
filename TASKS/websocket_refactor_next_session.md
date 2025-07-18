# WebSocket Refactor - Continue Implementation

## Context
You are continuing the WebSocket service refactor for HuleEdu. The new dedicated `websocket_service` has been created and is functional. Now you need to complete the migration by removing the legacy implementation from the API Gateway and updating documentation.

## Current State
- ✅ **Phase 1 Complete**: New websocket_service created with FastAPI, JWT auth, Redis Pub/Sub
- ❌ **Phase 2 Pending**: Remove legacy WebSocket code from api_gateway_service
- ❌ **Phase 3 Pending**: Update documentation for frontend team
- ❌ **Phase 4 Pending**: End-to-end verification

## Critical Rules to Follow
1. **Read the rule index first**: Start with `.cursor/rules/000-rule-index.mdc`
2. **Use agents for complex tasks**: Follow the patterns in `.cursor/rules/110.2-coding-mode.mdc`
3. **No assumptions**: Always read actual implementations before making changes
4. **Follow existing patterns**: Check how other services handle similar problems
5. **Protocol-based testing**: Mock protocols, not implementations

## Immediate Tasks

### Task 1: Remove Legacy WebSocket Implementation
Use an agent to safely remove all WebSocket code from api_gateway_service:

```
Remove all WebSocket-related code from the API Gateway service:
1. Delete services/api_gateway_service/routers/websocket_routes.py
2. Remove the import and registration from services/api_gateway_service/app/main.py
3. Delete services/api_gateway_service/tests/test_websocket_routes.py
4. Remove services/api_gateway_service/WEBSOCKET_README.md
5. Check app/metrics.py for any WebSocket-specific metrics to remove
```

### Task 2: Verify Service Integration
1. Check that websocket_service is properly configured in docker-compose
2. Ensure environment variables are correctly set
3. Verify health endpoints are working

### Task 3: Create Frontend Migration Guide
Create a document in TASKS/ explaining:
- Old endpoint: `ws://api-gateway:8080/ws/v1/status/{client_id}`
- New endpoint: `ws://websocket-service:8004/ws?token={jwt_token}`
- Authentication changes (header vs query param)
- Any message format changes

### Task 4: Run Verification Tests
1. Run all api_gateway_service tests to ensure no regressions
2. Run websocket_service tests to verify functionality
3. Create a simple end-to-end test script if needed

## Implementation Approach
1. Start by reading the main task document: `TASKS/WEBSOCKET_REFACTOR_TASK.md`
2. Use ULTRATHINK for planning any complex changes
3. Use agents for file operations to ensure pattern compliance
4. Always verify changes with tests before marking complete

## Reference Documents
- Main task: `TASKS/WEBSOCKET_REFACTOR_TASK.md`
- Architecture plan: `TASKS/WEBSOCKET_REFACTOR_PLAN.md`
- Implementation details: `TASKS/WEBSOCKET_SERVICE_IMPLEMENTATION_PLAN.md`
- Service patterns: `.cursor/rules/041-http-service-blueprint.mdc`

Remember: This is an atomic refactor with no legacy fallback. The old implementation must be completely removed.