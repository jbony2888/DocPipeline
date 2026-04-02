-- Persist batch-ranking finalization metadata so completed batches become read-only.

ALTER TABLE public.assignments
ADD COLUMN IF NOT EXISTS ranking_completed_at TIMESTAMPTZ NULL;

ALTER TABLE public.assignments
ADD COLUMN IF NOT EXISTS ranking_completed_by_name TEXT NULL;

ALTER TABLE public.assignments
ADD COLUMN IF NOT EXISTS ranking_completed_by_email TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_assignments_ranking_completed_at
ON public.assignments(ranking_completed_at);
