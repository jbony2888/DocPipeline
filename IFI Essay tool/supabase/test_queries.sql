-- Test Queries for IFI Essay Gateway Database
-- Use these queries to verify your setup and test RLS policies

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- 1. Check if table exists
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'submissions'
) AS table_exists;

-- 2. Check table structure
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'submissions'
ORDER BY ordinal_position;

-- 3. Check if RLS is enabled
SELECT 
    tablename, 
    rowsecurity AS rls_enabled
FROM pg_tables 
WHERE schemaname = 'public' 
AND tablename = 'submissions';

-- 4. List all RLS policies
SELECT 
    policyname,
    cmd AS command,
    qual AS using_expression,
    with_check AS with_check_expression
FROM pg_policies 
WHERE schemaname = 'public' 
AND tablename = 'submissions';

-- 5. Check indexes
SELECT 
    indexname,
    indexdef
FROM pg_indexes 
WHERE schemaname = 'public' 
AND tablename = 'submissions';

-- 6. Check triggers
SELECT 
    trigger_name,
    event_manipulation,
    event_object_table,
    action_statement
FROM information_schema.triggers
WHERE event_object_schema = 'public'
AND event_object_table = 'submissions';

-- ============================================================================
-- TEST DATA QUERIES (Run these as an authenticated user)
-- ============================================================================

-- Note: These queries will only return data for the currently authenticated user
-- due to RLS policies

-- 1. Count submissions for current user
SELECT COUNT(*) AS my_submission_count
FROM public.submissions;

-- 2. Get all submissions for current user
SELECT 
    submission_id,
    student_name,
    school_name,
    grade,
    needs_review,
    created_at
FROM public.submissions
ORDER BY created_at DESC
LIMIT 10;

-- 3. Get submissions that need review
SELECT 
    submission_id,
    student_name,
    school_name,
    grade,
    review_reason_codes,
    created_at
FROM public.submissions
WHERE needs_review = TRUE
ORDER BY created_at DESC;

-- 4. Get statistics for current user
SELECT 
    COUNT(*) AS total_submissions,
    COUNT(*) FILTER (WHERE needs_review = TRUE) AS needs_review_count,
    COUNT(*) FILTER (WHERE needs_review = FALSE) AS approved_count,
    COUNT(DISTINCT school_name) AS unique_schools,
    COUNT(DISTINCT grade) AS unique_grades,
    AVG(word_count) AS avg_word_count
FROM public.submissions;

-- 5. Get submissions by grade
SELECT 
    grade,
    COUNT(*) AS count,
    COUNT(*) FILTER (WHERE needs_review = TRUE) AS needs_review
FROM public.submissions
GROUP BY grade
ORDER BY grade;

-- 6. Get submissions by school
SELECT 
    school_name,
    COUNT(*) AS count,
    COUNT(*) FILTER (WHERE needs_review = TRUE) AS needs_review
FROM public.submissions
WHERE school_name IS NOT NULL
GROUP BY school_name
ORDER BY count DESC;

-- ============================================================================
-- TEST RLS POLICIES (Run these to verify security)
-- ============================================================================

-- As an authenticated user, you should only see your own data
-- Try running this query - it should only return rows where owner_user_id matches your user ID

-- Check your current user ID
SELECT auth.uid() AS current_user_id;

-- Verify you can only see your own submissions
SELECT 
    submission_id,
    owner_user_id,
    student_name,
    auth.uid() AS my_user_id,
    CASE 
        WHEN owner_user_id = auth.uid() THEN '✅ Accessible'
        ELSE '❌ Blocked by RLS'
    END AS access_status
FROM public.submissions
LIMIT 10;

-- ============================================================================
-- ADMIN QUERIES (Run these as database admin to see all data)
-- ============================================================================

-- Note: These bypass RLS - only run as admin for debugging

-- 1. See all submissions across all users (admin only)
-- SELECT 
--     submission_id,
--     owner_user_id,
--     student_name,
--     school_name,
--     created_at
-- FROM public.submissions
-- ORDER BY created_at DESC
-- LIMIT 20;

-- 2. Count submissions per user (admin only)
-- SELECT 
--     owner_user_id,
--     COUNT(*) AS submission_count
-- FROM public.submissions
-- GROUP BY owner_user_id
-- ORDER BY submission_count DESC;

-- 3. Check for orphaned submissions (submissions without valid owner)
-- SELECT 
--     submission_id,
--     owner_user_id,
--     student_name,
--     created_at
-- FROM public.submissions
-- WHERE owner_user_id NOT IN (SELECT id FROM auth.users)
-- LIMIT 10;





