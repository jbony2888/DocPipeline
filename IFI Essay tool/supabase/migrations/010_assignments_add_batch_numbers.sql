-- Add explicit batch numbering for school+grade reader assignments.
-- Existing rows are treated as single-batch assignments.

ALTER TABLE public.assignments
ADD COLUMN IF NOT EXISTS batch_number INTEGER;

ALTER TABLE public.assignments
ADD COLUMN IF NOT EXISTS total_batches INTEGER;

UPDATE public.assignments
SET batch_number = COALESCE(batch_number, 1),
    total_batches = COALESCE(total_batches, 1)
WHERE batch_number IS NULL
   OR total_batches IS NULL;

ALTER TABLE public.assignments
ALTER COLUMN batch_number SET NOT NULL;

ALTER TABLE public.assignments
ALTER COLUMN total_batches SET NOT NULL;

ALTER TABLE public.assignments
DROP CONSTRAINT IF EXISTS uq_assignments_reader_school_grade;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_assignments_reader_school_grade_batch'
          AND conrelid = 'public.assignments'::regclass
    ) THEN
        ALTER TABLE public.assignments
            ADD CONSTRAINT uq_assignments_reader_school_grade_batch
            UNIQUE (reader_id, school_name, grade, batch_number);
    END IF;
END $$;

ALTER TABLE public.assignments
DROP CONSTRAINT IF EXISTS assignments_batch_number_positive;

ALTER TABLE public.assignments
ADD CONSTRAINT assignments_batch_number_positive CHECK (batch_number >= 1);

ALTER TABLE public.assignments
DROP CONSTRAINT IF EXISTS assignments_total_batches_positive;

ALTER TABLE public.assignments
ADD CONSTRAINT assignments_total_batches_positive CHECK (total_batches >= 1);

ALTER TABLE public.assignments
DROP CONSTRAINT IF EXISTS assignments_batch_number_within_total;

ALTER TABLE public.assignments
ADD CONSTRAINT assignments_batch_number_within_total CHECK (batch_number <= total_batches);

CREATE INDEX IF NOT EXISTS idx_assignments_school_grade_batch
ON public.assignments(school_name, grade, batch_number);
