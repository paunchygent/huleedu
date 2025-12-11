# Docker Development

## Find Containers
```bash
docker ps | grep huleedu
```

## Commands
```bash
pdm run dev-start [service]       # Start without rebuilding
pdm run dev-build-start [service] # Build with cache then start
pdm run dev-build-clean [service] # Build without cache
pdm run dev-restart [service]     # Restart for code changes
pdm run dev-recreate [service]    # Recreate for env changes
pdm run dev-stop [service]        # Stop containers
pdm run dev-logs [service]        # Follow logs
pdm run dev-check                 # Check what needs rebuilding
```

## Debugging
Read `.agent/rules/046-docker-container-debugging.md`
