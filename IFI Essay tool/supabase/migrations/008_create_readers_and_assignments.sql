-- Create reader and assignment tables for admin grade-level assignment flow

CREATE TABLE IF NOT EXISTS public.readers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.assignments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reader_id BIGINT NOT NULL REFERENCES public.readers(id) ON DELETE CASCADE,
    school_name TEXT NOT NULL,
    grade TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_assignments_reader_school_grade UNIQUE (reader_id, school_name, grade)
);

CREATE INDEX IF NOT EXISTS idx_assignments_grade ON public.assignments(grade);
CREATE INDEX IF NOT EXISTS idx_assignments_school_name ON public.assignments(school_name);
CREATE INDEX IF NOT EXISTS idx_assignments_reader_id ON public.assignments(reader_id);
