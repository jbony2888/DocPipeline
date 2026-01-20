-- Make essay-submissions bucket public for shareable URLs
-- Run this in Supabase SQL Editor

-- ============================================================================
-- STEP 1: Make the bucket public
-- ============================================================================
UPDATE storage.buckets 
SET public = true 
WHERE id = 'essay-submissions';

-- ============================================================================
-- STEP 2: Add policy to allow public read access
-- ============================================================================
-- This allows anyone (even unauthenticated users) to read files from the bucket
-- Files will be accessible via public URLs like:
-- https://escbcdjlafzjxzqiephc.supabase.co/storage/v1/object/public/essay-submissions/...

DROP POLICY IF EXISTS "Public can read files" ON storage.objects;
CREATE POLICY "Public can read files"
ON storage.objects
FOR SELECT
TO public
USING (
    bucket_id = 'essay-submissions'
);

-- ============================================================================
-- STEP 3: Verify the bucket is public
-- ============================================================================
-- Run this query to verify:
-- SELECT id, name, public FROM storage.buckets WHERE id = 'essay-submissions';
-- Should show: public = true

-- ============================================================================
-- NOTE: Upload/Update/Delete policies remain restricted to authenticated users
-- Only READ access is public for shareable URLs
-- ============================================================================





