Email Service Phase 4B: Production Integration & Service Boundary Alignment - Session Initialization

ULTRATHINK: Email Service Production Integration Context

You are implementing Phase 4B of the Email Service in the HuleEdu monorepo. This is a sophisticated microservices architecture with strict DDD/Clean Architecture patterns, zero-tolerance mypy policy, and established event-driven communication patterns.

CRITICAL SUCCESS STATUS: Phase 4A completed successfully with 296/296 passing tests and 100% integration test coverage. However, a CRITICAL SERVICE BOUNDARY MISALIGNMENT has been discovered that prevents any actual email delivery in production.

---
🎯 CURRENT STATUS: PRODUCTION INTEGRATION PHASE

EXACT PROBLEM RIGHT NOW:

We have successfully implemented a fully tested Email Service (296 tests passing), but discovered a complete service boundary disconnect:

1. **Identity Service publishes events that Email Service CANNOT consume:**
   - Identity publishes: `huleedu.identity.email.verification.requested.v1` (EmailVerificationRequestedV1)
   - Identity publishes: `huleedu.identity.password.reset.requested.v1` (PasswordResetRequestedV1)
   - Email Service consumes: `huleedu.email.notification.requested.v1` (NotificationEmailRequestedV1)

2. **Result: ZERO emails can be sent for user verification, password reset, or welcome messages**

3. **Additional Gap: Only mock email provider exists - no production SMTP provider**

Current Position: Complete testing infrastructure ready, but service cannot function in production due to event flow disconnect and missing SMTP provider.

---
📚 MANDATORY READING BEFORE STARTING (READ IN EXACT ORDER)

CRITICAL: Read these files IN ORDER before attempting any work:

1. **Current Implementation Context (FIRST PRIORITY)**
   - TASKS/EMAIL_SERVICE_PHASE4B_PRODUCTION_INTEGRATION_PLAN.md - Complete implementation plan and context
   - services/email_service/protocols.py - EmailProvider protocol and contracts
   - services/email_service/implementations/provider_mock_impl.py - Existing mock implementation pattern
   - services/email_service/di.py - Current DI container setup
   - services/email_service/config.py - Current configuration structure

2. **Service Communication Analysis (UNDERSTAND THE GAP)**
   - services/email_service/kafka_consumer.py - Current email service consumer (consumes EMAIL_NOTIFICATION_REQUESTED)
   - services/identity_service/implementations/event_publisher_impl.py - Identity event publishing (lines 103-127, 151-175)
   - libs/common_core/src/common_core/emailing_models.py - NotificationEmailRequestedV1 event model
   - libs/common_core/src/common_core/identity_models.py - EmailVerificationRequestedV1, PasswordResetRequestedV1 models
   - libs/common_core/src/common_core/event_enums.py - Event topics and mappings

3. **Architecture Standards and Rules (FOLLOW EXACTLY)**
   - .cursor/rules/000-rule-index.mdc - Master rule index for quick navigation
   - .cursor/rules/010-foundational-principles.mdc - Core architectural principles
   - .cursor/rules/020-architectural-mandates.mdc - Event-driven architecture requirements
   - .cursor/rules/030-event-driven-architecture-eda-standards.mdc - EDA implementation standards
   - .cursor/rules/042-async-patterns-and-di.mdc - DI and dependency patterns
   - .cursor/rules/050-python-coding-standards.mdc - Python code standards
   - .cursor/rules/075-test-creation-methodology.mdc - Testing standards

4. **Email Service Implementation (CURRENT STATE)**
   - services/email_service/event_processor.py - Email processing logic
   - services/email_service/templates/ directory - Existing Jinja2 templates
   - services/email_service/models_db.py - Database models and schema

5. **Identity Service Integration Points**
   - services/identity_service/di.py - DI container where orchestrator must be added
   - services/identity_service/kafka_consumer.py - May need modification for internal event routing

---
🏗️ WHAT WE'VE ACCOMPLISHED (Complete Context)

✅ **Phase 1-3: Production-Ready Email Service (100% Complete)**

- Integrated Kafka consumer with idempotency guarantees
- Mock email provider with Jinja2 template rendering system
- Prometheus metrics system (15+ business intelligence metrics)
- Complete event publishing architecture (EmailSentV1/EmailDeliveryFailedV1)
- Circuit breaker resilience patterns with ResilientKafkaPublisher
- Professional email templates (verification, password_reset, welcome)
- Database schema standardization with EventOutbox model
- Health endpoints and Docker integration operational

✅ **Phase 4A: Comprehensive Test Coverage (100% Complete - 296 Tests)**

**Files Created with Full Test Coverage:**

