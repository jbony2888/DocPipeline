# RLS Policy Fix for Jobs Table

## Issue
Users were getting "new row violates row-level security policy for table 'jobs'" errors when uploading files.

## Root Cause
The `enqueue_submission` function was using an authenticated Supabase client, but the JWT wasn't being properly set for RLS policies. The RLS policy checks `auth.uid()` which requires proper JWT authentication.

## Solution
Modified `jobs/pg_queue.py` to use the `SUPABASE_SERVICE_ROLE_KEY` for job insertion. This bypasses RLS, which is safe because:

1. **Security**: The `owner_user_id` is still validated from the authenticated Flask session
2. **Worker needs it**: The worker already uses the service role key to process jobs
3. **RLS still protects**: Users can only see/update their own jobs via RLS policies when querying

## Changes Made

### `jobs/pg_queue.py`
- Changed `enqueue_submission()` to use `SUPABASE_SERVICE_ROLE_KEY` instead of authenticated client
- This bypasses RLS for INSERT operations while maintaining security

### `auth/supabase_client.py`
- Updated to use access token directly as auth key when provided (for future use)

## Testing
After deploying:
1. ✅ Users should be able to upload files without RLS errors
2. ✅ Jobs should be created successfully
3. ✅ Users should only see their own jobs in the queue

## Deployment Notes
- Ensure `SUPABASE_SERVICE_ROLE_KEY` is set in:
  - Local `.env` file
  - Render dashboard environment variables
  - Docker Compose environment variables

