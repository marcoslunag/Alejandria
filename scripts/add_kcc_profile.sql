-- Migration: Add kcc_profile column to app_settings
-- Run this if the column doesn't exist

ALTER TABLE app_settings ADD COLUMN IF NOT EXISTS kcc_profile VARCHAR(20) DEFAULT 'KPW5';

-- Verify the column was added
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'app_settings' AND column_name = 'kcc_profile';
