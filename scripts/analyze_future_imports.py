#!/usr/bin/env python3
"""
Script to analyze Python files in services/ directory to identify which ones need
'from __future__ import annotations' import.
"""

import os
import re
from pathlib import Path
from typing import Dict, List


def has_future_annotations(content: str) -> bool:
    """Check if file already has 'from __future__ import annotations' import."""
    return "from __future__ import annotations" in content

def has_type_annotations(content: str) -> bool:
    """Check if file contains type annotations that would benefit from future annotations."""
    patterns = [
        r'def\s+\w+\(.*?\)\s*->',  # Function return type annotations
        r':\s*[A-Z]\w*[\[\|]',      # Type hints like : List[str], : Union[int, str]
        r':\s*Optional\[',          # Optional types
        r':\s*Dict\[',              # Dict types
        r':\s*List\[',              # List types
        r':\s*Set\[',               # Set types
        r':\s*Tuple\[',             # Tuple types
        r':\s*Callable\[',          # Callable types
        r':\s*Union\[',             # Union types
        r':\s*Protocol\b',          # Protocol definitions
        r'class\s+\w+\([^)]*Protocol[^)]*\)',  # Protocol inheritance
        r'\|\s*None',               # New union syntax (str | None)
        r'\w+\s*\|\s*\w+',          # New union syntax (int | str)
    ]

    for pattern in patterns:
        if re.search(pattern, content, re.MULTILINE):
            return True
    return False

def is_implementation_file(filepath: str, content: str) -> bool:
    """Check if this is a substantial implementation file vs just config/simple script."""
    filename = os.path.basename(filepath)

    # Skip certain file types that typically don't need future annotations
    skip_files = {
        '__init__.py',
        'conftest.py',
    }

    if filename in skip_files:
        return False

    # Skip if it's a very simple file (less than 20 lines)
    if len(content.splitlines()) < 20:
        return False

    # Check for implementation indicators
    implementation_patterns = [
        r'class\s+\w+',           # Class definitions
        r'def\s+\w+',             # Function definitions
        r'async\s+def\s+\w+',     # Async function definitions
        r'from\s+typing\s+import', # Type imports
        r'import\s+.*typing',      # Type imports
        r'Protocol\b',            # Protocol usage
        r'@\w+',                  # Decorators
    ]

    for pattern in implementation_patterns:
        if re.search(pattern, content, re.MULTILINE):
            return True

    return False

def analyze_services_directory() -> Dict[str, List[str]]:
    """Analyze all Python files in services/ directory."""
    results = {
        'needs_future_import': [],
        'already_has_import': [],
        'simple_files_skipped': [],
        'no_types_found': []
    }

    services_path = Path("services")

    for py_file in services_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {py_file}: {e}")
            continue

        file_path = str(py_file)

        # Check if it's an implementation file worth analyzing
        if not is_implementation_file(file_path, content):
            results['simple_files_skipped'].append(file_path)
            continue

        # Check if it already has the future import
        if has_future_annotations(content):
            results['already_has_import'].append(file_path)
            continue

        # Check if it has type annotations
        if has_type_annotations(content):
            results['needs_future_import'].append(file_path)
        else:
            results['no_types_found'].append(file_path)

    return results

def main():
    """Main function to run the analysis."""
    print("Analyzing Python files in services/ directory...")
    print("=" * 60)

    results = analyze_services_directory()

    print("\n📊 ANALYSIS RESULTS:")
    print(f"  Files needing future import: {len(results['needs_future_import'])}")
    print(f"  Files already with import: {len(results['already_has_import'])}")
    print(f"  Simple files skipped: {len(results['simple_files_skipped'])}")
    print(f"  Implementation files without types: {len(results['no_types_found'])}")

    if results['needs_future_import']:
        print("\n🎯 FILES THAT NEED 'from __future__ import annotations':")
        print("=" * 60)

        # Group by service for better organization
        by_service = {}
        for filepath in sorted(results['needs_future_import']):
            parts = filepath.split('/')
            if len(parts) >= 2:
                service = parts[1]  # services/service_name/...
                if service not in by_service:
                    by_service[service] = []
                by_service[service].append(filepath)

        for service, files in sorted(by_service.items()):
            print(f"\n📁 {service}:")
            for filepath in files:
                print(f"  • {filepath}")

    if results['no_types_found']:
        print("\n📝 IMPLEMENTATION FILES WITHOUT TYPE ANNOTATIONS:")
        print("=" * 60)
        print("(These files might benefit from adding type annotations)")

        by_service = {}
        for filepath in sorted(results['no_types_found']):
            parts = filepath.split('/')
            if len(parts) >= 2:
                service = parts[1]
                if service not in by_service:
                    by_service[service] = []
                by_service[service].append(filepath)

        for service, files in sorted(by_service.items()):
            print(f"\n📁 {service}:")
            for filepath in files:
                print(f"  • {filepath}")

if __name__ == "__main__":
    main()
