ALTER TABLE public.submissions
ADD COLUMN IF NOT EXISTS parent_submission_id TEXT,
ADD COLUMN IF NOT EXISTS chunk_index INTEGER,
ADD COLUMN IF NOT EXISTS chunk_page_start INTEGER,
ADD COLUMN IF NOT EXISTS chunk_page_end INTEGER,
ADD COLUMN IF NOT EXISTS is_chunk BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS template_detected BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_container_parent BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_submissions_parent_submission_id
    ON public.submissions(parent_submission_id);

CREATE INDEX IF NOT EXISTS idx_submissions_chunk_pages
    ON public.submissions(chunk_page_start, chunk_page_end);