*Unit Tests (142 tests):*
- services/email_service/tests/unit/test_event_processor.py (13 tests, 509 LoC)
- services/email_service/tests/unit/test_kafka_consumer.py (27 tests, 561 LoC)
- services/email_service/tests/unit/test_template_renderer.py (31 tests, 419 LoC)
- services/email_service/tests/unit/test_email_provider.py (16 tests, 368 LoC)
- services/email_service/tests/unit/test_repository_basics.py (11 tests, 241 LoC)
- services/email_service/tests/unit/test_repository_operations.py (75 tests, 578 LoC)
- services/email_service/tests/unit/test_repository_errors.py (9 tests, 174 LoC)
- services/email_service/tests/unit/test_outbox_manager.py (13 tests, 626 LoC)

*Contract Tests (118 tests):*
- services/email_service/tests/contract/ - 9 files with comprehensive Pydantic validation
- Full event contract validation (EmailSentV1, EmailDeliveryFailedV1, NotificationEmailRequestedV1)
- Database model contract testing with Swedish character support
- API schema contract validation

*Integration Tests (36 tests):*
- services/email_service/tests/integration/test_email_workflow.py ✅ (11 tests)
- services/email_service/tests/integration/test_database_operations.py ✅ (9 tests)
- services/email_service/tests/integration/test_kafka_integration.py ✅ (7 tests)
- services/email_service/tests/integration/test_outbox_publishing.py ✅ (9 tests) - FIXED with database cleanup patterns

**CRITICAL FIXES APPLIED:**
- ✅ Database cleanup patterns implemented following file_service established methodology
- ✅ Unique message ID generation preventing constraint violations
- ✅ Complete test isolation with before/after database cleanup
- ✅ Swedish character support (åäöÅÄÖ) validated throughout all test layers

Current Test Metrics: 296/296 tests passing (100%)

---
❌ IMMEDIATE PROBLEM: SERVICE BOUNDARY DISCONNECT BLOCKS ALL EMAIL FUNCTIONALITY

**Root Cause Analysis:**

1. **Primary Issue: Event Topic Mismatch**
   - services/identity_service/implementations/event_publisher_impl.py publishes to:
     * `huleedu.identity.email.verification.requested.v1` (line 126)
     * `huleedu.identity.password.reset.requested.v1` (line 174) 
   - services/email_service/kafka_consumer.py consumes from:
     * `huleedu.email.notification.requested.v1` (line 50)
   - **Result: Complete communication failure**

2. **Secondary Issue: Data Model Incompatibility**
   - EmailVerificationRequestedV1 has: user_id, email, verification_token, expires_at, correlation_id
   - PasswordResetRequestedV1 has: user_id, email, token_id, expires_at, correlation_id  
   - NotificationEmailRequestedV1 expects: message_id, template_id, to, variables, category, correlation_id
   - **Models are completely different structures**

3. **Tertiary Issue: No Production Email Provider**
   - Only MockEmailProvider exists (services/email_service/implementations/provider_mock_impl.py)
   - No SMTP provider for actual email delivery
   - Configuration supports EMAIL_PROVIDER selection but only 'mock' works

**Real-World Impact:**
- ❌ User registration: No welcome emails sent
- ❌ Email verification: Users cannot verify accounts
- ❌ Password reset: Users cannot reset passwords
- ❌ Complete authentication flow breakdown

---
🔧 EXACT SOLUTION APPROACH (Phase 4B)

**Part 1: Service Boundary Alignment (CRITICAL)**

Create `services/identity_service/notification_orchestrator.py`:
- Listen to Identity Service's own published events
- Transform EmailVerificationRequestedV1 → NotificationEmailRequestedV1 with template_id="verification"
- Transform PasswordResetRequestedV1 → NotificationEmailRequestedV1 with template_id="password_reset"  
- Transform UserRegisteredV1 → NotificationEmailRequestedV1 with template_id="welcome"
- Publish to EMAIL_NOTIFICATION_REQUESTED topic that Email Service already consumes

**Part 2: SMTP Provider Implementation**

Create `services/email_service/implementations/provider_smtp_impl.py`:
- Implement EmailProvider protocol using aiosmtplib
- Namecheap Private Email configuration:
  * Host: mail.privateemail.com
  * Port: 587 with STARTTLS
  * Username: noreply@hule.education
  * Password: (from environment)
- Support HTML + text multipart messages
- Swedish character support (UTF-8 encoding)

**Part 3: Configuration & Provider Selection**

Update services/email_service/config.py and di.py:
- Add SMTP configuration fields
- Provider selection logic: mock (dev) vs smtp (prod)
- Environment-based provider switching

---
🎯 EXACT TASK RIGHT NOW

ULTRATHINK: Implement Service Boundary Bridge and SMTP Provider

Your immediate task is to create the missing service integration components:

1. **PRIORITY 1: Create NotificationOrchestrator**
   - File: services/identity_service/notification_orchestrator.py
   - Purpose: Transform Identity events → Email notification events
   - Integration: Add to identity_service DI container and wire to internal event consumption

2. **PRIORITY 2: Create SMTPEmailProvider**  
   - File: services/email_service/implementations/provider_smtp_impl.py
   - Purpose: Production email delivery via Namecheap Private Email
   - Requirements: aiosmtplib, multipart HTML/text, UTF-8 Swedish character support

