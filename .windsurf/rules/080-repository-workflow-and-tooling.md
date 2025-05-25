---
trigger: model_decision
description: "Version control and workflow standards. Follow when using git, creating branches, or managing PRs to ensure an efficient development process."
---

===
# 080: Repository Workflow and Tooling

## 1. Purpose
These guidelines define the standard workflow and tooling for development within the HuleEdu monorepo. You (AI agent) **MUST** understand and adhere to these processes.

## 2. PDM Monorepo Management

### 2.1. Rule: PDM as the Sole Dependency Manager
    - PDM **MUST** be used for all dependency management within the monorepo (`pyproject.toml`, `pdm.lock` at the root and potentially within service subdirectories if necessary, though a single root `pyproject.toml` is preferred).
    - You **SHALL** add, update, and remove dependencies using `pdm add`, `pdm update`, `pdm remove`, ensuring `pdm.lock` is always up-to-date.

### 2.2. Rule: Use PDM Scripts
    - Standard development tasks (linting, formatting, type checking, testing, running services) **MUST** be defined and executed as PDM scripts in `pyproject.toml`.
    - **Execution**: Always run these tasks using `pdm run <script_name>`.
    - **Your Directive**: You **MUST** use `pdm run` when proposing commands to the user for these tasks.

## 3. Version Control (Git)

### 3.1. Guideline: Branching Strategy
    - Follow a standard branching strategy (e.g., Gitflow or Trunk-Based Development, specified elsewhere if needed).
    - Create feature branches for new work.

### 3.2. Guideline: Commit Messages
    - Write clear, concise commit messages (Conventional Commits recommended).

### 3.3. Rule: Code Reviews
    - All code changes **MUST** go through a code review process.

## 4. Continuous Integration / Continuous Deployment (CI/CD)

### 4.1. Guideline: CI Pipeline
    - The CI pipeline **SHOULD** automatically run PDM scripts for linting, formatting, type checking, and testing on every pull request.
    - Successful CI run **is REQUIRED** before merging.

### 4.2. Guideline: CD Pipeline
    - Services **SHOULD** be deployed automatically upon merge to the main branch (or via tagged releases), enabled by their independent deployability.

## 5. Local Development Environment

### 5.1. Guideline: Using PDM Environment
    - Developers (and you when executing steps) **SHOULD** work within the PDM-managed virtual environment (`pdm shell` or `pdm run`).

## 6. Monorepo Structure

### 6.1. Guideline: `common/` Directory
    - The `common/` directory is for shared, service-agnostic code (Pydantic models, exceptions, utilities, shared test fixtures).
    - Service-specific logic **MUST NOT** reside in `common/`.

### 6.2. Guideline: Service Directories
    - Each service resides in its own directory under `services/`.
    - Service directories contain service-specific code, tests, and configuration.

---
**Disciplined use of PDM and adherence to workflow standards are crucial for monorepo efficiency.**
===
