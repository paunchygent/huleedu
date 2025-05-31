---
trigger: model_decision
description: "Rule management guidelines. Follow when creating, updating, or removing rules in the HuleEdu codebase."
---

---
description: Read before attempting to edit .cursor/rules
globs: 
alwaysApply: false
---
===
# 999: Rule Management

## 1. Purpose
This rule defines the process for updating or proposing changes to this set of HuleEdu Development Rules. You (AI agent) **MUST** follow this process if instructed to modify the rules or if you identify a need for a rule change.

## 2. Rule Change Proposal Process

### 2.1. Rule: Discuss with User
    - If you identify a potential issue with an existing rule or a need for a new rule, **MUST** discuss this with the user to reach an agreement on the proposed change or addition.

### 2.2. Rule: Propose Changes via `edit_file`
    - Once a change is agreed upon, **MUST** use the `edit_file` tool to propose the modifications to the relevant `.mdc` rule file(s).
    - The `code_edit` **MUST** clearly show the proposed changes, using the `// ... existing code ...` marker.
    - The `instructions` field **MUST** explain the purpose of the rule change.

### 2.3. Rule: Update Rule Index
    - If a new rule file is created or an existing one is renamed, **MUST** propose an update to the [000-rule-index.mdc](mdc:000-rule-index.mdc) file using the `edit_file` tool to ensure the index remains accurate.

### 2.3. Rule: Ensure new rules have a frontmatter containing Rule Type and     
    Description. 

### 2.4. Rule: Explain Impact
    - When proposing a rule change, **SHOULD** explain the impact of the change on development practices or other rules.

### 2.5. Rule: Justify the Change
    - **SHOULD** provide a clear justification for the proposed change, explaining why it is necessary or beneficial (e.g., addresses an inconsistency, improves clarity, reflects a new architectural decision).

## 3. Rule Review and Approval
    - Rule changes **MUST** be reviewed and approved by a designated project lead (outside of your direct actions).

## 4. Maintaining Rule Consistency
    - After a rule change is approved and applied, **MUST** ensure your subsequent actions and code generation adhere to the updated rule set.
    - If you notice discrepancies or outdated information in other rules as a result of a change, **SHOULD** propose further updates as needed.

---
**This process ensures that our development rules remain accurate, relevant, and agreed upon.**
===