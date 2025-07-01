#!/usr/bin/env python3
"""
Analyze correlation_id usage patterns across the codebase to prepare for refactoring.

This script will:
1. Find all correlation_id definitions and usages
2. Identify where correlation_id is generated vs passed through
3. Find test files that need updating
4. Generate a refactoring report
"""

import re
import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict
import json

# Patterns to search for
CORRELATION_PATTERNS = {
    'optional_param': re.compile(r'correlation_id:\s*(?:UUID|str|Optional\[(?:UUID|str)\])\s*\|\s*None'),
    'none_default': re.compile(r'correlation_id[^=]*=\s*None'),
    'uuid_generation': re.compile(r'(?:uuid4\(\)|UUID\()|correlation_id\s*=\s*(?:uuid4\(\)|UUID\()'),
    'conditional_none': re.compile(r'correlation_id[^=]*=.*?if.*?else\s*None'),
    'string_conversion': re.compile(r'str\(correlation_id\)'),
    'none_check': re.compile(r'if\s+correlation_id\s*(?:is\s*)?(?:None|not)'),
}

class CorrelationIdAnalyzer:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.findings = defaultdict(list)
        self.statistics = defaultdict(int)
        
    def analyze_file(self, file_path: Path) -> Dict[str, List[Tuple[int, str]]]:
        """Analyze a single file for correlation_id patterns."""
        results = defaultdict(list)
        
        try:
            content = file_path.read_text()
            lines = content.split('\n')
            
            for pattern_name, pattern in CORRELATION_PATTERNS.items():
                for match in pattern.finditer(content):
                    line_num = content[:match.start()].count('\n') + 1
                    line_content = lines[line_num - 1].strip()
                    results[pattern_name].append((line_num, line_content))
                    
            # Special analysis for method definitions
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for arg in node.args.args:
                            if arg.arg == 'correlation_id':
                                line_num = node.lineno
                                line_content = lines[line_num - 1].strip()
                                
                                # Check if it has a default value
                                defaults_start = len(node.args.args) - len(node.args.defaults)
                                arg_index = next((i for i, a in enumerate(node.args.args) if a.arg == 'correlation_id'), -1)
                                
                                if arg_index >= defaults_start and arg_index - defaults_start < len(node.args.defaults):
                                    default = node.args.defaults[arg_index - defaults_start]
                                    if isinstance(default, ast.Constant) and default.value is None:
                                        results['method_with_none_default'].append((line_num, f"{node.name}() method"))
                                        
            except SyntaxError:
                # Some files might have syntax that ast can't parse
                pass
                
        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")
            
        return dict(results)
    
    def analyze_directory(self, directory: Path) -> None:
        """Analyze all Python files in a directory."""
        for file_path in directory.rglob('*.py'):
            if not self._should_skip(file_path):
                results = self.analyze_file(file_path)
                if results:
                    self.findings[str(file_path.relative_to(self.base_dir))] = results
                    
                    # Update statistics
                    for pattern_name, occurrences in results.items():
                        self.statistics[pattern_name] += len(occurrences)
    
    def _should_skip(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = ['.venv', '__pycache__', '.git', 'build', 'dist']
        return any(pattern in str(file_path) for pattern in skip_patterns)
    
    def find_generation_points(self) -> Dict[str, List[str]]:
        """Find where correlation_ids are generated vs passed through."""
        generation_points = defaultdict(list)
        
        for file_path, results in self.findings.items():
            if 'uuid_generation' in results:
                for line_num, line in results['uuid_generation']:
                    generation_points[file_path].append(f"Line {line_num}: {line}")
                    
        return dict(generation_points)
    
    def find_test_files(self) -> List[str]:
        """Find test files that might need updating."""
        test_files = []
        
        for file_path in self.findings.keys():
            if 'test' in file_path.lower() or file_path.endswith('_test.py'):
                test_files.append(file_path)
                
        return test_files
    
    def generate_report(self) -> str:
        """Generate a comprehensive report."""
        report = []
        report.append("# Correlation ID Usage Analysis Report\n")
        
        # Statistics
        report.append("## Statistics\n")
        total_files = len(self.findings)
        report.append(f"- Total files with correlation_id: {total_files}")
        report.append(f"- Optional parameters: {self.statistics['optional_param']}")
        report.append(f"- None defaults: {self.statistics['none_default']}")
        report.append(f"- Conditional None assignments: {self.statistics['conditional_none']}")
        report.append(f"- UUID generation points: {self.statistics['uuid_generation']}")
        report.append(f"- String conversions: {self.statistics['string_conversion']}")
        report.append(f"- None checks: {self.statistics['none_check']}")
        report.append("")
        
        # Generation points
        generation_points = self.find_generation_points()
        if generation_points:
            report.append("## Correlation ID Generation Points\n")
            report.append("These locations generate new correlation IDs:\n")
            for file_path, locations in generation_points.items():
                report.append(f"### {file_path}")
                for location in locations:
                    report.append(f"- {location}")
                report.append("")
        
        # Test files
        test_files = self.find_test_files()
        if test_files:
            report.append("## Test Files Requiring Updates\n")
            for file_path in test_files:
                report.append(f"- {file_path}")
            report.append("")
        
        # Detailed findings by pattern
        report.append("## Detailed Findings by Pattern\n")
        
        pattern_descriptions = {
            'optional_param': 'Optional correlation_id parameters',
            'none_default': 'Parameters with None as default',
            'conditional_none': 'Conditional None assignments',
            'uuid_generation': 'UUID generation locations',
            'string_conversion': 'String conversions of correlation_id',
            'none_check': 'Checks for None correlation_id',
            'method_with_none_default': 'Methods with None default for correlation_id'
        }
        
        for pattern_name, description in pattern_descriptions.items():
            files_with_pattern = [
                (file_path, results[pattern_name]) 
                for file_path, results in self.findings.items() 
                if pattern_name in results
            ]
            
            if files_with_pattern:
                report.append(f"### {description}\n")
                for file_path, occurrences in files_with_pattern:
                    report.append(f"**{file_path}**")
                    for line_num, line in occurrences:
                        report.append(f"  - Line {line_num}: `{line}`")
                    report.append("")
        
        return '\n'.join(report)
    
    def export_findings(self, output_path: Path) -> None:
        """Export findings to JSON for programmatic use."""
        export_data = {
            'statistics': dict(self.statistics),
            'findings': dict(self.findings),
            'generation_points': self.find_generation_points(),
            'test_files': self.find_test_files()
        }
        
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze correlation_id usage in the codebase')
    parser.add_argument('--base-dir', type=Path, default=Path.cwd(),
                        help='Base directory of the project')
    parser.add_argument('--output', type=Path, default=Path('correlation_id_analysis.md'),
                        help='Output file for the report')
    parser.add_argument('--json', type=Path,
                        help='Export findings as JSON')
    parser.add_argument('--services', nargs='*',
                        default=['services', 'common_core'],
                        help='Service directories to analyze')
    
    args = parser.parse_args()
    
    analyzer = CorrelationIdAnalyzer(args.base_dir)
    
    print("Analyzing correlation_id usage patterns...")
    for service_dir in args.services:
        service_path = args.base_dir / service_dir
        if service_path.exists():
            print(f"Analyzing {service_path}...")
            analyzer.analyze_directory(service_path)
    
    # Generate and save report
    report = analyzer.generate_report()
    args.output.write_text(report)
    print(f"\nReport saved to: {args.output}")
    
    # Export JSON if requested
    if args.json:
        analyzer.export_findings(args.json)
        print(f"Findings exported to: {args.json}")
    
    # Print summary
    print(f"\nSummary:")
    print(f"  Files analyzed: {len(analyzer.findings)}")
    print(f"  Optional parameters found: {analyzer.statistics['optional_param']}")
    print(f"  None defaults found: {analyzer.statistics['none_default']}")
    print(f"  Generation points: {analyzer.statistics['uuid_generation']}")


if __name__ == '__main__':
    main()