# Service Implementation

## Communication
- **Primary**: Async via Kafka
- **Secondary**: Sync HTTP for immediate queries
- **Strict**: No direct DB access between services

## HTTP Services
- `app.py`: Setup only (<150 LoC)
- Blueprints in `api/` directory

## Worker Services
- **Complex**: Standalone worker + API (e.g., `essay_lifecycle_service`)
- **Simple**: Integrated via `@app.before_serving`

## Dependency Injection (Dishka)
- Interfaces: `typing.Protocol` in `protocols.py`
- Providers: `Provider` classes in `di.py`
- Scopes: `APP` (singletons), `REQUEST` (per-operation)

**Detailed**: `.agent/rules/042-async-patterns-and-di.md`
