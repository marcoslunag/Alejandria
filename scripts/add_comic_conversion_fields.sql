-- Migration: Add conversion fields to comic_issues table
-- Run this script if you already have the comic_issues table created

-- Add converted_path column (stores path(s) to converted EPUB, separated by '|' if multiple parts)
ALTER TABLE comic_issues ADD COLUMN IF NOT EXISTS converted_path VARCHAR(2000);

-- Add converted_at column (timestamp when conversion completed)
ALTER TABLE comic_issues ADD COLUMN IF NOT EXISTS converted_at TIMESTAMP;

-- Verify columns were added
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'comic_issues'
AND column_name IN ('converted_path', 'converted_at');
