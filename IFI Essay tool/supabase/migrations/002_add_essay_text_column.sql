-- Migration: Add essay_text column to store the actual essay content
-- This is optional - add if you want to store essay text in the database

ALTER TABLE public.submissions 
ADD COLUMN IF NOT EXISTS essay_text TEXT;

-- Add comment
COMMENT ON COLUMN public.submissions.essay_text IS 'The full text content of the student essay';





