#!/usr/bin/env bash
# Extract CJ assessment comparison results and Bradley-Terry statistics from database

set -euo pipefail

# Configuration
DB_USER="huleedu_user"
DB_NAME="huleedu_cj_assessment"
CONTAINER="huleedu_cj_assessment_db"

# Parse arguments
BATCH_IDENTIFIER="${1:-}"
OUTPUT_FILE="${2:-}"

if [ -z "$BATCH_IDENTIFIER" ]; then
    echo "Usage: $0 <batch_id_or_bos_batch_id> [output_file]" >&2
    exit 1
fi

# Function to execute SQL query
execute_query() {
    local query="$1"
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "$query"
}

# Get batch ID
if [[ "$BATCH_IDENTIFIER" =~ ^[0-9]+$ ]]; then
    # Numeric batch ID
    BATCH_ID="$BATCH_IDENTIFIER"
    BOS_BATCH_ID=$(execute_query "SELECT bos_batch_id FROM cj_batch_uploads WHERE id = $BATCH_ID;" | xargs)
else
    # BOS batch ID
    BOS_BATCH_ID="$BATCH_IDENTIFIER"
    BATCH_ID=$(execute_query "SELECT id FROM cj_batch_uploads WHERE bos_batch_id = '$BOS_BATCH_ID';" | xargs)
fi

if [ -z "$BATCH_ID" ]; then
    echo "Error: Batch not found: $BATCH_IDENTIFIER" >&2
    exit 1
fi

# Function to write output
write_output() {
    if [ -n "$OUTPUT_FILE" ]; then
        cat >> "$OUTPUT_FILE"
    else
        cat
    fi
}

# Clear output file if it exists
if [ -n "$OUTPUT_FILE" ]; then
    > "$OUTPUT_FILE"
fi

# Header
{
    echo "=================================================================================================="
    echo "CJ ASSESSMENT RESULTS: $BOS_BATCH_ID"
    echo "=================================================================================================="
    echo "Batch ID: $BATCH_ID"
    echo ""
} | write_output

# Get batch info
{
    echo "BATCH INFORMATION:"
    execute_query "
        SELECT
            'Status: ' || status ||
            E'\nCreated: ' || created_at ||
            E'\nUpdated: ' || COALESCE(updated_at::text, 'N/A') ||
            E'\nAssignment ID: ' || assignment_id ||
            E'\nCompleted: ' || COALESCE(completed_at::text, 'N/A')
        FROM cj_batch_uploads
        WHERE id = $BATCH_ID;
    "
    echo ""
} | write_output

# Get comparison count
COMPARISON_COUNT=$(execute_query "SELECT COUNT(*) FROM cj_comparison_pairs WHERE cj_batch_id = $BATCH_ID;" | xargs)
SUCCESS_COUNT=$(execute_query "SELECT COUNT(*) FROM cj_comparison_pairs WHERE cj_batch_id = $BATCH_ID AND winner IS NOT NULL;" | xargs)
ERROR_COUNT=$(execute_query "SELECT COUNT(*) FROM cj_comparison_pairs WHERE cj_batch_id = $BATCH_ID AND error_code IS NOT NULL;" | xargs)

{
    echo "=================================================================================================="
    echo "PAIRWISE COMPARISON RESULTS"
    echo "=================================================================================================="
    echo ""
    echo "Total Comparisons: $COMPARISON_COUNT"
    echo "Successful: $SUCCESS_COUNT"
    echo "Failed: $ERROR_COUNT"
    echo ""
} | write_output

