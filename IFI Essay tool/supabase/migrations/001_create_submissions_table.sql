-- Migration: Create submissions table for IFI Essay Gateway
-- This table stores essay submission records with teacher ownership

-- Create the submissions table
CREATE TABLE IF NOT EXISTS public.submissions (
    submission_id TEXT PRIMARY KEY,
    student_name TEXT,
    school_name TEXT,
    grade INTEGER,
    teacher_name TEXT,
    city_or_location TEXT,
    father_figure_name TEXT,
    phone TEXT,
    email TEXT,
    word_count INTEGER,
    ocr_confidence_avg REAL,
    needs_review BOOLEAN DEFAULT FALSE,
    review_reason_codes TEXT,
    artifact_dir TEXT,
    filename TEXT,
    owner_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_submissions_owner_user_id 
    ON public.submissions(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_submissions_needs_review 
    ON public.submissions(needs_review);

CREATE INDEX IF NOT EXISTS idx_submissions_created_at 
    ON public.submissions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_submissions_grade 
    ON public.submissions(grade);

-- Create a function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update updated_at on row updates
CREATE TRIGGER update_submissions_updated_at
    BEFORE UPDATE ON public.submissions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Enable Row Level Security (RLS)
ALTER TABLE public.submissions ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own submissions
CREATE POLICY "Users can view own submissions"
    ON public.submissions
    FOR SELECT
    USING (auth.uid() = owner_user_id);

-- Policy: Users can only insert their own submissions
CREATE POLICY "Users can insert own submissions"
    ON public.submissions
    FOR INSERT
    WITH CHECK (auth.uid() = owner_user_id);

-- Policy: Users can only update their own submissions
CREATE POLICY "Users can update own submissions"
    ON public.submissions
    FOR UPDATE
    USING (auth.uid() = owner_user_id)
    WITH CHECK (auth.uid() = owner_user_id);

-- Policy: Users can only delete their own submissions
CREATE POLICY "Users can delete own submissions"
    ON public.submissions
    FOR DELETE
    USING (auth.uid() = owner_user_id);

-- Grant necessary permissions
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON public.submissions TO authenticated;

-- Add comment to table
COMMENT ON TABLE public.submissions IS 'Stores essay submission records, scoped to individual teachers via owner_user_id';



