#!/usr/bin/env python3
"""
Verify the correlation_id refactoring and find any remaining issues.
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict
import argparse

class CorrelationVerifier:
    def __init__(self):
        self.issues = defaultdict(list)
        self.patterns = {
            'optional_correlation': re.compile(
                r'correlation_id:\s*(?:UUID|str|Optional\[(?:UUID|str)\])\s*\|\s*None',
                re.MULTILINE
            ),
            'none_default': re.compile(
                r'correlation_id[^=]*=\s*None\b(?!\s*#\s*type:)',
                re.MULTILINE
            ),
            'none_comparison': re.compile(
                r'correlation_id\s*(?:is\s*)?(?:==\s*)?None|if\s+not\s+correlation_id',
                re.MULTILINE
            ),
            'optional_in_string': re.compile(
                r'correlation_id.*\?',  # TypeScript style optional
                re.MULTILINE
            ),
            'str_or_none': re.compile(
                r'str\(correlation_id\)\s+if\s+correlation_id',
                re.MULTILINE
            ),
        }
        
    def verify_file(self, file_path: Path) -> Dict[str, List[Tuple[int, str]]]:
        """Verify a single file for correlation_id issues."""
        issues = defaultdict(list)
        
        try:
            content = file_path.read_text()
            lines = content.split('\n')
            
            for pattern_name, pattern in self.patterns.items():
                for match in pattern.finditer(content):
                    line_num = content[:match.start()].count('\n') + 1
                    line_text = lines[line_num - 1].strip()
                    
                    # Skip comments and docstrings
                    if line_text.strip().startswith('#') or '"""' in line_text:
                        continue
                        
                    issues[pattern_name].append((line_num, line_text))
                    
        except Exception as e:
            print(f"Error verifying {file_path}: {e}")
            
        return dict(issues)
    
    def verify_directory(self, directory: Path) -> None:
        """Verify all Python files in a directory."""
        for file_path in directory.rglob('*.py'):
            if self._should_skip(file_path):
                continue
                
            file_issues = self.verify_file(file_path)
            if file_issues:
                self.issues[str(file_path)] = file_issues
    
    def _should_skip(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = ['.venv', '__pycache__', '.git', 'build', 'dist']
        return any(pattern in str(file_path) for pattern in skip_patterns)
    
    def generate_report(self) -> str:
        """Generate verification report."""
        report = []
        report.append("# Correlation ID Refactoring Verification Report\n")
        
        if not self.issues:
            report.append("✅ No correlation_id issues found! Refactoring appears complete.\n")
            return '\n'.join(report)
        
        # Summary
        report.append("## Summary\n")
        total_files = len(self.issues)
        total_issues = sum(len(issues) for file_issues in self.issues.values() 
                          for issues in file_issues.values())
        report.append(f"- Files with issues: {total_files}")
        report.append(f"- Total issues found: {total_issues}\n")
        
        # Issues by type
        issue_counts = defaultdict(int)
        for file_issues in self.issues.values():
            for issue_type, occurrences in file_issues.items():
                issue_counts[issue_type] += len(occurrences)
        
        report.append("## Issues by Type\n")
        for issue_type, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
            report.append(f"- {issue_type}: {count}")
        report.append("")
        
        # Detailed findings
        report.append("## Detailed Findings\n")
        
        issue_descriptions = {
            'optional_correlation': '⚠️  Optional correlation_id parameters',
            'none_default': '⚠️  correlation_id assigned None',
            'none_comparison': '⚠️  Checking if correlation_id is None',
            'optional_in_string': '⚠️  Optional correlation_id in strings',
            'str_or_none': '⚠️  Conditional string conversion',
        }
        
        for file_path, file_issues in sorted(self.issues.items()):
            report.append(f"### {file_path}\n")
            
            for issue_type, occurrences in file_issues.items():
                if occurrences:
                    report.append(f"{issue_descriptions.get(issue_type, issue_type)}:")
                    for line_num, line_text in occurrences:
                        report.append(f"  - Line {line_num}: `{line_text}`")
                    report.append("")
        
        # Recommendations
        report.append("## Recommendations\n")
        if 'optional_correlation' in issue_counts:
            report.append("1. Update remaining optional correlation_id parameters to required")
        if 'none_default' in issue_counts:
            report.append("2. Replace correlation_id=None with correlation_id=uuid4()")
        if 'none_comparison' in issue_counts:
            report.append("3. Remove None checks for correlation_id")
        if 'str_or_none' in issue_counts:
            report.append("4. Simplify string conversions since correlation_id is always present")
        
        return '\n'.join(report)
    
    def check_imports(self, directory: Path) -> Dict[str, List[str]]:
        """Check if files using UUID have proper imports."""
        import_issues = {}
        
        for file_path in directory.rglob('*.py'):
            if self._should_skip(file_path):
                continue
                
            try:
                content = file_path.read_text()
                
                # Check if file uses UUID or uuid4
                uses_uuid = 'UUID' in content and 'correlation_id' in content
                uses_uuid4 = 'uuid4()' in content
                
                if uses_uuid or uses_uuid4:
                    has_uuid_import = (
                        'from uuid import' in content or
                        'import uuid' in content
                    )
                    
                    if not has_uuid_import:
                        missing = []
                        if uses_uuid:
                            missing.append('UUID')
                        if uses_uuid4:
                            missing.append('uuid4')
                        import_issues[str(file_path)] = missing
                        
            except Exception as e:
                print(f"Error checking imports in {file_path}: {e}")
                
        return import_issues


def main():
    parser = argparse.ArgumentParser(description='Verify correlation_id refactoring')
    parser.add_argument('--output', type=Path, default=Path('correlation_verification.md'),
                        help='Output file for the report')
    parser.add_argument('--check-imports', action='store_true',
                        help='Also check for missing UUID imports')
    parser.add_argument('--services', nargs='*',
                        default=['services', 'common_core'],
                        help='Directories to verify')
    
    args = parser.parse_args()
    
    verifier = CorrelationVerifier()
    
    print("Verifying correlation_id refactoring...")
    for service_dir in args.services:
        service_path = Path(service_dir)
        if service_path.exists():
            print(f"Verifying {service_path}...")
            verifier.verify_directory(service_path)
    
    # Check imports if requested
    import_issues = {}
    if args.check_imports:
        print("\nChecking UUID imports...")
        for service_dir in args.services:
            service_path = Path(service_dir)
            if service_path.exists():
                import_issues.update(verifier.check_imports(service_path))
    
    # Generate report
    report = verifier.generate_report()
    
    # Add import issues to report
    if import_issues:
        report += "\n\n## Missing UUID Imports\n"
        for file_path, missing in sorted(import_issues.items()):
            report += f"\n{file_path}:\n"
            report += f"  - Missing imports: {', '.join(missing)}\n"
    
    # Save report
    args.output.write_text(report)
    print(f"\nVerification report saved to: {args.output}")
    
    # Print summary
    if verifier.issues:
        print(f"\n⚠️  Found issues in {len(verifier.issues)} files")
    else:
        print("\n✅ No issues found! Refactoring appears complete.")
    
    if import_issues:
        print(f"⚠️  Found {len(import_issues)} files with missing imports")


if __name__ == '__main__':
    main()