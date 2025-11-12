-- Seed script for ENG5 NP test assignment
-- Creates minimal test data to unblock ENG5 runner integration testing
--
-- Usage:
--   docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment -f /path/to/this/script.sql
--
-- Or copy-paste directly:
--   docker exec huleedu_cj_assessment_db psql -U huleedu_user -d huleedu_cj_assessment

BEGIN;

-- Clear any existing test data for this assignment ID
DELETE FROM assessment_instructions WHERE assignment_id = '00000000-0000-0000-0000-000000000001';

-- Insert ENG5 NP test assignment instruction
INSERT INTO assessment_instructions (
    assignment_id,
    instructions_text,
    grade_scale,
    student_prompt_storage_id
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'ENG5 NP Role Models Essay Assessment - Test Assignment

This is a test assignment for validating the ENG5 Comparative Judgment workflow.

Students should write an essay about role models and their importance in society.
The essay should demonstrate critical thinking and use of relevant examples.

Assessment criteria:
- Argumentation and structure
- Use of examples and evidence
- Language quality and grammar
- Depth of analysis',
    'eng5_np_legacy_9_step',
    NULL  -- Prompt storage ID will be set by cj-admin CLI or separately
);

COMMIT;

-- Verification query
SELECT
    assignment_id,
    grade_scale,
    student_prompt_storage_id,
    LEFT(instructions_text, 100) || '...' as instructions_preview,
    created_at
FROM assessment_instructions
WHERE assignment_id = '00000000-0000-0000-0000-000000000001';
