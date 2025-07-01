#!/usr/bin/env python3
"""
Update correlation_id signatures from optional to required.

This focused script specifically handles:
1. Method signatures with correlation_id parameters
2. Protocol definitions
3. Implementation matching
"""

import re
import ast
from pathlib import Path
from typing import List, Tuple, Dict, Set
import argparse
from collections import defaultdict

class SignatureUpdater:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.changes_made = defaultdict(list)
        
    def update_file(self, file_path: Path) -> List[str]:
        """Update correlation_id signatures in a file."""
        changes = []
        
        try:
            content = file_path.read_text()
            original_content = content
            
            # Pattern 1: correlation_id: UUID | None = None -> correlation_id: UUID
            pattern1 = re.compile(
                r'(\s*)(correlation_id:\s*)(UUID\s*\|\s*None)(\s*=\s*None)',
                re.MULTILINE
            )
            content = pattern1.sub(r'\1\2UUID', content)
            
            # Pattern 2: correlation_id: Optional[UUID] = None -> correlation_id: UUID
            pattern2 = re.compile(
                r'(\s*)(correlation_id:\s*)(Optional\[UUID\])(\s*=\s*None)',
                re.MULTILINE
            )
            content = pattern2.sub(r'\1\2UUID', content)
            
            # Pattern 3: correlation_id: str | None = None -> correlation_id: UUID
            pattern3 = re.compile(
                r'(\s*)(correlation_id:\s*)(str\s*\|\s*None)(\s*=\s*None)',
                re.MULTILINE
            )
            content = pattern3.sub(r'\1\2UUID', content)
            
            # Pattern 4: Fix EventEnvelope field
            pattern4 = re.compile(
                r'(correlation_id:\s*UUID\s*\|\s*None)(\s*=\s*None)(\s*#.*EventEnvelope)?',
                re.MULTILINE
            )
            if 'EventEnvelope' in content and 'correlation_id' in content:
                content = pattern4.sub(r'correlation_id: UUID = Field(default_factory=uuid4)', content)
            
            # Check if we need to add imports
            if content != original_content:
                # Check if UUID import is needed
                if 'UUID' in content and 'from uuid import' not in content:
                    # Add import after __future__ imports
                    lines = content.split('\n')
                    import_added = False
                    for i, line in enumerate(lines):
                        if (line.strip() and 
                            not line.startswith('from __future__') and 
                            not line.startswith('#') and 
                            not line.startswith('"""')):
                            lines.insert(i, 'from uuid import UUID, uuid4')
                            import_added = True
                            break
                    if import_added:
                        content = '\n'.join(lines)
                        changes.append("Added UUID imports")
                
                # Track what changed
                if pattern1.search(original_content):
                    changes.append("Updated correlation_id: UUID | None = None signatures")
                if pattern2.search(original_content):
                    changes.append("Updated correlation_id: Optional[UUID] = None signatures")
                if pattern3.search(original_content):
                    changes.append("Updated correlation_id: str | None = None signatures")
                if pattern4.search(original_content) and 'EventEnvelope' in original_content:
                    changes.append("Updated EventEnvelope correlation_id field")
                
                if not self.dry_run:
                    file_path.write_text(content)
                    
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            
        return changes
    
    def update_method_calls(self, file_path: Path) -> List[str]:
        """Update method calls that pass None for correlation_id."""
        changes = []
        
        try:
            content = file_path.read_text()
            original_content = content
            
            # Pattern 1: correlation_id=None -> correlation_id=uuid4()
            pattern1 = re.compile(r'correlation_id\s*=\s*None\b')
            content = pattern1.sub('correlation_id=uuid4()', content)
            
            # Pattern 2: Remove None checks
            pattern2 = re.compile(
                r'(correlation_id\s*=\s*)(.+?)\s+if\s+\2\s+else\s+uuid4\(\)',
                re.MULTILINE
            )
            content = pattern2.sub(r'\1\2', content)
            
            # Pattern 3: Simplify string conversions
            pattern3 = re.compile(
                r'str\(correlation_id\)\s+if\s+correlation_id\s+else\s+None'
            )
            content = pattern3.sub('str(correlation_id)', content)
            
            if content != original_content:
                # Ensure uuid4 is imported
                if 'uuid4()' in content and 'from uuid import' not in content:
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if (line.strip() and 
                            not line.startswith('from __future__') and 
                            not line.startswith('#') and 
                            not line.startswith('"""')):
                            lines.insert(i, 'from uuid import UUID, uuid4')
                            changes.append("Added uuid4 import")
                            break
                    content = '\n'.join(lines)
                
                if pattern1.search(original_content):
                    changes.append("Replaced correlation_id=None with correlation_id=uuid4()")
                if pattern2.search(original_content):
                    changes.append("Removed unnecessary None checks")
                if pattern3.search(original_content):
                    changes.append("Simplified string conversions")
                
                if not self.dry_run:
                    file_path.write_text(content)
                    
        except Exception as e:
            print(f"Error updating calls in {file_path}: {e}")
            
        return changes
    
    def process_directory(self, directory: Path) -> None:
        """Process all Python files in a directory."""
        for file_path in directory.rglob('*.py'):
            if self._should_skip(file_path):
                continue
                
            # Update signatures
            signature_changes = self.update_file(file_path)
            
            # Update method calls
            call_changes = self.update_method_calls(file_path)
            
            all_changes = signature_changes + call_changes
            
            if all_changes:
                self.changes_made[str(file_path)] = all_changes
                if self.dry_run:
                    print(f"\n[DRY RUN] {file_path}:")
                else:
                    print(f"\nUpdated {file_path}:")
                for change in all_changes:
                    print(f"  - {change}")
    
    def _should_skip(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = ['.venv', '__pycache__', '.git', 'build', 'dist', 'scripts']
        return any(pattern in str(file_path) for pattern in skip_patterns)
    
    def print_summary(self) -> None:
        """Print summary of changes."""
        total_files = len(self.changes_made)
        total_changes = sum(len(changes) for changes in self.changes_made.values())
        
        print(f"\n{'[DRY RUN] Would update' if self.dry_run else 'Updated'} {total_files} files")
        print(f"Total changes: {total_changes}")
        
        if self.dry_run:
            print("\nTo apply these changes, run with --apply flag")


def main():
    parser = argparse.ArgumentParser(
        description='Update correlation_id from optional to required in signatures'
    )
    parser.add_argument('--apply', action='store_true',
                        help='Apply changes (default is dry-run)')
    parser.add_argument('--services', nargs='*',
                        default=['services', 'common_core'],
                        help='Directories to process')
    
    args = parser.parse_args()
    
    updater = SignatureUpdater(dry_run=not args.apply)
    
    print("Updating correlation_id signatures...")
    for service_dir in args.services:
        service_path = Path(service_dir)
        if service_path.exists():
            print(f"\nProcessing {service_path}...")
            updater.process_directory(service_path)
    
    updater.print_summary()


if __name__ == '__main__':
    main()