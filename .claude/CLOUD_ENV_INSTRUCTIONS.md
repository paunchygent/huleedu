# Cloud Environment Instructions for Claude Instances

**READ THIS FIRST when working in Claude Code cloud environment (Claude.ai web interface)**

## Environment Overview

You are running in a **sandboxed cloud environment**, NOT on the user's local machine. This has critical implications for what you can and cannot do.

### Environment Specifics
- **OS**: Linux (Ubuntu Noble 24.04)
- **User**: root
- **Working Directory**: `/home/user/huledu-reboot` (repository root)
- **Shell**: bash (`/bin/bash`)
- **Python**: 3.11.14 (matches project requirements)
- **Package Manager**: PDM 2.26.1 (installed in `/root/.local/bin/`)

### Git Configuration
- Repository is already cloned
- Git remote uses local proxy: `http://local_proxy@127.0.0.1:59249/git/paunchygent/huledu-reboot`
- Git operations (status, log, commit, push) work normally
- You are on a feature branch named like `claude/explore-env-setup-<session-id>`
- **ALWAYS** develop and commit on your assigned feature branch (check git status first)

---

## ✅ WHAT WORKS (Use These Confidently)

### 1. Python Development Tools - FULLY FUNCTIONAL

**PDM (Python Dependency Manager)**
```bash
# PDM is installed but not in PATH by default
# Always export PATH first in Bash commands:
export PATH=$PATH:/root/.local/bin && pdm <command>

# Or use the venv directly:
.venv/bin/python
.venv/bin/pytest
```

**Dependencies**
- 285/287 packages installed successfully (98.9%)
- Only 2 spaCy language models failed (network restrictions)
- All Python development dependencies are available

**Code Quality Tools**
```bash
# These work perfectly:
export PATH=$PATH:/root/.local/bin && pdm run lint-all
export PATH=$PATH:/root/.local/bin && pdm run lint-fix
export PATH=$PATH:/root/.local/bin && pdm run format-all
export PATH=$PATH:/root/.local/bin && pdm run typecheck-all
export PATH=$PATH:/root/.local/bin && pdm run typecheck-libs

# mypy is also available directly:
mypy --version  # Already in PATH
```

### 2. Testing - PARTIALLY FUNCTIONAL

**What Works:**
```bash
# Run tests directly via venv (RECOMMENDED):
.venv/bin/pytest <test_path> -v

# Examples:
.venv/bin/pytest libs/common_core/tests/test_grade_scales.py -v
.venv/bin/pytest services/llm_provider_service/tests/unit/ -v
.venv/bin/pytest -m unit  # Unit tests only

# The PDM test commands work:
export PATH=$PATH:/root/.local/bin && pdm run test-all
```

**What Doesn't Work:**
- `pdm run pytest-root` script has shell compatibility issues
- Tests marked with `@pytest.mark.docker` will fail (no Docker)
- Tests marked with `@pytest.mark.e2e` will fail (require Docker)
- Integration tests requiring external services (Kafka, PostgreSQL, Redis) will fail

**Best Practice:**
Always use `.venv/bin/pytest` directly rather than the pytest-root wrapper script.

### 3. File Operations - FULLY FUNCTIONAL

Use the specialized tools (Read, Write, Edit, Glob, Grep) rather than bash commands:
- ✅ Read files: Use `Read` tool
- ✅ Search files: Use `Glob` tool
- ✅ Search content: Use `Grep` tool
- ✅ Edit files: Use `Edit` tool
- ✅ Write files: Use `Write` tool

### 4. Git Operations - FULLY FUNCTIONAL

```bash
git status
git log
git diff
git add <files>
git commit -m "message"
git push -u origin <branch-name>
```

**Remember:**
- Always push to your assigned feature branch (starts with `claude/`)
- Use proper commit message format
- Git operations work through the local proxy

### 5. Basic Unix Tools - AVAILABLE

These commands work (all in `/usr/bin`):
- `grep`, `awk`, `sed`, `cut`, `sort`, `uniq`
- `find`, `ls`, `cat`, `head`, `tail`
- `wc`, `tr`, `xargs`

---

## ❌ WHAT DOESN'T WORK (Critical Limitations)

### 1. Docker - COMPLETELY UNAVAILABLE

**Docker daemon CANNOT start** due to kernel restrictions:
- Missing iptables/nftables support
- Missing overlay filesystem support
- This is inherent to the sandboxed environment and cannot be fixed

**Impact:**
```bash
# ALL OF THESE WILL FAIL:
pdm run dev-*         # Any dev-* commands
pdm run prod-*        # Any prod-* commands
pdm run db-*          # Any db-* commands
docker-compose        # Not functional
docker build          # Not functional
docker run            # Not functional
```

### 2. Database Operations - UNAVAILABLE

- Cannot access PostgreSQL containers (no Docker)
- Cannot run database migrations (no Docker)
- Cannot seed development data (no Docker)
- Database CLI commands will fail

