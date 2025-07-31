# Copy-Paste Prompt for New Claude Session

Copy and paste this exact prompt to start your new Claude session:

---

I need you to implement the Pending Content Pattern to fix a critical race condition in our microservices. A previous Claude session has already discovered the problem, validated the solution, and created a comprehensive implementation plan.

**CRITICAL**: Before doing ANYTHING else, read the full context and implementation guide at:
`/TASKS/NEW_CLAUDE_SESSION_PENDING_CONTENT_IMPLEMENTATION.md`

This document contains:
- The race condition problem discovered
- The validated solution (with passing tests) 
- All architectural rules you must read first
- A phased implementation plan
- Critical notes about NO backwards compatibility

**Your first action** should be to read that document completely, then follow its ULTRATHINK steps in order.

The race condition causes functional tests to hang because essays arrive before batch registration. The Pending Content Pattern stores these as "pending" instead of "excess" and reconciles them later.

Start by reading the implementation guide document, then the architectural rules it references, then begin Phase 1.

Current directory: `/Users/olofs_mba/Documents/Repos/huledu-reboot`