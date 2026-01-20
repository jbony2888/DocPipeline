-- Migration: Create jobs table for background processing
-- This replaces Redis/RQ with a PostgreSQL-based job queue

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type TEXT NOT NULL DEFAULT 'process_submission',
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'started', 'finished', 'failed')),
    priority INTEGER DEFAULT 0,
    
    -- Job data (stored as JSONB for flexibility)
    job_data JSONB NOT NULL,
    
    -- Progress tracking
    progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
    status_message TEXT,
    
    -- Result and error tracking
    result JSONB,
    error_message TEXT,
    error_traceback TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    
    -- Worker tracking
    worker_id TEXT,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status_priority ON jobs(status, priority DESC, created_at ASC);

-- Enable Row Level Security
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own jobs
CREATE POLICY "Users can view their own jobs"
ON jobs
FOR SELECT
TO authenticated
USING (
    (job_data->>'owner_user_id')::text = auth.uid()::text
);

-- Policy: Users can create their own jobs
CREATE POLICY "Users can create their own jobs"
ON jobs
FOR INSERT
TO authenticated
WITH CHECK (
    (job_data->>'owner_user_id')::text = auth.uid()::text
);

-- Policy: Users can update their own jobs (for progress tracking)
CREATE POLICY "Users can update their own jobs"
ON jobs
FOR UPDATE
TO authenticated
USING (
    (job_data->>'owner_user_id')::text = auth.uid()::text
)
WITH CHECK (
    (job_data->>'owner_user_id')::text = auth.uid()::text
);

-- Policy: Service role can manage all jobs (for worker)
-- Note: This requires service_role key, not anon key
-- Workers will use service_role key to bypass RLS

COMMENT ON TABLE jobs IS 'Background job queue for processing submissions';
COMMENT ON COLUMN jobs.job_data IS 'JSONB containing job parameters (file_bytes as base64, filename, owner_user_id, access_token, etc.)';
COMMENT ON COLUMN jobs.result IS 'JSONB containing job result when finished';
COMMENT ON COLUMN jobs.progress IS 'Progress percentage (0-100)';





