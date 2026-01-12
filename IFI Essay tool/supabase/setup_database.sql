-- Complete Database Setup Script for IFI Essay Gateway
-- Run this script in Supabase SQL Editor to set up all tables and policies
-- 
-- Instructions:
-- 1. Go to: https://supabase.com/dashboard/project/YOUR_PROJECT_ID/sql/new
-- 2. Copy and paste this entire script
-- 3. Click "Run" to execute

-- ============================================================================
-- STEP 1: Create submissions table
-- ============================================================================

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
    essay_text TEXT, -- Optional: full essay text content
    owner_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- STEP 2: Create indexes for performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_submissions_owner_user_id 
    ON public.submissions(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_submissions_needs_review 
    ON public.submissions(needs_review);

CREATE INDEX IF NOT EXISTS idx_submissions_created_at 
    ON public.submissions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_submissions_grade 
    ON public.submissions(grade);

CREATE INDEX IF NOT EXISTS idx_submissions_school_name 
    ON public.submissions(school_name);

-- ============================================================================
-- STEP 3: Create function to auto-update updated_at timestamp
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- STEP 4: Create trigger for auto-updating updated_at
-- ============================================================================

DROP TRIGGER IF EXISTS update_submissions_updated_at ON public.submissions;
CREATE TRIGGER update_submissions_updated_at
    BEFORE UPDATE ON public.submissions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- STEP 5: Enable Row Level Security (RLS)
-- ============================================================================

ALTER TABLE public.submissions ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- STEP 6: Create RLS Policies
-- ============================================================================

-- Drop existing policies if they exist (for re-running script)
DROP POLICY IF EXISTS "Users can view own submissions" ON public.submissions;
DROP POLICY IF EXISTS "Users can insert own submissions" ON public.submissions;
DROP POLICY IF EXISTS "Users can update own submissions" ON public.submissions;
DROP POLICY IF EXISTS "Users can delete own submissions" ON public.submissions;

-- Policy: Users can only SELECT their own submissions
CREATE POLICY "Users can view own submissions"
    ON public.submissions
    FOR SELECT
    USING (auth.uid() = owner_user_id);

-- Policy: Users can only INSERT their own submissions
CREATE POLICY "Users can insert own submissions"
    ON public.submissions
    FOR INSERT
    WITH CHECK (auth.uid() = owner_user_id);

-- Policy: Users can only UPDATE their own submissions
CREATE POLICY "Users can update own submissions"
    ON public.submissions
    FOR UPDATE
    USING (auth.uid() = owner_user_id)
    WITH CHECK (auth.uid() = owner_user_id);

-- Policy: Users can only DELETE their own submissions
CREATE POLICY "Users can delete own submissions"
    ON public.submissions
    FOR DELETE
    USING (auth.uid() = owner_user_id);

-- ============================================================================
-- STEP 7: Grant permissions
-- ============================================================================

GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON public.submissions TO authenticated;

-- ============================================================================
-- STEP 8: Add table and column comments
-- ============================================================================

COMMENT ON TABLE public.submissions IS 'Stores essay submission records, scoped to individual teachers via owner_user_id';
COMMENT ON COLUMN public.submissions.owner_user_id IS 'References auth.users(id) - ensures each submission belongs to a teacher';
COMMENT ON COLUMN public.submissions.needs_review IS 'Flag indicating if submission requires manual review';
COMMENT ON COLUMN public.submissions.review_reason_codes IS 'Semicolon-separated codes explaining why review is needed (e.g., MISSING_STUDENT_NAME;MISSING_GRADE)';

-- ============================================================================
-- Verification queries (optional - run these to verify setup)
-- ============================================================================

-- Check if table exists
-- SELECT EXISTS (
--     SELECT FROM information_schema.tables 
--     WHERE table_schema = 'public' 
--     AND table_name = 'submissions'
-- );

-- Check RLS policies
-- SELECT * FROM pg_policies WHERE tablename = 'submissions';

-- Check indexes
-- SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'submissions';



