# LTI 1.3 (LMS) Integration Plan (Weeks 2–6)

Objective
- Provide LTI 1.3 tool support: launch, NRPS (names/roles), AGS (assignments/grades) for one target LMS.

Scope
- In: LTI tool endpoints, deep linking (basic), grade passback, roster access (read), basic state projection to LMS.
- Out: Full multi-LMS certification matrix (phase 2), complex deep linking catalogs.

Architecture Option
- New microservice `lti_adapter_service` (preferred for isolation) or Gateway plugin. Follow service blueprint per `042` rules.

References
- Gateway: `services/api_gateway_service/*` (if embedding)
- Result data: `services/result_aggregator_service/*`
- Rules: `020`, `040-service-implementation-guidelines`, `041-fastapi-integration-patterns`, `070`

Deliverables
1. LTI Security Profile: JWKs, OIDC login/initiate login, launch endpoint handling nonce/state.
2. NRPS fetch: Class roster mapping to CMS entities.
3. AGS grade passback: Writeback of results from RAS to LMS.
4. Configurable LMS tenants: Per-tenant LTI registrations/secrets.
5. Tests: Contract tests with a mock LMS, E2E launch ➜ grade passback.

Work Packages
1) Service Scaffolding
   - Create `services/lti_adapter_service/` (Quart or FastAPI consistent with rules).
   - Endpoints: `/.well-known/jwks.json`, `/lti/login`, `/lti/launch`, `/lti/ags/*`, `/lti/nrps/*`.
   - Acceptance: Health/metrics live; jwks resolvable; basic flow mocked.

2) Security + Storage
   - Store registrations and keys (per LMS deployment) with Alembic migrations.
   - Validate id_token signatures and claims.
   - Acceptance: Valid launch end-to-end with mock credentials.

3) NRPS ➜ CMS
   - Map NRPS membership to `class_management_service` models and APIs.
   - Acceptance: Roster imported; students/classes visible via CMS API.

4) AGS ➜ RAS
   - Map internal results to AGS line items and score publish endpoints.
   - Acceptance: Grade writeback success; retries and error mapping verified.

5) Tests + Docs
   - Add integration tests (mock LMS). Update docs in `documentation/` and service README.

Dependencies
- LMS sandbox tenant, LTI client credentials.

Risks/Mitigations
- Claim variability between LMSs ➜ normalize with adapters and robust validation.

Definition of Done
- Launch/NRPS/AGS working against one LMS sandbox; CMS roster sync works; grade passback verified; tests pass.
