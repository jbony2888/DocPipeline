-- Migration: Add DBF audit trail tables
-- Creates submission_audit_traces and submission_audit_events for DBF compliance

-- Step 1: Create submission_audit_traces table
CREATE TABLE IF NOT EXISTS public.submission_audit_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id TEXT NOT NULL,
    owner_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    trace_version TEXT NOT NULL DEFAULT 'dbf-audit-v1',
    input JSONB NOT NULL,
    signals JSONB NOT NULL,
    rules_applied JSONB NOT NULL,
    outcome JSONB NOT NULL,
    errors JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for submission_audit_traces
CREATE INDEX IF NOT EXISTS idx_audit_traces_submission_id 
    ON public.submission_audit_traces(submission_id);

CREATE INDEX IF NOT EXISTS idx_audit_traces_owner_user_id 
    ON public.submission_audit_traces(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_audit_traces_created_at 
    ON public.submission_audit_traces(created_at DESC);

-- Step 2: Create submission_audit_events table
CREATE TABLE IF NOT EXISTS public.submission_audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id TEXT NOT NULL,
    actor_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    actor_role TEXT NOT NULL CHECK (actor_role IN ('system', 'reviewer', 'admin')),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'INGESTED',
        'OCR_COMPLETE',
        'EXTRACTION_COMPLETE',
        'VALIDATION_COMPLETE',
        'SAVED',
        'APPROVED',
        'REJECTED',
        'ESCALATED',
        'DUPLICATE_SKIPPED',
        'ERROR',
        'CACHED_LLM_RESULT'
    )),
    event_payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for submission_audit_events
CREATE INDEX IF NOT EXISTS idx_audit_events_submission_id 
    ON public.submission_audit_events(submission_id);

CREATE INDEX IF NOT EXISTS idx_audit_events_actor_user_id 
    ON public.submission_audit_events(actor_user_id);

CREATE INDEX IF NOT EXISTS idx_audit_events_event_type 
    ON public.submission_audit_events(event_type);

CREATE INDEX IF NOT EXISTS idx_audit_events_created_at 
    ON public.submission_audit_events(created_at DESC);

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_audit_events_submission_type 
    ON public.submission_audit_events(submission_id, event_type);

-- Step 3: Add status column to submissions table (if not exists)
ALTER TABLE public.submissions
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'PENDING_REVIEW';

-- Add check constraint for status
ALTER TABLE public.submissions
    DROP CONSTRAINT IF EXISTS check_submission_status;

ALTER TABLE public.submissions
    ADD CONSTRAINT check_submission_status 
    CHECK (status IN ('PENDING_REVIEW', 'PROCESSED', 'APPROVED', 'FAILED'));

-- Step 4: Enable RLS on audit tables
ALTER TABLE public.submission_audit_traces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.submission_audit_events ENABLE ROW LEVEL SECURITY;

-- Policy: Users can view their own audit traces
CREATE POLICY "Users can view own audit traces"
    ON public.submission_audit_traces
    FOR SELECT
    USING (auth.uid() = owner_user_id);

-- Policy: System can insert audit traces (via service role)
-- Note: Service role bypasses RLS, but we add policy for authenticated users
CREATE POLICY "Users can insert own audit traces"
    ON public.submission_audit_traces
    FOR INSERT
    WITH CHECK (auth.uid() = owner_user_id OR auth.uid() IS NULL);

-- Policy: Users can view their own audit events
CREATE POLICY "Users can view own audit events"
    ON public.submission_audit_events
    FOR SELECT
    USING (
        auth.uid() = actor_user_id 
        OR EXISTS (
            SELECT 1 FROM public.submissions s 
            WHERE s.submission_id = submission_audit_events.submission_id 
            AND s.owner_user_id = auth.uid()
        )
    );

-- Policy: System can insert audit events
CREATE POLICY "Users can insert own audit events"
    ON public.submission_audit_events
    FOR INSERT
    WITH CHECK (
        auth.uid() = actor_user_id 
        OR actor_role = 'system'
        OR auth.uid() IS NULL
    );

-- Grant permissions
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON public.submission_audit_traces TO authenticated;
GRANT ALL ON public.submission_audit_events TO authenticated;

-- Add comments
COMMENT ON TABLE public.submission_audit_traces IS 'DBF-compliant audit trail: Input → Signal → Rule → Outcome for each submission processing run';
COMMENT ON TABLE public.submission_audit_events IS 'Event log for major stages and human decisions (approvals, rejections, escalations)';
COMMENT ON COLUMN public.submissions.status IS 'Processing status: PENDING_REVIEW (default), PROCESSED, APPROVED, FAILED';
