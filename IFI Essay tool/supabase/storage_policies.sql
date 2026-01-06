-- Supabase Storage Policies for essay-submissions bucket
-- Run this in Supabase SQL Editor to allow authenticated users to upload/download files

-- ============================================================================
-- STEP 1: Enable RLS on storage.objects (if not already enabled)
-- ============================================================================
-- Note: RLS is usually enabled by default on storage.objects

-- ============================================================================
-- STEP 2: Create policies for essay-submissions bucket
-- ============================================================================

-- Policy: Allow authenticated users to upload files to their own folder
DROP POLICY IF EXISTS "Users can upload files to their own folder" ON storage.objects;
CREATE POLICY "Users can upload files to their own folder"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
    bucket_id = 'essay-submissions' AND
    (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Allow authenticated users to read files from their own folder
DROP POLICY IF EXISTS "Users can read files from their own folder" ON storage.objects;
CREATE POLICY "Users can read files from their own folder"
ON storage.objects
FOR SELECT
TO authenticated
USING (
    bucket_id = 'essay-submissions' AND
    (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Allow authenticated users to update files in their own folder
DROP POLICY IF EXISTS "Users can update files in their own folder" ON storage.objects;
CREATE POLICY "Users can update files in their own folder"
ON storage.objects
FOR UPDATE
TO authenticated
USING (
    bucket_id = 'essay-submissions' AND
    (storage.foldername(name))[1] = auth.uid()::text
)
WITH CHECK (
    bucket_id = 'essay-submissions' AND
    (storage.foldername(name))[1] = auth.uid()::text
);

-- Policy: Allow authenticated users to delete files from their own folder
DROP POLICY IF EXISTS "Users can delete files from their own folder" ON storage.objects;
CREATE POLICY "Users can delete files from their own folder"
ON storage.objects
FOR DELETE
TO authenticated
USING (
    bucket_id = 'essay-submissions' AND
    (storage.foldername(name))[1] = auth.uid()::text
);

-- ============================================================================
-- STEP 3: Make bucket public for reading (optional - if you want public URLs)
-- ============================================================================
-- Uncomment the following if you want files to be publicly accessible:
-- UPDATE storage.buckets 
-- SET public = true 
-- WHERE id = 'essay-submissions';

-- ============================================================================
-- Alternative: If you want files to be readable by authenticated users only
-- ============================================================================
-- Keep bucket private and use the SELECT policy above