3. **PRIORITY 3: Update Configuration and DI**
   - Update services/email_service/config.py with SMTP settings
   - Update services/email_service/di.py with provider selection logic
   - Update services/identity_service/di.py to include NotificationOrchestrator

4. **PRIORITY 4: Integration Testing**
   - Create services/email_service/tests/integration/test_smtp_provider.py
   - Test Swedish character support (ÅÄÖ)
   - Test multipart email generation

SUCCESS CRITERIA:
- Identity Service events trigger email notifications
- SMTP provider successfully sends emails via Namecheap
- Mock provider remains functional for development
- All 296 existing tests continue to pass
- Swedish character support maintained throughout

---
🏗️ CURRENT ENVIRONMENT STATUS

**Email Service State:**
- Email Service: ✅ Healthy and operational (localhost:8082/healthz)
- Email DB: ✅ Healthy (huleedu_email_db on port 5443)
- Current Test Count: ✅ 296/296 tests passing (100%)
- Mypy Status: ✅ Clean (zero errors across all files)
- Rule 075 Compliance: ✅ Perfect (zero @patch violations, behavioral testing)

**Service Dependencies:**
- Identity Service: ✅ Operational (publishes events but Email Service cannot consume them)
- Kafka: ✅ Running (topic routing functional, events being published)
- Redis: ✅ Available (outbox notifications working)

**Configuration Context:**
```
Development: EMAIL_PROVIDER=mock (current working state)
Production: EMAIL_PROVIDER=smtp (not implemented - will fail)

Required SMTP Config:
EMAIL_SMTP_HOST=mail.privateemail.com
EMAIL_SMTP_PORT=587  
EMAIL_SMTP_USERNAME=noreply@hule.education
EMAIL_SMTP_PASSWORD=<secret>
EMAIL_SMTP_USE_TLS=true
```

Test Directory Structure (Completed):
```
services/email_service/tests/
├── unit/                           ✅ 142 tests passing
├── contract/                       ✅ 118 tests passing  
└── integration/                    ✅ 36 tests passing
    ├── test_email_workflow.py      ✅ 11 tests
    ├── test_database_operations.py ✅ 9 tests
    ├── test_kafka_integration.py   ✅ 7 tests
    └── test_outbox_publishing.py   ✅ 9 tests (FIXED - database cleanup applied)
```

---
🎪 DEVELOPMENT METHODOLOGY

**Rule 075 Compliance Requirements:**
- NO @patch usage anywhere in new code
- AsyncMock(spec=Protocol) only for external boundaries
- Behavioral testing focus, not implementation details
- Swedish character testing mandatory (åäöÅÄÖ) in SMTP provider tests
- File size limits: <500 LoC per implementation file

**Architecture Standards:**
- Follow services/email_service/implementations/provider_mock_impl.py as implementation pattern
- Use established DI patterns from services/email_service/di.py
- Follow event transformation patterns from other service integrations
- Maintain strict protocol boundaries and Clean Architecture

**Implementation Dependencies:**
```python
# Required for SMTP provider
import aiosmtplib
from email.message import EmailMessage

# Required for notification orchestrator  
from common_core.emailing_models import NotificationEmailRequestedV1
from common_core.identity_models import EmailVerificationRequestedV1, PasswordResetRequestedV1, UserRegisteredV1
```

---
📋 IMMEDIATE NEXT ACTIONS

After creating the core components, you will need to:

1. **Validate Integration**: Test that Identity events → Email notifications → SMTP delivery
2. **Update Templates**: Ensure verification.html.j2, password_reset.html.j2, welcome.html.j2 handle new variables
3. **Cross-Service Testing**: Create integration tests that span Identity → Email services
4. **Production Configuration**: Document exact .env requirements for SMTP deployment

---
🚨 CRITICAL REMINDERS

1. **Immediate Focus**: Service boundary alignment is BLOCKING all email functionality
2. **Pattern Compliance**: Follow existing EmailProvider protocol implementation exactly
3. **No Over-Engineering**: Only implement mock + SMTP providers (no SendGrid, SES, etc.)
4. **Testing Standards**: Maintain Rule 075 compliance and Swedish character validation
5. **Configuration**: Use existing settings pattern from services/email_service/config.py

**CRITICAL CONTEXT**: The Email Service infrastructure is production-ready and fully tested, but cannot send any emails because Identity Service events never reach it. Your task is to create the missing bridge and production email provider.

**Current Progress**: Email Service 95% complete. Missing only: event bridge (20% of remaining work) + SMTP provider (80% of remaining work).

🧪 Begin by reading the referenced files in exact order, then implement the NotificationOrchestrator to bridge the service boundary gap, followed by the SMTP provider for production email delivery.

IMPORTANT: Do not use Task/Agent tools. Implement directly using Read, Write, Edit, and MultiEdit tools.