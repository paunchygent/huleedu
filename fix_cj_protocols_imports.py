#!/usr/bin/env python3
"""Fix protocol imports in CJ Assessment Service to use fully qualified imports."""

import os
import re
from pathlib import Path


def fix_protocols_import(file_path: Path) -> bool:
    """Fix protocol imports in a single file."""
    try:
        with open(file_path, "r") as f:
            content = f.read()

        original_content = content

        # Replace various patterns of protocol imports
        patterns_and_replacements = [
            # Multi-line imports
            (
                r"from protocols import \(\s*([^)]+)\s*\)",
                r"from services.cj_assessment_service.protocols import (\1)",
            ),
            # Single line imports
            (
                r"from protocols import ([^\n]+)",
                r"from services.cj_assessment_service.protocols import \1",
            ),
        ]

        for pattern, replacement in patterns_and_replacements:
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)

        if content != original_content:
            with open(file_path, "w") as f:
                f.write(content)
            print(f"✓ Fixed imports in {file_path}")
            return True
        else:
            print(f"- No changes needed in {file_path}")
            return False

    except Exception as e:
        print(f"✗ Error processing {file_path}: {e}")
        return False


def main():
    """Fix all protocol imports in CJ Assessment Service."""
    cj_service_dir = Path("services/cj_assessment_service")

    if not cj_service_dir.exists():
        print(f"Directory {cj_service_dir} does not exist!")
        return

    # Find all Python files that import from protocols
    python_files = []
    for root, dirs, files in os.walk(cj_service_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                try:
                    with open(file_path, "r") as f:
                        content = f.read()
                    if "from protocols import" in content:
                        python_files.append(file_path)
                except Exception:
                    continue

    print(f"Found {len(python_files)} files with protocol imports:")
    for file_path in python_files:
        print(f"  {file_path}")

    print("\nFixing imports...")
    fixed_count = 0
    for file_path in python_files:
        if fix_protocols_import(file_path):
            fixed_count += 1

    print(f"\nCompleted: Fixed imports in {fixed_count}/{len(python_files)} files")


if __name__ == "__main__":
    main()
