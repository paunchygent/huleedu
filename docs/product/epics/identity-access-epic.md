---
type: epic
id: EPIC-001
title: Identity & Access Management
status: draft
phase: 1
sprint_target: TBD
created: 2025-11-27
last_updated: 2025-11-27
---

# EPIC-001: Identity & Access Management

## Summary

Define and implement school-level authentication and role-based access control for the HuleEdu platform. This epic focuses on basic RBAC for teacher and school admin roles, enabling secure access to CJ Assessment workflows without enterprise SSO complexity.

**Business Value**: Enables multi-user access with role-based permissions for school deployments.

**Scope Boundaries**:
- **In Scope**: School admin role, teacher role, basic account validation, CJ Assessment permissions
- **Out of Scope**: Enterprise OIDC/SSO, district admin, SAML, multi-tenant orchestration, SCIM

## User Stories

### US-001.1: Teacher Login
**As a** teacher
**I want to** log in with email/password
**So that** I can access my batches and assessment results.

**Acceptance Criteria**:
- [ ] Teacher logs in via `/v1/auth/login`
- [ ] JWT issued with user_id and role claims
- [ ] Session persists across browser refreshes via refresh token

### US-001.2: School Admin Role
**As a** school admin
**I want to** manage teacher accounts for my school
**So that** I can onboard and offboard staff without platform support.

**Acceptance Criteria**:
- [ ] Admin can create teacher accounts
- [ ] Admin can deactivate teacher accounts
- [ ] Admin can view all teachers in their school
- [ ] Role assignments limited to school scope

### US-001.3: CJ Assessment Permissions
**As a** teacher
**I want to** only access my own batches and results
**So that** student data remains private to my classes.

**Acceptance Criteria**:
- [ ] Batch queries filter by owner_id
- [ ] Cross-user batch access returns 404
- [ ] Result queries validate ownership

## Technical Requirements

### Authentication
- **Method**: Email/password with JWT tokens
- **Token Structure**: user_id, role, school_id claims
- **Refresh**: Long-lived refresh tokens, short-lived access tokens (15min)

### Authorization
- **Role Model**: teacher, school_admin
- **Enforcement**: API Gateway middleware
- **Scope**: Per-school isolation (school_id filtering)

### Service Components
- **Identity Service**: `services/identity_service/` (existing)
- **API Gateway**: `services/api_gateway_service/` (existing)

## Dependencies

- Identity Service operational
- API Gateway authentication middleware

## Notes

- Enterprise SSO (Google OIDC, SAML) deferred to future epic
- Multi-tenant district support deferred
- Focus on proving CJ Assessment workflow with basic auth