# Get all comparison results
execute_query "
SELECT
    'Comparison #' || ROW_NUMBER() OVER (ORDER BY id) || ' (ID: ' || id || ')' ||
    E'\n  Essay A: ' || essay_a_els_id ||
    E'\n  Essay B: ' || essay_b_els_id ||
    E'\n  Winner: ' || COALESCE(winner, 'ERROR') ||
    E'\n  Confidence: ' || COALESCE(confidence::text, 'N/A') || '/5.0' ||
    E'\n  Justification:' ||
    CASE
        WHEN justification IS NOT NULL THEN E'\n    ' || REPLACE(justification, E'\n', E'\n    ')
        ELSE E'\n    (No justification provided)'
    END ||
    CASE
        WHEN error_code IS NOT NULL THEN E'\n  ERROR: ' || error_code
        ELSE ''
    END ||
    E'\n  Correlation ID: ' || COALESCE(request_correlation_id::text, 'N/A') ||
    E'\n  Submitted: ' || COALESCE(submitted_at::text, 'N/A') ||
    E'\n  Completed: ' || COALESCE(completed_at::text, 'N/A') ||
    E'\n'
FROM cj_comparison_pairs
WHERE cj_batch_id = $BATCH_ID
ORDER BY id;
" | write_output

# Bradley-Terry Statistics
{
    echo ""
    echo "=================================================================================================="
    echo "BRADLEY-TERRY RANKING & STATISTICS"
    echo "=================================================================================================="
    echo ""
} | write_output

# Header row
printf "%-6s %-38s %-12s %-12s %-6s %-8s %-6s %-8s\n" \
    "Rank" "Essay ID" "BT Score" "BT SE" "Wins" "Losses" "Total" "Anchor" | write_output
echo "--------------------------------------------------------------------------------------------------" | write_output

# Get Bradley-Terry stats with wins/losses
execute_query "
WITH wins_losses AS (
    SELECT
        essay_id,
        SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
        COUNT(*) as total
    FROM (
        SELECT
            essay_a_els_id as essay_id,
            CASE
                WHEN winner = 'essay_a' THEN 'win'
                WHEN winner = 'essay_b' THEN 'loss'
                ELSE 'tie'
            END as result
        FROM cj_comparison_pairs
        WHERE cj_batch_id = $BATCH_ID

        UNION ALL

        SELECT
            essay_b_els_id as essay_id,
            CASE
                WHEN winner = 'essay_b' THEN 'win'
                WHEN winner = 'essay_a' THEN 'loss'
                ELSE 'tie'
            END as result
        FROM cj_comparison_pairs
        WHERE cj_batch_id = $BATCH_ID
    ) combined
    GROUP BY essay_id
)
SELECT
    ROW_NUMBER() OVER (ORDER BY pe.current_bt_score DESC NULLS LAST) || '      ' ||
    pe.els_essay_id || '  ' ||
    COALESCE(ROUND(pe.current_bt_score::numeric, 4)::text, 'N/A       ') || '  ' ||
    COALESCE(ROUND(pe.current_bt_se::numeric, 4)::text, 'N/A       ') || '  ' ||
    COALESCE(wl.wins::text, '0') || '      ' ||
    COALESCE(wl.losses::text, '0') || '        ' ||
    COALESCE(wl.total::text, '0') || '      ' ||
    CASE WHEN pe.is_anchor THEN 'Yes' ELSE 'No' END
FROM cj_processed_essays pe
LEFT JOIN wins_losses wl ON pe.els_essay_id = wl.essay_id
WHERE pe.cj_batch_id = $BATCH_ID
ORDER BY pe.current_bt_score DESC NULLS LAST;
" | write_output

# Footer
{
    echo ""
    echo "=================================================================================================="
    ESSAY_COUNT=$(execute_query "SELECT COUNT(*) FROM cj_processed_essays WHERE cj_batch_id = $BATCH_ID;" | xargs)
    echo "Total Essays: $ESSAY_COUNT"
    echo "Total Comparisons: $COMPARISON_COUNT"
    echo "Successful Comparisons: $SUCCESS_COUNT"
    echo "Failed Comparisons: $ERROR_COUNT"
    echo "=================================================================================================="
} | write_output

if [ -n "$OUTPUT_FILE" ]; then
    echo "Results written to: $OUTPUT_FILE" >&2
fi
