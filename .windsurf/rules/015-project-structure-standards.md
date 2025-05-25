---
description: "Standards for organizing files and directories in HuleEdu projects. Follow these for all project, service, and module structures."
globs: 
  - "**/*"
alwaysApply: true
---
# 015: Project Structure Standards

## 1. Purpose
Mandatory file and folder organization standards for the HuleEdu monorepo.

## 2. Root Directory

### 2.1. Allowed Root Files
```
README.md         # Project overview
LICENSE           # Project license
pyproject.toml    # PDM config
pdm.lock         # PDM lock file
docker-compose.yml # Docker config
.gitignore        # Git ignore rules
.pdm-python      # PDM Python version
```

### 2.2. Allowed Root Dirs
```
.git/           # Git data
.venv/          # PDM venv
.mypy_cache/    # Type checking
__pycache__/    # Python cache
.cursor/        # IDE config
common_core/    # Shared package
services/       # Microservices
scripts/        # Project scripts
TASKS/          # Project tasks
```

## 3. Scripts Directory

### 3.1. Structure
```
scripts/
├── docs/                    # Script documentation
│   ├── SETUP_GUIDE.md
│   └── DEPLOYMENT_GUIDE.md
├── setup_huledu_environment.sh
├── deploy.sh
└── utils/                   # Utilities
    ├── backup.sh
    └── maintenance.sh
```

### 3.2. Rules
- Docs in `scripts/docs/` only
- No script docs outside this dir
- Include purpose/usage in docs

## 4. Services Directory

### 4.1. Structure
```
services/
├── libs/                    # Shared libs
│   └── huleedu_service_libs/
├── content_service/         # Example service
│   ├── app.py
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── tests/
│   └── docs/
├── batch_service/
└── spell_checker_service/
```

### 4.2. Rules
- Service `README.md` at root
- Docs in `services/{name}/docs/`
- No service docs in root

## 5. Common Core

### 5.1. Structure
```
common_core/
├── src/common_core/
│   ├── __init__.py
│   ├── enums.py
│   ├── metadata_models.py
│   ├── pipeline_models.py
│   └── events/
├── tests/
└── README.md
```

## 6. TASKS Directory

### 6.1. Structure
```
TASKS/
├── PHASE_1.0.md           # Project tasks
├── PHASE_1.1.md
└── services/              # Service tasks
    ├── content_service/
    └── batch_service/
```

### 6.2. Rules
- Project tasks in root `TASKS/`
- Service tasks in `TASKS/services/{name}/`
- Clearly document scope

## 7. Documentation

### 7.1. README Files
- Root: Project overview
- Services: `services/{name}/README.md`
- Common Core: `common_core/README.md`
- No READMEs in `docs/` dirs

## 8. File Management

### 8.1. Creation Rules
1. Verify target directory
2. Follow structure standard
3. Create parent dirs if needed
4. Update rules for new patterns

### 8.2. Maintenance
- Update rules for new patterns
- Keep structure consistent
- Clean temporary files

## 9. Enforcement

### 9.1. AI Agent Rules
- Enforce structure
- Reject violations
- Suggest fixes
- Update rules as needed

### 9.2. Validation
- Validate before operations
- Propose corrections
- Maintain consistency
