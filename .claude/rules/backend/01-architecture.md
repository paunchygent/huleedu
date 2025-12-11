# Backend Architecture

## Pattern
Event-driven microservices with **strict DDD/Clean Code** principles.

## File Size Limit
**<400-500 LoC** hard limit per file.

## Stack
- **Core**: Python 3.11, Quart, PDM monorepo, Dishka, Pydantic
- **Data**: PostgreSQL, SQLAlchemy async, asyncpg
- **Comms**: Kafka, aiohttp, Redis
- **Client-facing**: FastAPI

## Critical Constraints
- Always run `pdm <command>` **from repo root** — never from subdirectory
- Use **absolute imports** from root for cross-service dependencies
- Never use relative imports outside service directory

**Detailed**: `.agent/rules/010-foundational-principles.md`
