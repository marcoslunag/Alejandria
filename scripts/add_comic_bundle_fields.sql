-- Migration: Add bundle fields to comic_issues table
-- Date: 2026-02-09
-- Purpose: Enable bundle/collection support for comics

-- Add bundle fields
ALTER TABLE comic_issues
ADD COLUMN IF NOT EXISTS bundle_id VARCHAR(64) NULL,
ADD COLUMN IF NOT EXISTS bundle_title VARCHAR(255) NULL,
ADD COLUMN IF NOT EXISTS bundle_range VARCHAR(50) NULL,
ADD COLUMN IF NOT EXISTS is_bundle_master BOOLEAN DEFAULT FALSE;

-- Create index for bundle queries
CREATE INDEX IF NOT EXISTS idx_comic_issues_bundle_id ON comic_issues(bundle_id);

-- Add comment
COMMENT ON COLUMN comic_issues.bundle_id IS 'Unique ID for bundle/collection (hash of download URL)';
COMMENT ON COLUMN comic_issues.bundle_title IS 'Title of the bundle (e.g., "Paper Girls Vol. 6 (TPB)")';
COMMENT ON COLUMN comic_issues.bundle_range IS 'Issue range covered by bundle (e.g., "#26-30")';
COMMENT ON COLUMN comic_issues.is_bundle_master IS 'True if this is the first issue of the bundle (responsible for download)';
