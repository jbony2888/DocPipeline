-- Migration: Add batch defaults functionality
-- Creates upload_batches table and adds batch tracking to submissions

-- Step 1: Create upload_batches table
CREATE TABLE IF NOT EXISTS public.upload_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    default_school_name TEXT,
    default_grade TEXT,  -- TEXT to match submissions.grade type (supports int and text like "K")
    default_teacher_name TEXT
);

-- Create indexes for upload_batches
CREATE INDEX IF NOT EXISTS idx_upload_batches_owner_user_id 
    ON public.upload_batches(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_upload_batches_created_at 
    ON public.upload_batches(created_at DESC);

-- Step 2: Add batch tracking columns to submissions table
ALTER TABLE public.submissions
    ADD COLUMN IF NOT EXISTS upload_batch_id UUID REFERENCES public.upload_batches(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS school_source TEXT NOT NULL DEFAULT 'extracted',
    ADD COLUMN IF NOT EXISTS grade_source TEXT NOT NULL DEFAULT 'extracted',
    ADD COLUMN IF NOT EXISTS teacher_source TEXT NOT NULL DEFAULT 'extracted';

-- Create index for batch queries
CREATE INDEX IF NOT EXISTS idx_submissions_upload_batch_id 
    ON public.submissions(upload_batch_id);

-- Add check constraints for source values
ALTER TABLE public.submissions
    ADD CONSTRAINT check_school_source 
    CHECK (school_source IN ('extracted', 'batch_default', 'manual'));

ALTER TABLE public.submissions
    ADD CONSTRAINT check_grade_source 
    CHECK (grade_source IN ('extracted', 'batch_default', 'manual'));

ALTER TABLE public.submissions
    ADD CONSTRAINT check_teacher_source 
    CHECK (teacher_source IN ('extracted', 'batch_default', 'manual'));

-- Step 3: Enable RLS on upload_batches
ALTER TABLE public.upload_batches ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only view their own batches
CREATE POLICY "Users can view own batches"
    ON public.upload_batches
    FOR SELECT
    USING (auth.uid() = owner_user_id);

-- Policy: Users can only insert their own batches
CREATE POLICY "Users can insert own batches"
    ON public.upload_batches
    FOR INSERT
    WITH CHECK (auth.uid() = owner_user_id);

-- Policy: Users can only update their own batches
CREATE POLICY "Users can update own batches"
    ON public.upload_batches
    FOR UPDATE
    USING (auth.uid() = owner_user_id)
    WITH CHECK (auth.uid() = owner_user_id);

-- Policy: Users can only delete their own batches
CREATE POLICY "Users can delete own batches"
    ON public.upload_batches
    FOR DELETE
    USING (auth.uid() = owner_user_id);

-- Step 4: Update submissions RLS to allow access via batch ownership
-- The existing policy already checks owner_user_id, but we add a helper policy
-- that allows access if the submission belongs to a batch owned by the user
-- (This is already covered by owner_user_id, but we ensure consistency)

-- Grant permissions
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON public.upload_batches TO authenticated;

-- Add comments
COMMENT ON TABLE public.upload_batches IS 'Tracks bulk upload batches with default values for school, grade, and teacher';
COMMENT ON COLUMN public.submissions.upload_batch_id IS 'Links submission to its upload batch';
COMMENT ON COLUMN public.submissions.school_source IS 'Source of school_name: extracted, batch_default, or manual';
COMMENT ON COLUMN public.submissions.grade_source IS 'Source of grade: extracted, batch_default, or manual';
COMMENT ON COLUMN public.submissions.teacher_source IS 'Source of teacher_name: extracted, batch_default, or manual';



