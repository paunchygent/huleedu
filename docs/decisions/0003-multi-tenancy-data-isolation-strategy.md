---
type: decision
id: ADR-0003
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0003: Multi-Tenancy Data Isolation Strategy

## Status
Proposed

## Context
The HuleEdu platform is expanding from a single-organization deployment to supporting multiple tenants (schools and districts). This requires a data isolation strategy that ensures:

1. **Security**: Tenant data must be completely isolated to prevent cross-tenant access
2. **Performance**: Queries must be efficient and not suffer from multi-tenant overhead
3. **Scalability**: The solution must scale to hundreds of tenants without degradation
4. **Operational Simplicity**: Database management, backups, and migrations should remain straightforward
5. **Cost Efficiency**: Infrastructure costs should scale linearly with tenant count

Current state: Single-tenant deployment with no tenant isolation mechanisms. All services use a single PostgreSQL database per service with no tenant partitioning.

The platform uses event-driven microservices with strict DDD boundaries, where each service owns its data and communicates via Kafka events.

## Decision
Implement **row-level tenant isolation** using a `tenant_id` column with composite indexes:

1. **Database Schema Changes**:
   - Add `tenant_id UUID NOT NULL` column to all core tables (batches, essays, users, results)
   - Create composite indexes: `(tenant_id, primary_key)` and `(tenant_id, frequently_queried_fields)`
   - Add CHECK constraints to ensure tenant_id is always populated

2. **Tenant Context Propagation**:
   - Identity Service issues JWT with `tenant_id` claim
   - API Gateway extracts `tenant_id` and adds `X-Tenant-ID` header to all downstream requests
   - Services validate and use `tenant_id` from header for all database operations

3. **Repository Pattern Enforcement**:
   - All repository methods automatically filter by `tenant_id` from request context
   - Use SQLAlchemy filter mixins to ensure tenant isolation at the ORM level
   - Dishka DI provides tenant-scoped repository instances

4. **Cache Isolation**:
   - Redis keys use prefix pattern: `tenant:{tenant_id}:{service}:{key}`
   - TTL policies remain service-specific but keys are tenant-namespaced

5. **Event Envelope Enhancement** (PROPOSED - not yet implemented):
   - Add `tenant_id` field to `EventEnvelope` for cross-service event propagation
   - Event consumers validate tenant context before processing
   - Note: Current EventEnvelope in `libs/common_core/` does not have tenant_id

## Consequences

### Positive
- **Simple Implementation**: No schema changes or connection pooling complexity
- **Query Performance**: Composite indexes make tenant-filtered queries fast
- **Operational Simplicity**: Standard backup, migration, and monitoring tools work unchanged
- **Cost Efficient**: No database multiplication or complex sharding infrastructure
- **Development Velocity**: Developers work with familiar single-database patterns
- **Flexible Scaling**: Can migrate individual large tenants to dedicated schemas/databases later

### Negative
- **Query Discipline Required**: Developers must remember to filter by tenant_id
- **Index Overhead**: Additional indexes consume storage and slow down writes slightly
- **No Database-Level Isolation**: Misconfigured queries could theoretically leak data (mitigated by testing)
- **Shared Resource Limits**: All tenants share database connection pool and IOPS

## Alternatives Considered

1. **Database-per-Tenant**: Each tenant gets a dedicated PostgreSQL database
   - Rejected: Operational complexity (hundreds of databases), expensive infrastructure, difficult connection pooling
   - Benefit would be absolute isolation and per-tenant performance tuning

2. **Schema-per-Tenant**: Each tenant gets a PostgreSQL schema within shared database
   - Rejected: Complex migration management (N schemas × M services), search_path complexity, limited PostgreSQL schema count
   - Similar operational overhead to database-per-tenant without the isolation benefits

3. **Hybrid Approach**: Row-level for most tenants, dedicated database for enterprise customers
   - Deferred: Start with row-level, add enterprise tier later if needed
   - Complexity not justified without clear enterprise demand

4. **No Isolation** (application-layer trust only): Rely on application code to filter data
   - Rejected: Unacceptable security risk, no defense in depth

## Related ADRs
- ADR-0005: Event Schema Versioning Strategy (tenant_id in EventEnvelope)

## References
- TASKS/assessment/multi-tenancy-implementation-plan.md
- .claude/rules/020-architectural-mandates.md (service boundaries)
- .claude/rules/042-async-patterns-and-di.md (Dishka DI for request-scoped tenant context)
- .claude/rules/070-testing-and-quality-assurance.md (isolation testing)
