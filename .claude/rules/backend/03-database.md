# Database Standards

## ORM
- SQLAlchemy async with `asyncpg`
- **Strict ban on raw SQL**
- Each service has its own PostgreSQL database

## Database Access
```bash
# Always source .env first
source .env

# Access database
docker exec huleedu_<service>_db psql -U "$HULEEDU_DB_USER" -d huleedu_<service> -c "SQL"
```

## Environment Separation

| Environment | Config |
|-------------|--------|
| Development | Docker containers (default) |
| Production | External managed DBs |

## Commands
```bash
pdm run db-reset      # Reset development databases
pdm run db-seed       # Seed development data
```

**Detailed**: `.agent/rules/085-database-migration-standards.md`
