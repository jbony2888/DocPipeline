-- Persist reader essay rankings for one assignment batch.

CREATE TABLE IF NOT EXISTS public.essay_rankings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    assignment_id BIGINT NOT NULL REFERENCES public.assignments(id) ON DELETE CASCADE,
    reader_id BIGINT NOT NULL REFERENCES public.readers(id) ON DELETE CASCADE,
    submission_id TEXT NOT NULL REFERENCES public.submissions(submission_id) ON DELETE CASCADE,
    school_name TEXT NOT NULL,
    grade TEXT NOT NULL,
    batch_number INTEGER NOT NULL,
    rank_position INTEGER NOT NULL CHECK (rank_position >= 1),
    reader_name TEXT NOT NULL,
    reader_email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_essay_rankings_assignment_reader_submission'
          AND conrelid = 'public.essay_rankings'::regclass
    ) THEN
        ALTER TABLE public.essay_rankings
            ADD CONSTRAINT uq_essay_rankings_assignment_reader_submission
            UNIQUE (assignment_id, reader_id, submission_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_essay_rankings_assignment_reader_rank'
          AND conrelid = 'public.essay_rankings'::regclass
    ) THEN
        ALTER TABLE public.essay_rankings
            ADD CONSTRAINT uq_essay_rankings_assignment_reader_rank
            UNIQUE (assignment_id, reader_id, rank_position);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_essay_rankings_assignment_id
ON public.essay_rankings(assignment_id);

CREATE INDEX IF NOT EXISTS idx_essay_rankings_grade
ON public.essay_rankings(grade);

CREATE INDEX IF NOT EXISTS idx_essay_rankings_school_grade
ON public.essay_rankings(school_name, grade);

CREATE INDEX IF NOT EXISTS idx_essay_rankings_submission_id
ON public.essay_rankings(submission_id);
