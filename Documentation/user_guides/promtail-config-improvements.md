# Promtail Configuration Improvements

## What Changed

The improved Promtail configuration handles structlog JSON parsing more gracefully:

### Key Improvements:

1. **Flexible JSON Detection**: First checks if a line is valid JSON before trying to parse it
2. **Multiple Message Field Support**: Handles different field names (`event`, `message`, `msg`)
3. **Graceful Field Handling**: Doesn't fail when optional fields are missing
4. **Better Timestamp Parsing**: Supports multiple timestamp formats
5. **Default Values**: Sets sensible defaults for missing fields (e.g., level="info")

## How to Apply the Changes

1. **Backup Original Config** (already done):
   ```bash
   mv promtail-config.yml promtail-config-original.yml
   ```

2. **Apply Improved Config** (already done):
   ```bash
   mv promtail-config-improved.yml promtail-config.yml
   ```

3. **Restart Promtail** (already done):
   ```bash
   docker compose restart promtail
   ```

## Verifying the Improvements

### Check in Grafana:

1. Go to the Service Deep Dive dashboard
2. Select a service (e.g., `batch_orchestrator_service`)
3. Look at the Live Logs panel
4. You should see:
   - Fewer or no `JSONParserErr` entries
   - Cleaner log formatting
   - Correlation IDs still properly extracted when present

### Test Query:

In Grafana Explore, try this query to see the difference:
```
{service="batch_orchestrator_service"} | json | __error__ = ""
```

This shows only successfully parsed logs.

## What to Expect

### Before (Original Config):
- Many logs show `JSONParserErr`
- `__error__` field pollutes the log view
- Still functional but visually noisy

### After (Improved Config):
- Cleaner log parsing
- Optional fields handled gracefully
- Better handling of structlog's `event` field
- Correlation IDs still tracked when present

## Rollback if Needed

If you encounter any issues:
```bash
mv promtail-config.yml promtail-config-improved.yml
mv promtail-config-original.yml promtail-config.yml
docker compose restart promtail
```

## Important Notes

1. **Give it time**: New logs will use the improved parsing. Old logs already in Loki won't change.
2. **Correlation IDs**: Still captured when present in event processing logs
3. **Performance**: No impact on performance - just better parsing logic
4. **All Services Benefit**: This improves log parsing for all services, not just BOS