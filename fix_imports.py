import os
import re


def fix_imports_in_file(filepath, dry_run=True):
    with open(filepath, 'r') as f:
        content = f.read()

    original = content

    # Fix imports with full service path
    replacements = [
        (r'^from config import', 'from services.cj_assessment_service.config import'),
        (r'^from protocols import', 'from services.cj_assessment_service.protocols import'),
        (r'^from di import', 'from services.cj_assessment_service.di import'),
        (r'^from models_api import', 'from services.cj_assessment_service.models_api import'),
        (r'^from models_db import', 'from services.cj_assessment_service.models_db import'),
        (r'^from enums_db import', 'from services.cj_assessment_service.enums_db import'),
    ]

    changes_made = []
    for pattern, replacement in replacements:
        if re.search(pattern, content, flags=re.MULTILINE):
            old_lines = re.findall(pattern + r'.*', content, flags=re.MULTILINE)
            new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            new_lines = re.findall(replacement.replace('import', r'import.*'), new_content, flags=re.MULTILINE)

            for old_line, new_line in zip(old_lines, new_lines):
                changes_made.append((old_line, new_line))
            content = new_content

    if content != original:
        print(f"\n=== {filepath} ===")
        for old_line, new_line in changes_made:
            print(f"  - {old_line}")
            print(f"  + {new_line}")

        if not dry_run:
            with open(filepath, 'w') as f:
                f.write(content)
            print("  ✓ Applied changes")
        else:
            print("  (DRY RUN - no changes applied)")
        return True
    return False

print("=== DRY RUN: Import fixes for cj_assessment_service ===")
print("This shows what WOULD be changed (no files will be modified)")

# Find all Python files in cj_assessment_service
for root, dirs, files in os.walk('services/cj_assessment_service'):
    # Skip test directories
    if 'tests' in root:
        continue

    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            fix_imports_in_file(filepath, dry_run=True)
