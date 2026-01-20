-- Migration: Update grade column to support text values (Kindergarten, K, etc.)
-- This allows grade to be either an integer (1-12) or text ("K", "Kindergarten", etc.)

-- First, update the column type to TEXT
ALTER TABLE submissions 
ALTER COLUMN grade TYPE TEXT USING 
  CASE 
    WHEN grade IS NULL THEN NULL
    WHEN grade::text = 'K' THEN 'K'
    ELSE grade::text
  END;

-- Add a comment explaining the format
COMMENT ON COLUMN submissions.grade IS 'Grade level: integer (1-12) or text (K, Kindergarten, Pre-K, etc.)';





