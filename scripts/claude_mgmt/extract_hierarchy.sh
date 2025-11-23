#!/bin/bash
# Extract parent-child hierarchy from batch analysis reports

echo "Extracting hierarchy from batch analysis reports..."
echo ""

for report in .claude/work/reports/2025-11-22-rule-analysis-batch-*.md; do
  if [ -f "$report" ]; then
    grep -E "^\*\*Parent Rule\*\*:|^\*\*Child Rules\*\*:" "$report"
  fi
done
