-- Round 2 finalist mapping: specific essays tied to a reader assignment.

CREATE TABLE IF NOT EXISTS public.assignment_finalists (
    assignment_id BIGINT NOT NULL REFERENCES public.assignments(id) ON DELETE CASCADE,
    submission_id TEXT NOT NULL REFERENCES public.submissions(submission_id) ON DELETE CASCADE,
    finalist_position INTEGER NOT NULL CHECK (finalist_position >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (assignment_id, submission_id)
);

CREATE INDEX IF NOT EXISTS idx_assignment_finalists_assignment_id
ON public.assignment_finalists(assignment_id);

CREATE INDEX IF NOT EXISTS idx_assignment_finalists_submission_id
ON public.assignment_finalists(submission_id);
