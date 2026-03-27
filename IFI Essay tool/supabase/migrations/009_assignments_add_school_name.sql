-- Backward-compatible upgrade for assignment batches by school+grade
-- Safe to run if 008 was already applied with grade-only uniqueness.

ALTER TABLE public.assignments
ADD COLUMN IF NOT EXISTS school_name TEXT;

UPDATE public.assignments
SET school_name = COALESCE(school_name, 'Unknown School')
WHERE school_name IS NULL;

ALTER TABLE public.assignments
ALTER COLUMN school_name SET NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_assignments_reader_grade'
          AND conrelid = 'public.assignments'::regclass
    ) THEN
        ALTER TABLE public.assignments DROP CONSTRAINT uq_assignments_reader_grade;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_assignments_reader_school_grade'
          AND conrelid = 'public.assignments'::regclass
    ) THEN
        ALTER TABLE public.assignments
            ADD CONSTRAINT uq_assignments_reader_school_grade UNIQUE (reader_id, school_name, grade);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_assignments_school_name ON public.assignments(school_name);