### 3. Service Deployment - UNAVAILABLE

- Cannot start services locally
- Cannot test HTTP endpoints directly
- Cannot run the full stack
- Cannot validate service-to-service communication

### 4. Environment Variables

- No `.env` file exists in the repository
- Cannot access secrets or service configuration
- Tests requiring environment variables may fail

---

## 🎯 RECOMMENDED WORKFLOW

### For Code Review Tasks

```bash
# 1. Check what branch you're on
git status

# 2. Read the code to review
# Use Read, Glob, Grep tools

# 3. Run linting
export PATH=$PATH:/root/.local/bin && pdm run lint-all

# 4. Run formatting check
export PATH=$PATH:/root/.local/bin && pdm run format-all --check

# 5. Run type checking
export PATH=$PATH:/root/.local/bin && pdm run typecheck-all

# 6. Run unit tests
.venv/bin/pytest libs/common_core/tests/ -v -m unit
```

### For Implementation Tasks

```bash
# 1. Read relevant files and understand the codebase
# Use Read, Glob, Grep tools

# 2. Make code changes
# Use Edit or Write tools

# 3. Run formatters
export PATH=$PATH:/root/.local/bin && pdm run format-all

# 4. Run linters and fix issues
export PATH=$PATH:/root/.local/bin && pdm run lint-fix

# 5. Run type checking
export PATH=$PATH:/root/.local/bin && pdm run typecheck-all

# 6. Run tests
.venv/bin/pytest <relevant_test_path> -v

# 7. Commit and push
git add <files>
git commit -m "feat: description of changes"
git push -u origin <branch-name>
```

### For Bug Investigation

```bash
# 1. Search for relevant code
# Use Grep tool to search for keywords

# 2. Read the problematic code
# Use Read tool

# 3. Look at test failures
.venv/bin/pytest <test_path> -v --tb=short

# 4. Check git history
git log --oneline --graph -20
git blame <file>

# 5. Review related files
# Use Glob to find related files
```

---

## 🚨 COMMON PITFALLS & HOW TO AVOID THEM

### 1. "Docker Not Available" Confusion

**Problem:** User instructions might say "build and test the service"

**Solution:** Clarify with user or adapt:
- Instead of: "Build the Docker image and test"
- Do: "Run unit tests and static analysis"
- Explain Docker limitation if unclear

### 2. PATH Issues with PDM

**Problem:** `pdm` command not found

**Solution:** Always use:
```bash
export PATH=$PATH:/root/.local/bin && pdm <command>
```

Or use venv directly:
```bash
.venv/bin/python
.venv/bin/pytest
```

### 3. pytest-root Script Fails

**Problem:** The `pdm run pytest-root` script has shell compatibility issues

**Solution:** Use pytest directly via venv:
```bash
.venv/bin/pytest <test_path> -v
```

### 4. Test Discovery Issues

**Problem:** pytest says "no tests ran" or "not found"

**Solution:**
- Use relative paths from repository root
- Check if test file actually exists: `ls <test_path>`
- Use glob patterns: `.venv/bin/pytest services/*/tests/unit/ -v`

### 5. Environment Variables Missing

**Problem:** Tests fail due to missing environment variables

**Solution:**
- No .env file exists in cloud environment
- Tests requiring real credentials will fail
- Focus on tests that use mocks or don't need external services

### 6. Database Migration Commands Fail

**Problem:** `pdm run db-reset` or similar fails

**Solution:**
- Cannot run these in cloud environment (require Docker)
- Instead: Review migration files manually
- Validate SQL syntax and schema changes statically

---

## 📋 FIRST STEPS CHECKLIST

When starting a new task in this environment:

```bash
# 1. Check your git status and branch
git status

# 2. Verify you're in repo root
pwd  # Should be /home/user/huledu-reboot

# 3. Review recent commits to understand context
git log --oneline -10

# 4. Understand the task requirements
# Read relevant documentation files

# 5. If implementing code:
#    - Read existing code patterns
#    - Follow established conventions
#    - Use specialized tools (Read, Edit, Grep, Glob)

# 6. Before committing:
#    - Run formatters: pdm run format-all
#    - Run linters: pdm run lint-fix
#    - Run type checks: pdm run typecheck-all
#    - Run relevant tests: .venv/bin/pytest <path> -v

# 7. Commit and push to your feature branch
git add <files>
git commit -m "type: description"
git push -u origin <branch-name>
```

---

## 🔧 DEBUGGING TIPS

### When Commands Fail

1. **Check PATH first:**
   ```bash
   echo $PATH
   which pdm
   which python
   ```

2. **Use absolute paths if needed:**
   ```bash
   /root/.local/bin/pdm run lint-all
   .venv/bin/pytest tests/
   ```

3. **Check file existence:**
   ```bash
   ls -la <file>
   find . -name "<pattern>"
   ```

4. **Read error messages carefully:**
   - "Docker daemon not running" = Expected, Docker unavailable
   - "command not found" = PATH issue or command unavailable
   - "No such file or directory" = Check path from repo root

