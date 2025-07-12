-- Bootstrap script for spellchecker_service database
-- Ensures required extensions are available before the application starts
CREATE EXTENSION IF NOT EXISTS pg_trgm;
