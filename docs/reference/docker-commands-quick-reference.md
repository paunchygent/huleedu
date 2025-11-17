# Docker Commands Quick Reference

## Most Common Commands

### 🚀 Fast Builds
```bash
# Parallel build with cache
pdm run build-parallel

# Fresh build all services (no cache + parallel)
pdm run dev-fresh

# Fresh build single service
pdm run dev-fresh-single file_service
```

### 🔧 Development Workflow
```bash
# Complete rebuild cycle
pdm run dev-rebuild

# Start services
pdm run dc-up

# View logs
pdm run dc-logs
pdm run dc-logs-service file_service
```

### 🧹 Maintenance
```bash
# Clean BuildKit cache
pdm run docker-builder-prune

# Full system reset
pdm run docker-reset
```

## Build Time Comparison

| Command | Typical Time | Use Case |
|---------|--------------|----------|
| `dev-fresh` | ~3-5 min | Complete rebuild, all services |
| `dev-fresh-single` | ~30-60s | Rebuild one service |
| `build-parallel` | ~1-2 min | Normal build with cache |
| `dc-build` | ~2-3 min | Legacy build (not optimized) |

## Pro Tips

1. **For fastest no-cache builds**: Always use `dev-fresh` instead of `dev-fresh-single` for multiple services
2. **Low on disk space?**: Run `docker-builder-prune` regularly
3. **Debugging builds?**: Use `dev-fresh-verbose` to see detailed output
4. **Building in CI/CD?**: Export these environment variables:
   ```bash
   export COMPOSE_DOCKER_CLI_BUILD=1
   export DOCKER_BUILDKIT=1
   ```

## Service-Specific Builds

```bash
# Build only what you need
pdm run build-service file_service
pdm run build-service content_service batch_orchestrator_service

# Fresh build specific services
pdm run dev-fresh-single file_service
pdm run dev-fresh-single api_gateway_service
```

Remember: BuildKit + Parallel = 🚀 Fast Builds!