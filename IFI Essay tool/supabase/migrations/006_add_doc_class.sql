-- Add formal document classification column.
-- Every submission has exactly one doc_class; classification runs before extraction.
-- Existing rows default to SINGLE_TYPED (most common for legacy typed forms).
ALTER TABLE public.submissions
ADD COLUMN IF NOT EXISTS doc_class TEXT DEFAULT 'SINGLE_TYPED';

COMMENT ON COLUMN public.submissions.doc_class IS 'DocClass: SINGLE_TYPED | SINGLE_SCANNED | MULTI_PAGE_SINGLE | BULK_SCANNED_BATCH';
