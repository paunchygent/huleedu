# Language Tool Service: JAR Testing Strategy

## Overview

The Language Tool Service employs a dual-mode testing strategy that intelligently adapts to the presence or absence of the LanguageTool JAR file. This allows for efficient local development while ensuring production fidelity.

## The Two Modes

### 1. Real JAR Mode (Production)

- **When**: LanguageTool JAR is present at `/app/languagetool/languagetool-server.jar`
- **Where**: Docker containers, production deployments, CI/CD with Docker
- **Behavior**:
  - Spawns actual Java process (requires Java 21 JRE)
  - Full LanguageTool grammar checking capabilities
  - 100+ language support
  - ~30-60 second startup time
  - ~512MB memory usage

### 2. Stub Mode (Development)

- **When**: JAR file is not found
- **Where**: Local development, unit tests, quick iterations
- **Behavior**:
  - Lightweight Python stub implementation
  - Returns predictable test data
  - Instant startup
  - Minimal memory usage
  - No Java dependency required

## Architecture Decision

```python
# From di.py - Automatic mode selection
jar_path = Path(settings.LANGUAGE_TOOL_JAR_PATH)
if jar_path.exists():
    return LanguageToolManager(...)  # Real Java process
else:
    return StubLanguageToolWrapper()  # Stub implementation
```

## Test Behavior

### Integration Tests (`test_languagetool_process_lifecycle.py`)

Tests that require the real Java process will skip when JAR is missing:

```python
jar_path = Path(manager.settings.LANGUAGE_TOOL_JAR_PATH)
if not jar_path.exists():
    pytest.skip(f"LanguageTool JAR not found at {jar_path}, skipping...")
```

**Expected Behavior**:

- **Local Development**: 4 tests skip, 1 test passes (stub fallback test)
- **Docker/CI**: All 5 tests pass

This is NOT a failure - it's intelligent test adaptation.

### Why Tests Skip

| Environment | JAR Present | Test Behavior | Reason |
|------------|-------------|---------------|---------|
| Local Mac/Linux | ❌ | Skip Java tests | No JAR downloaded locally |
| Docker Container | ✅ | Run all tests | JAR downloaded during build |
| CI with Docker | ✅ | Run all tests | JAR in container image |
| Unit Tests | N/A | Use stub | Testing logic, not Java |

## JAR Acquisition

### In Docker (Automatic)

Both `Dockerfile` and `Dockerfile.dev` download the JAR:

```dockerfile
RUN mkdir -p /app/languagetool && \
    cd /app/languagetool && \
    wget -q https://languagetool.org/download/LanguageTool-stable.zip && \
    unzip -q LanguageTool-stable.zip && \
    mv LanguageTool-*/*.jar . && \
    rm -rf LanguageTool-* LanguageTool-stable.zip
```

### For Local Testing (Optional)

If you want to run Java process tests locally:

```bash
# Download LanguageTool manually
mkdir -p /app/languagetool
cd /app/languagetool
wget https://languagetool.org/download/LanguageTool-stable.zip
unzip LanguageTool-stable.zip
mv LanguageTool-*/*.jar .

# Install Java 21
# Mac: brew install openjdk@21
# Linux: apt-get install openjdk-21-jre-headless
```

## Benefits of This Strategy

1. **Developer Experience**: No need to download 230MB JAR for local development
2. **Fast Iteration**: Unit tests and basic integration tests run instantly
3. **Production Fidelity**: Docker ensures production always has real implementation
4. **Graceful Degradation**: Service adapts rather than crashing
5. **Test Flexibility**: Can test both modes independently

## Testing Both Modes

### Testing Stub Mode

```python
def test_fallback_to_stub_when_jar_missing():
    """Verifies service gracefully falls back to stub when JAR is missing."""
    # Temporarily point to non-existent JAR
    # Verify stub implementation is used
```

### Testing Real Mode

```python
def test_java_process_starts_successfully():
    """Tests real Java process management (skips if JAR missing)."""
    # Only runs when JAR is present
    # Validates actual subprocess creation
```

## Best Practices

1. **Always test both modes** in your test suite
2. **Document skip expectations** in test docstrings
3. **Use Docker for integration tests** requiring real JAR
4. **Rely on stub for unit tests** - faster and more predictable
5. **Monitor skip patterns** in CI to detect configuration issues

## Troubleshooting

### All tests skipping unexpectedly

- Check `LANGUAGE_TOOL_JAR_PATH` environment variable
- Verify Docker image was built correctly
- Ensure Java 21 is installed in container

### Tests failing instead of skipping

- Check pytest skip conditions are properly implemented
- Verify Path.exists() check before Java operations

### Stub not activating when expected

- Check DI container configuration
- Verify jar_path.exists() logic in providers

## Summary

This dual-mode strategy provides the best of both worlds:

- **Fast local development** without heavyweight dependencies
- **Production-accurate testing** in Docker/CI environments
- **Graceful adaptation** to available resources
- **Clear test behavior** with appropriate skipping

The skipped tests are a feature, not a bug - they indicate the system is correctly adapting to the environment.
