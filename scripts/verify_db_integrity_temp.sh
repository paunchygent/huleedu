#!/bin/bash
source .env

echo "=== 1. Content Service Inventory ==="
docker exec huleedu_content_service_db psql -U "$HULEEDU_DB_USER" -d huleedu_content -c \
  "SELECT COUNT(*) as total_content, content_type, MIN(created_at) as oldest, MAX(created_at) as newest
   FROM stored_content GROUP BY content_type;"

echo -e "\n=== 2. CJ Anchor References ==="
docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d huleedu_cj_assessment -c \
  "SELECT COUNT(*) as total, COUNT(DISTINCT text_storage_id) as unique_storage_ids,
   COUNT(*) FILTER (WHERE text_storage_id IS NULL) as null_storage_ids
   FROM anchor_essay_references;"

echo -e "\n=== 3. Check for Null Storage IDs in Anchors ==="
docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d huleedu_cj_assessment -c \
  "SELECT id, anchor_label, grade FROM anchor_essay_references WHERE text_storage_id IS NULL;"

echo -e "\n=== 4. Export Anchor Storage IDs for Cross-Check ==="
docker exec huleedu_cj_assessment_db psql -U "$HULEEDU_DB_USER" -d huleedu_cj_assessment -t -A -c \
  "SELECT text_storage_id FROM anchor_essay_references WHERE text_storage_id IS NOT NULL ORDER BY id;" \
  > /tmp/anchor_storage_ids.txt

echo -e "\n=== 5. Verify All Anchor IDs Exist in Content Service ==="
success=0
total=0
while IFS= read -r storage_id; do
  total=$((total + 1))
  if curl -sf "http://localhost:8001/v1/content/${storage_id}" > /dev/null 2>&1; then
    success=$((success + 1))
  else
    echo "❌ ORPHANED: ${storage_id}"
  fi
done < /tmp/anchor_storage_ids.txt

echo -e "\nResult: $success/$total anchor storage IDs verified"
rm /tmp/anchor_storage_ids.txt

if [ "$success" -eq "$total" ]; then
  echo "✅ NO ORPHANED REFERENCES FOUND"
  exit 0
else
  echo "❌ ORPHANED REFERENCES DETECTED - Re-registration needed"
  exit 1
fi