### When Tests Fail

1. **Run with verbose output:**
   ```bash
   .venv/bin/pytest <path> -v --tb=short
   ```

2. **Check test markers:**
   ```bash
   # Skip Docker tests:
   .venv/bin/pytest <path> -v -m "not docker"

   # Run only unit tests:
   .venv/bin/pytest <path> -v -m unit
   ```

3. **Isolate the failure:**
   ```bash
   # Run single test file
   .venv/bin/pytest <test_file> -v

   # Run single test
   .venv/bin/pytest <test_file>::<test_name> -v
   ```

---

## 📚 Reference: Project Structure

```
/home/user/huledu-reboot/          # Repository root (always your working dir)
├── .venv/                         # Virtual environment (PDM created)
├── .claude/                       # Claude-specific instructions and rules
│   ├── rules/                     # Project standards and patterns
│   ├── HANDOFF.md                # Cross-service context (read first!)
│   └── README_FIRST.md           # Critical task context
├── libs/                          # Shared libraries
│   ├── common_core/              # Core domain models and events
│   └── huleedu_service_libs/     # Service utilities
├── services/                      # Microservices
│   ├── llm_provider_service/
│   ├── cj_assessment_service/
│   └── ...
├── scripts/                       # Utility scripts
├── tests/                         # Cross-service integration tests
├── pyproject.toml                # PDM configuration and scripts
└── pdm.lock                      # Locked dependencies
```

---

## 💡 BEST PRACTICES

### 1. Always Start by Reading Context

```bash
# Read the project instructions
# Use Read tool on: CLAUDE.md

# Read the rule index
# Use Read tool on: .claude/rules/000-rule-index.mdc

# Read handoff documentation
# Use Read tool on: .claude/HANDOFF.md
```

### 2. Use Specialized Tools Over Bash

**Prefer:**
- `Read` tool over `cat`
- `Grep` tool over `grep` command
- `Glob` tool over `find` command
- `Edit` tool over `sed`
- `Write` tool over redirection

**Why:** These tools are optimized for the environment and provide better context management.

### 3. Test Before Committing

**Always run:**
1. Format: `pdm run format-all`
2. Lint: `pdm run lint-fix`
3. Type check: `pdm run typecheck-all`
4. Tests: `.venv/bin/pytest <relevant_path> -v`

### 4. Commit Messages

Follow conventional commits:
```bash
feat: add new feature
fix: resolve bug
refactor: restructure code
test: add or update tests
docs: update documentation
chore: maintenance task
```

### 5. Communication with User

When Docker limitations affect the task:
- **Be proactive:** Mention the limitation early
- **Offer alternatives:** Suggest what you CAN do instead
- **Be specific:** Explain exactly what won't work and why

Example:
> "I cannot start the service in Docker to test the endpoint directly due to cloud environment limitations. However, I can:
> 1. Implement the endpoint code following existing patterns
> 2. Run unit tests to verify the logic
> 3. Run static analysis (linting, type checking)
> 4. Review the code for correctness
>
> Would you like me to proceed with this approach?"

---

## 🎓 LEARNING FROM ERRORS

### Common Error Messages and What They Mean

| Error Message | What It Means | What To Do |
|--------------|---------------|------------|
| "Docker daemon not running" | Docker unavailable | Use non-Docker alternatives |
| "command not found" (pdm) | PATH issue | Export PATH or use absolute path |
| "No such file or directory" | Wrong path | Check path from repo root |
| "bad substitution" (pytest-root) | Shell compatibility issue | Use `.venv/bin/pytest` directly |
| "403 Forbidden" (spacy models) | Network restriction | Expected, ignore if not critical |
| "not found: <test>::<class>::<method>" | Test path syntax issue | Use simpler path or check test exists |

---

## ✨ SUMMARY: Your Superpowers in This Environment

You CAN:
- ✅ Read and analyze any code in the repository
- ✅ Make code changes (edit, write new files)
- ✅ Run Python scripts and tools
- ✅ Execute linting, formatting, type checking
- ✅ Run unit tests and integration tests (non-Docker)
- ✅ Use git (commit, push, create branches/PRs)
- ✅ Search code with advanced patterns
- ✅ Analyze test results and debug issues

You CANNOT:
- ❌ Build or run Docker containers
- ❌ Start services locally
- ❌ Access databases (PostgreSQL, Redis, Kafka)
- ❌ Run end-to-end tests requiring full stack
- ❌ Execute Docker-dependent scripts

**Your primary value:** Code analysis, static verification, unit testing, and implementation following established patterns.

---

## 🔄 WHEN TO UPDATE THIS DOCUMENT

If you discover:
- New working commands or tools
- New limitations or restrictions
- Better workflows or patterns
- Common errors and solutions

Add them to this document to help future Claude instances!

---

**Last Updated:** 2025-11-09 (Initial cloud environment exploration)
**Environment Version:** Claude Code Cloud (claude.ai web interface)
