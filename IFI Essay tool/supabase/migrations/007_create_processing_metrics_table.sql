-- Migration: Create processing_metrics table for performance analytics
-- Stores per-submission processing timings and outcomes.

CREATE TABLE IF NOT EXISTS public.processing_metrics (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    submission_id TEXT,
    parent_submission_id TEXT,
    owner_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    job_id TEXT,
    filename TEXT,
    doc_class TEXT,
    ocr_provider TEXT,
    status TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'failed')),
    upload_batch_id TEXT,
    batch_run_id TEXT,
    chunk_index INTEGER,
    chunk_page_start INTEGER,
    chunk_page_end INTEGER,
    queue_wait_ms DOUBLE PRECISION,
    processing_time_ms DOUBLE PRECISION,
    ocr_time_ms DOUBLE PRECISION,
    segmentation_time_ms DOUBLE PRECISION,
    extraction_time_ms DOUBLE PRECISION,
    validation_time_ms DOUBLE PRECISION,
    pipeline_time_ms DOUBLE PRECISION,
    word_count INTEGER,
    ocr_confidence_avg DOUBLE PRECISION,
    needs_review BOOLEAN,
    is_duplicate BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_processing_metrics_owner_user_id
    ON public.processing_metrics(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_processing_metrics_submission_id
    ON public.processing_metrics(submission_id);

CREATE INDEX IF NOT EXISTS idx_processing_metrics_parent_submission_id
    ON public.processing_metrics(parent_submission_id);

CREATE INDEX IF NOT EXISTS idx_processing_metrics_status_created_at
    ON public.processing_metrics(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_processing_metrics_doc_class_created_at
    ON public.processing_metrics(doc_class, created_at DESC);

ALTER TABLE public.processing_metrics ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own processing metrics" ON public.processing_metrics;
CREATE POLICY "Users can view own processing metrics"
    ON public.processing_metrics
    FOR SELECT
    USING (auth.uid() = owner_user_id);

GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT ON public.processing_metrics TO authenticated;

COMMENT ON TABLE public.processing_metrics IS 'Per-submission processing metrics for performance, reliability, and QA analysis.';
