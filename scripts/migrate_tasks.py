#!/usr/bin/env python3
"""
Task migration script: Move files from .claude/work/tasks/ to TASKS/
Generates proper frontmatter according to TASKS/_REORGANIZATION_PROPOSAL.md
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import yaml

# Source and destination
SOURCE_DIR = Path("/Users/olofs_mba/Documents/Repos/huledu-reboot/.claude/work/tasks")
TASKS_DIR = Path("/Users/olofs_mba/Documents/Repos/huledu-reboot/TASKS")

# Migration mappings: filename -> (dest_domain, dest_subdir, new_id, status)
MIGRATION_MAP = {
    # Phase 1: Active In-Progress Tasks
    "TASK-CJ-BATCH-STATE-AND-COMPLETION-FIXES.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "cj-batch-state-and-completion-fixes",
        "status": "in_progress",
        "priority": "high",
        "service": "cj_assessment_service",
    },
    "TASK-CJ-LLM-SERIAL-BUNDLE-VALIDATION-FIXES.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "cj-llm-serial-bundle-validation-fixes",
        "status": "in_progress",
        "priority": "high",
        "service": "cj_assessment_service",
    },
    "TASK-FIX-ELS-TRANSACTION-BOUNDARY-VIOLATIONS.md": {
        "domain": "infrastructure",
        "subdir": None,
        "new_id": "fix-els-transaction-boundary-violations",
        "status": "in_progress",
        "priority": "high",
        "service": "essay_lifecycle_service",
    },
    # Phase 1: Blocked Tasks (awaiting approval)
    "TASK-LPS-RATE-LIMITING-IMPLEMENTATION-2025-11-21.md": {
        "domain": "infrastructure",
        "subdir": None,
        "new_id": "lps-rate-limiting-implementation",
        "status": "blocked",
        "priority": "high",
        "service": "llm_provider_service",
    },
    "TASK-CROSS-SERVICE-TEST-REFACTORING.md": {
        "domain": "architecture",
        "subdir": None,
        "new_id": "cross-service-test-boundary-refactor",
        "status": "blocked",
        "priority": "medium",
        "service": "",
    },
    # Phase 1: TODO Tasks
    "TASK-CJ-ASSESSMENT-CODE-HARDENING.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "cj-assessment-code-hardening",
        "status": "in_progress",
        "priority": "high",
        "service": "cj_assessment_service",
    },
    "TASK-CONTENT-SERVICE-IDEMPOTENT-UPLOADS.md": {
        "domain": "content",
        "subdir": None,
        "new_id": "content-service-idempotent-uploads",
        "status": "research",
        "priority": "medium",
        "service": "content_service",
    },
    "TASK-ENG5-RUNNER-ASSUMPTION-HARDENING.md": {
        "domain": "programs",
        "subdir": "eng5",
        "new_id": "eng5-runner-assumption-hardening",
        "status": "in_progress",
        "priority": "high",
        "service": "",
    },
    "TASK-ENG5-RUNNER-TESTING-PLAN.md": {
        "domain": "programs",
        "subdir": "eng5",
        "new_id": "eng5-runner-testing-plan",
        "status": "research",
        "priority": "medium",
        "service": "",
    },
    # Phase 2: Consolidation - Main files (others will be archived)
    "TASK-LLM-BATCH-STRATEGY.md": {
        "domain": "integrations",
        "subdir": None,
        "new_id": "llm-batch-strategy-serial-bundle",
        "status": "completed",
        "priority": "high",
        "service": "llm_provider_service",
    },
    "TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "fix-anchor-essay-infrastructure",
        "status": "completed",
        "priority": "high",
        "service": "essay_lifecycle_service",
    },
    "TASK-FIX-CJ-ANCHOR-FINALIZATION-AND-MONITORING.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "fix-cj-anchor-finalization-monitoring",
        "status": "completed",
        "priority": "high",
        "service": "cj_assessment_service",
    },
    "TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "fix-cj-llm-prompt-construction",
        "status": "completed",
        "priority": "high",
        "service": "cj_assessment_service",
    },
    # Phase 2: Archive tasks
    "TASK-CJ-BATCHMONITOR-EMBED-AND-RECOVER-2025-11-21.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "cj-batchmonitor-embed-recovery",
        "status": "archived",
        "priority": "high",
        "service": "cj_assessment_service",
    },
    "TASK-CJ-COMPLETION-EVENT-IDEMPOTENCY-2025-11-21.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "cj-completion-event-idempotency",
        "status": "archived",
        "priority": "high",
        "service": "cj_assessment_service",
    },
    "TASK-LLM-QUEUE-EXPIRY-METRICS-FIX.md": {
        "domain": "integrations",
        "subdir": None,
        "new_id": "llm-queue-expiry-metrics-fix",
        "status": "archived",
        "priority": "high",
        "service": "llm_provider_service",
    },
    "TASK-LLM-SERIAL-BUNDLING.md": {
        "domain": "integrations",
        "subdir": None,
        "new_id": "llm-serial-bundling-design",
        "status": "archived",
        "priority": "high",
        "service": "llm_provider_service",
    },
    "TASK-FIX-ELS-BATCH-REGISTRATION-TRANSACTION-FAILURE.md": {
        "domain": "infrastructure",
        "subdir": None,
        "new_id": "fix-els-batch-registration-transaction",
        "status": "archived",
        "priority": "high",
        "service": "essay_lifecycle_service",
    },
    "TASK-FIX-PROMPT-REFERENCE-PROPAGATION-AND-BCS-DLQ-TIMEOUT.md": {
        "domain": "infrastructure",
        "subdir": None,
        "new_id": "fix-prompt-propagation-bcs-dlq",
        "status": "archived",
        "priority": "high",
        "service": "",
    },
    "TASK-LOGGING-FILE-PERSISTENCE-AND-DOCKER-CONFIG.md": {
        "domain": "infrastructure",
        "subdir": None,
        "new_id": "logging-file-persistence-docker-rotation",
        "status": "archived",
        "priority": "medium",
        "service": "",
    },
    "TASK-LOKI-LOGGING-OTEL-ALIGNMENT-AND-CARDINALITY-FIX.md": {
        "domain": "infrastructure",
        "subdir": None,
        "new_id": "loki-cardinality-otel-alignment",
        "status": "archived",
        "priority": "medium",
        "service": "",
    },
    "CONTRACTS-BEFORE-AFTER.md": {
        "domain": "architecture",
        "subdir": None,
        "new_id": "cj-lps-contracts-refactor-analysis",
        "status": "archived",
        "priority": "medium",
        "service": "",
    },
    # LLM Batch Strategy consolidation files (to archive)
    "TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION-CHECKLIST.md": {
        "domain": "integrations",
        "subdir": None,
        "new_id": "llm-batch-strategy-checklist",
        "status": "archived",
        "priority": "high",
        "service": "llm_provider_service",
    },
    "TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION.md": {
        "domain": "integrations",
        "subdir": None,
        "new_id": "llm-batch-strategy-implementation",
        "status": "archived",
        "priority": "high",
        "service": "llm_provider_service",
    },
    "TASK-LLM-BATCH-STRATEGY-LPS-IMPLEMENTATION.md": {
        "domain": "integrations",
        "subdir": None,
        "new_id": "llm-batch-strategy-lps-implementation",
        "status": "archived",
        "priority": "high",
        "service": "llm_provider_service",
    },
    "TASK-LLM-BATCH-STRATEGY-PRE-CONTRACTS-AND-TESTS.md": {
        "domain": "integrations",
        "subdir": None,
        "new_id": "llm-batch-strategy-pre-contracts-tests",
        "status": "archived",
        "priority": "high",
        "service": "llm_provider_service",
    },
    "TASK-LLM-BATCH-STRATEGY-CJ-CONFIG.md": {
        "domain": "integrations",
        "subdir": None,
        "new_id": "llm-batch-strategy-cj-config",
        "status": "archived",
        "priority": "high",
        "service": "cj_assessment_service",
    },
    "TASK-LLM-SERIAL-BUNDLE-METRICS-AND-DIAGNOSTICS-FIX.md": {
        "domain": "integrations",
        "subdir": None,
        "new_id": "llm-serial-bundle-metrics-diagnostics",
        "status": "archived",
        "priority": "high",
        "service": "llm_provider_service",
    },
    # Consolidation - Anchor files (to archive)
    "TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE-CHECKLIST.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "fix-anchor-essay-infrastructure-checklist",
        "status": "archived",
        "priority": "high",
        "service": "essay_lifecycle_service",
    },
    "TASK-FIX-CJ-ANCHOR-FINALIZATION-AND-MONITORING-CHECKLIST.md": {
        "domain": "assessment",
        "subdir": None,
        "new_id": "fix-cj-anchor-finalization-checklist",
        "status": "archived",
        "priority": "high",
        "service": "cj_assessment_service",
    },
    # ENG5 Flow consolidation files (to archive)
    "ENG5_CJ_ANCHOR_COMPARISON_FLOW.md": {
        "domain": "programs",
        "subdir": "eng5",
        "new_id": "eng5-cj-anchor-comparison-flow",
        "status": "archived",
        "priority": "medium",
        "service": "",
    },
    "ENG5_CJ_ANCHOR_COMPARISON_FLOW_PR_AND_DIFF.md": {
        "domain": "programs",
        "subdir": "eng5",
        "new_id": "eng5-cj-anchor-comparison-flow-pr-diff",
        "status": "archived",
        "priority": "medium",
        "service": "",
    },
    # Session artifacts (to archive)
    "common-core-documentation-session-1.md": {
        "domain": "architecture",
        "subdir": None,
        "new_id": "common-core-documentation-session-1",
        "status": "archived",
        "priority": "low",
        "service": "",
    },
    "common-core-documentation-session-1-updated.md": {
        "domain": "architecture",
        "subdir": None,
        "new_id": "common-core-documentation-session-1-updated",
        "status": "archived",
        "priority": "low",
        "service": "",
    },
    "service-readme-standardization.md": {
        "domain": "architecture",
        "subdir": None,
        "new_id": "service-readme-standardization",
        "status": "archived",
        "priority": "low",
        "service": "",
    },
    "UNSCOPED.md": {
        "domain": "architecture",
        "subdir": None,
        "new_id": "unscoped-items",
        "status": "archived",
        "priority": "low",
        "service": "",
    },
}


def extract_frontmatter(content: str) -> tuple[Optional[Dict], str]:
    """Extract YAML frontmatter from content."""
    if not content.startswith("---"):
        return None, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, content

    try:
        fm = yaml.safe_load(parts[1])
        body = parts[2].lstrip("\n")
        return fm, body
    except Exception:
        return None, content


def create_frontmatter(mapping: Dict, created_date: str) -> Dict:
    """Create proper frontmatter from migration mapping."""
    fm = {
        "id": mapping["new_id"],
        "title": mapping["new_id"].replace("-", " ").title(),
        "type": "task",
        "status": mapping["status"],
        "priority": mapping["priority"],
        "domain": mapping["domain"],
        "owner_team": "agents",
        "created": created_date,
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
    }

    if mapping.get("service"):
        fm["service"] = mapping["service"]
    else:
        fm["service"] = ""

    fm["owner"] = ""
    fm["program"] = ""
    fm["related"] = []
    fm["labels"] = []

    return fm


def get_destination_path(mapping: Dict) -> Path:
    """Determine destination path for task."""
    domain = mapping["domain"]
    new_id = mapping["new_id"]
    subdir = mapping.get("subdir")

    domain_dir = TASKS_DIR / domain

    if subdir:
        dest_dir = domain_dir / subdir
    else:
        dest_dir = domain_dir

    dest_dir.mkdir(parents=True, exist_ok=True)

    return dest_dir / f"{new_id}.md"


def migrate_file(source_file: Path, mapping: Dict) -> bool:
    """Migrate a single file."""
    try:
        # Read source file
        content = source_file.read_text(encoding="utf-8")
        existing_fm, body = extract_frontmatter(content)

        # Determine created date
        if existing_fm and "created" in existing_fm:
            created_date = existing_fm["created"]
        else:
            created_date = datetime.now().strftime("%Y-%m-%d")

        # Create new frontmatter
        new_fm = create_frontmatter(mapping, created_date)

        # Build new content
        fm_yaml = yaml.dump(new_fm, default_flow_style=False, sort_keys=False)
        new_content = f"---\n{fm_yaml}---\n\n{body}"

        # Write to destination
        dest_path = get_destination_path(mapping)
        dest_path.write_text(new_content, encoding="utf-8")

        print(f"✓ {source_file.name} → {dest_path.relative_to(TASKS_DIR)}")
        return True
    except Exception as e:
        print(f"✗ {source_file.name}: {e}")
        return False


def main():
    """Execute migration."""
    print("HuleEdu Task Migration Script")
    print("=" * 60)
    print(f"Source: {SOURCE_DIR}")
    print(f"Destination: {TASKS_DIR}")
    print()

    # Verify source directory exists
    if not SOURCE_DIR.exists():
        print(f"Error: Source directory does not exist: {SOURCE_DIR}")
        return 1

    # Get list of files to migrate
    files_to_migrate = []
    for filename in MIGRATION_MAP.keys():
        source_file = SOURCE_DIR / filename
        if source_file.exists():
            files_to_migrate.append(source_file)
        else:
            print(f"Warning: File not found: {filename}")

    print(f"Found {len(files_to_migrate)} files to migrate\n")

    # Execute migrations
    successful = 0
    failed = 0

    for source_file in sorted(files_to_migrate):
        mapping = MIGRATION_MAP[source_file.name]
        if migrate_file(source_file, mapping):
            successful += 1
        else:
            failed += 1

    print()
    print("=" * 60)
    print(f"Migration complete: {successful} successful, {failed} failed")

    if failed == 0:
        print("\nNext steps:")
        print("1. Verify migrated files in TASKS/")
        print("2. Run: python scripts/task_mgmt/validate_front_matter.py --verbose")
        print("3. Run: python scripts/task_mgmt/index_tasks.py")
        print("4. Review git diff and commit")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
