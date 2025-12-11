---
id: "110-ai-agent-interaction-modes"
type: "workflow"
created: 2025-05-25
last_updated: 2025-11-22
scope: "all"
child_rules: ["110.1-planning-mode", "110.2-coding-mode", "110.3-testing-mode", "110.4-debugging-mode", "110.5-refactoring-linting-mode", "110.6-agentic-implementation-flow", "110.7-task-creation-and-decomposition-methodology"]
---
# 110: AI Agent Interaction Modes

## 1. General Interaction Principles

- **MUST** understand user request, ask user story questions (epic), codebase context, and applicable rules before action.
- **MUST** adhere to rules and HuleEdu architecture
- **MUST** use provided tools (no simulation)
- **MUST** explain tool actions briefly
- **MUST** structure responses clearly
- **MUST** cite sources with file and line numbers
- **MUST** update all relevant documentation as part of task completion

## 2. Operational Modes

- **Planning Mode**: Task analysis and execution planning
- **Coding Mode**: Code generation and modification
- **Testing Mode**: Test creation, execution, and evaluation
- **Debugging Mode**: Issue identification and resolution
- **Refactoring/Linting Mode**: Code improvement and style fixes

## 3. State Management
- **SHOULD** maintain context about current task, relevant files, and architectural constraints
===
